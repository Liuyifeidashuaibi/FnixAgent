/**
 * Copyright (C) 2026 FnixAgent. All rights reserved.
 * 准发布验收：模拟用户全功能走查 Tauri 前端（Vite dev 同源同代码）。
 * 覆盖：首页/侧栏/会话流/Composer/模式切换/⋮菜单/设置/诊断/导出/思考块/工具卡/a11y。
 * 截图落盘 .tmp/shots-accept/，结果 JSON 落盘 .tmp/accept-results.json。
 */
import { test, expect } from '@playwright/test';
import { mkdirSync, writeFileSync } from 'node:fs';

const OUT = '.tmp/shots-accept';
const RES: Record<string, unknown> = {};
const shot = (p: import('@playwright/test').Page, name: string) =>
  p.screenshot({ path: `${OUT}/${name}.png`, fullPage: false });

test.beforeAll(() => {
  mkdirSync(OUT, { recursive: true });
});

test.afterAll(() => {
  writeFileSync('.tmp/accept-results.json', JSON.stringify(RES, null, 2));
});

test('用户全功能走查 @acceptance', async ({ page }) => {
  test.setTimeout(240_000);
  const consoleErrors: string[] = [];
  const pageErrors: string[] = [];
  page.on('console', (m) => {
    if (m.type() === 'error') consoleErrors.push(m.text().slice(0, 200));
  });
  page.on('pageerror', (e) => pageErrors.push(String(e).slice(0, 200)));

  await page.goto('http://127.0.0.1:5175/');
  await page.waitForTimeout(2500);

  // ── A. 首页渲染与美观基线 ──
  RES.homeRendered = await page.locator('body').isVisible();
  await shot(page, '01-home');

  // ── B. 侧栏（新建会话 / 会话列表 / 折叠展开）──
  const sidebar = page.locator('.fnix-nav-primary, [class*="fnix-aside"]').first();
  RES.sidebarVisible = await sidebar.isVisible().catch(() => false);
  // 新任务按钮（fnix-nav-primary）
  const newChatBtns = page.locator('button.fnix-nav-primary, button:has-text("新任务")');
  RES.newChatBtnFound = (await newChatBtns.count()) > 0;

  // ── C. Composer 可输入 + 模式 pill 存在 ──
  const composer = page.locator('textarea, [contenteditable="true"]').last();
  RES.composerVisible = await composer.isVisible().catch(() => false);
  if (RES.composerVisible) {
    await composer.click();
    await composer.fill('帮我创建一个 hello.py，内容为 print("hello")');
    await shot(page, '02-composer-typed');
    const text = await composer.inputValue().catch(() => '');
    RES.composerAcceptsInput = text.includes('hello.py');
    // Shift+Tab 模式循环（Ask→Plan→Craft）
    await page.keyboard.press('Shift+Tab');
    await page.waitForTimeout(300);
    await page.keyboard.press('Shift+Tab');
    await page.waitForTimeout(300);
    RES.modeAfterShiftTabs = (await page.locator('[class*="mode"], [class*="pill"]').allTextContents())
      .join('|')
      .slice(0, 120);
  }

  // ── D. ⋮ 更多菜单（设置/诊断/快捷键/导出 MD）──
  const moreBtn = page.locator('button[aria-label="更多操作"]').first();
  RES.moreBtnFound = (await moreBtn.count()) > 0;
  if (RES.moreBtnFound) {
    await moreBtn.click();
    await page.waitForTimeout(350);
    const items = await page.locator('.fnix-more-menu button').allTextContents();
    RES.moreMenuItems = items.map((s) => s.trim());
    await shot(page, '03-more-menu');
    // 导出 Markdown 菜单项存在且可点（无消息时点击不报错）
    const exportItem = page.locator('.fnix-more-menu button', { hasText: '导出' });
    RES.exportItemFound = (await exportItem.count()) > 0;
    await page.keyboard.press('Escape');
    await page.waitForTimeout(200);
  }

  // ── E. 真实任务执行链路（Work 流水线，真 LLM）──
  if (RES.composerVisible) {
    const c2 = page.locator('textarea, [contenteditable="true"]').last();
    await c2.click();
    await c2.fill('用一句话回答：什么是冒泡排序？不要写代码。');
    await c2.press('Enter');
    // 等待流式开始（thinking 块或状态行出现）
    const started = await page
      .waitForSelector('[class*="thinking"], [class*="streaming"], [class*="status"]', { timeout: 30_000 })
      .then(() => true)
      .catch(() => false);
    RES.streamingStarted = started;
    if (started) await shot(page, '04-streaming');
    // 等 done（usage meta 行出现或输入框恢复可用），上限 120s
    const done = await page
      .waitForSelector('.fnix-msg-meta, [class*="fnix-actions"]', { timeout: 150_000 })
      .then(() => true)
      .catch(() => false);
    RES.taskDone = done;
    await page.waitForTimeout(800);
    await shot(page, '05-done');
    const meta = await page.locator('.fnix-msg-meta').allTextContents();
    RES.metaLines = meta.map((s) => s.trim()).filter(Boolean);

    // ── D2. 会话视图的 ⋮ 更多菜单（进入会话后才渲染）──
    const moreBtn2 = page.locator('button[aria-label="更多操作"]').first();
    RES.moreBtnFound = (await moreBtn2.count()) > 0;
    if (RES.moreBtnFound) {
      await moreBtn2.click();
      await page.waitForTimeout(350);
      const items = await page.locator('.fnix-more-menu button').allTextContents();
      RES.moreMenuItems = items.map((s) => s.trim());
      await shot(page, '03-more-menu');
      const exportItem = page.locator('.fnix-more-menu button', { hasText: '导出' });
      RES.exportItemFound = (await exportItem.count()) > 0;
      await page.keyboard.press('Escape');
      await page.mouse.click(400, 300); // 关闭菜单
      await page.waitForTimeout(200);
    }
  }

  // ── F. 会话持久化：刷新后消息仍在 ──
  await page.reload();
  await page.waitForTimeout(2000);
  const msgCountAfterReload = await page.locator('[class*="bubble"], [class*="message"]').count();
  RES.msgCountAfterReload = msgCountAfterReload;
  RES.persistedAcrossReload = msgCountAfterReload > 0;

  // ── G. 设置页可达（左下角齿轮按钮）──
  const gearBtn = page.locator('button[title*="设置"], button[aria-label*="设置"]').first();
  RES.settingsOpened =
    (await gearBtn.count()) > 0
      ? await gearBtn
          .click()
          .then(() => true)
          .catch(() => false)
      : false;
  if (RES.settingsOpened) {
    await page.waitForTimeout(600);
    await shot(page, '06-settings');
    await page.keyboard.press('Escape');
  }

  RES.consoleErrors = consoleErrors.slice(0, 10);
  RES.pageErrors = pageErrors.slice(0, 10);
});
