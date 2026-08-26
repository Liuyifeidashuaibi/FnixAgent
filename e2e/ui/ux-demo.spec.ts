/**
 * Copyright (C) 2026 FnixAgent. All rights reserved.
 * UX-POLISH 真实链路演示 — 真 UI → 真 API → 真 LLM，采集新功能截图（仅本地 .tmp）
 */
import { test } from '@playwright/test';
import { mkdirSync, writeFileSync, readFileSync } from 'node:fs';
import path from 'node:path';

const OUT = path.join(process.cwd(), '.tmp', 'shots-polish');
mkdirSync(OUT, { recursive: true });

test('ux-polish demo: full chain with real backend', async ({ page }) => {
  page.on('pageerror', (e) => console.error('PAGEERROR:', e.message));
  await page.addInitScript(() => {
    try {
      localStorage.setItem('fnix.onboarding.done', '1');
      localStorage.setItem('fnix.web-hint-dismissed', '1');
    } catch { /* ignore */ }
  });
  await page.goto('http://127.0.0.1:5175/');
  await page.waitForLoadState('networkidle');
  await page.waitForTimeout(1500);
  await page.screenshot({ path: path.join(OUT, 'd0-home.png') });

  // ── 发送真实任务（ask 模式，走 work stream 全管线）──
  const ta = page.locator('.glass-composer textarea').first();
  await ta.click();
  // Shift+Tab 切到 Ask 模式（纯问答不写盘，快且稳定）
  await ta.press('Shift+Tab');
  await page.waitForTimeout(300);
  const modeLabel = (await page.locator('.wb-mode-pill').first().textContent())?.trim();
  console.log('MODE_AFTER_SHIFT_TAB:', modeLabel);

  await ta.fill('用两句话介绍一下你自己');
  const t0 = Date.now();
  await ta.press('Enter');

  // ── 流式期间截一张过程图（thinking block / statusline）──
  await page.waitForTimeout(4000);
  await page.screenshot({ path: path.join(OUT, 'd1-streaming.png') });
  console.log('STREAMING_SHOT_MS:', Date.now() - t0);

  // ── 等待完成（done 后 meta 行应出现）──
  // 轮询检查 fnix-msg-meta-usage 出现（最多 120s）
  let usageShown = false;
  for (let i = 0; i < 60; i++) {
    await page.waitForTimeout(2000);
    if ((await page.locator('.fnix-msg-meta-usage').count()) > 0) { usageShown = true; break; }
    const stopBtn = page.locator('.fnix-status-line-stop');
    if ((await stopBtn.count()) === 0 && i > 20) break;
  }
  console.log('USAGE_META_SHOWN:', usageShown);
  await page.waitForTimeout(800);
  await page.screenshot({ path: path.join(OUT, 'd2-done.png') });

  // hover 最后一条 assistant 气泡让时间戳显形
  const bubble = page.locator('.fnix-turn-assistant').last();
  if ((await bubble.count()) > 0) {
    await bubble.hover();
    await page.waitForTimeout(500);
    await page.screenshot({ path: path.join(OUT, 'd3-hover-ts.png') });
  }

  // ── ⋮ 菜单 + 导出验证 ──
  const moreBtn = page.getByRole('button', { name: '更多操作' });
  if ((await moreBtn.count()) > 0) {
    await moreBtn.first().click();
    await page.waitForTimeout(300);
    await page.screenshot({ path: path.join(OUT, 'd4-more-menu.png') });
  }
});
