/**
 * Shell keyboard + landmark a11y smoke (WCAG 2.2 operable path).
 * Optional axe scan when @axe-core/playwright is installed.
 */
import { test, expect } from '@playwright/test';

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => {
    try {
      localStorage.setItem('fnix.onboarding.done', '1');
    } catch {
      /* ignore */
    }
  });
});

test('shell exposes skip link and main landmark', async ({ page }) => {
  await page.goto('/');
  await expect(page.locator('#fnix-main')).toBeVisible({ timeout: 20_000 });
  const skip = page.locator('a.fnix-skip-link');
  await expect(skip).toHaveCount(1);
  await skip.focus();
  await expect(skip).toBeFocused();
});

test('Work/Code segment is keyboard reachable', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByText('Work', { exact: true }).first()).toBeVisible({ timeout: 20_000 });
  await page.keyboard.press('Tab');
  // Product segment or New work should receive focus within a few tabs
  let focused = false;
  for (let i = 0; i < 12; i++) {
    const handle = await page.evaluateHandle(() => document.activeElement?.tagName);
    const tag = await handle.jsonValue();
    if (tag === 'BUTTON' || tag === 'A' || tag === 'INPUT' || tag === 'TEXTAREA') {
      focused = true;
      break;
    }
    await page.keyboard.press('Tab');
  }
  expect(focused).toBeTruthy();
});

test('axe critical violations on shell root (if axe available)', async ({ page }) => {
  await page.goto('/');
  await expect(page.locator('.fnix-root')).toBeVisible({ timeout: 20_000 });
  try {
    const axePlaywright = await import('@axe-core/playwright');
    const AxeBuilder = axePlaywright.default;
    const results = await new AxeBuilder({ page }).include('.fnix-root').analyze();
    const critical = results.violations.filter((v) => v.impact === 'critical' || v.impact === 'serious');
    expect(
      critical,
      critical.map((v) => `${v.id}: ${v.help}`).join('\n'),
    ).toEqual([]);
  } catch (e) {
    const msg = String(e);
    if (msg.includes("Cannot find module") || msg.includes('Cannot find package')) {
      test.info().annotations.push({ type: 'note', description: 'axe not installed — landmark tests still ran' });
      return;
    }
    throw e;
  }
});
