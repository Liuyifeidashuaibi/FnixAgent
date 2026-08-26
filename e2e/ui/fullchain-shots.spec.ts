/**
 * Copyright (C) 2026 FnixAgent. All rights reserved.
 * 前端截图采集 — 输出到 .tmp/shots/*.png（仅本地查看，不入库）
 */

import { test } from '@playwright/test';
import { mkdirSync } from 'node:fs';
import path from 'node:path';

const OUT = path.join(process.cwd(), '.tmp', 'shots');
mkdirSync(OUT, { recursive: true });

test('capture: work home', async ({ page }) => {
  await page.addInitScript(() => {
    try {
      localStorage.setItem('fnix.onboarding.done', '1');
    } catch {
      /* ignore */
    }
  });
  await page.goto('/');
  await page.waitForTimeout(3500);
  await page.screenshot({ path: path.join(OUT, '1-work-home.png'), fullPage: false });

  // Composer 输入示例任务后的状态
  const composer = page.getByPlaceholder(/描述要构建|输入你的问题|提问/).first();
  if (await composer.isVisible().catch(() => false)) {
    await composer.fill('帮我制作一份 Q3 销售总结 Excel，包含图表和趋势分析');
    await page.waitForTimeout(800);
    await page.screenshot({ path: path.join(OUT, '2-composer-filled.png') });
    await composer.fill('');
  }

  // Code 模式 tab
  const codeTab = page.getByRole('tab', { name: 'Code' });
  if (await codeTab.isVisible().catch(() => false)) {
    await codeTab.click();
    await page.waitForTimeout(2500);
    await page.screenshot({ path: path.join(OUT, '3-code-mode.png') });
    await page.getByRole('tab', { name: 'Work' }).click();
    await page.waitForTimeout(1200);
  }

  // 设置页
  const settingsBtn = page.getByRole('button', { name: '设置' });
  if (await settingsBtn.isVisible().catch(() => false)) {
    await settingsBtn.click();
    await page.waitForTimeout(2000);
    await page.screenshot({ path: path.join(OUT, '4-settings.png') });
  }
});
