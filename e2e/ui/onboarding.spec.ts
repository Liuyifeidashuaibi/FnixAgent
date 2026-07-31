import { test, expect } from '@playwright/test';
import { electronMock } from './electron-mock';

test.beforeEach(async ({ page }) => {
  await page.addInitScript(electronMock);
  await page.addInitScript(() => {
    try {
      localStorage.removeItem('fnixagent-onboarded-v1');
    } catch {
      /* ignore */
    }
  });
});

test('first-run wizard appears and can skip', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByRole('heading', { name: /接入你的 API Key/i })).toBeVisible({
    timeout: 15_000,
  });
  await page.getByRole('button', { name: /稍后配置/i }).click();
  await expect(page.getByRole('button', { name: /登录|Sign in/i })).toHaveCount(0);
  await expect(page.getByText('Fnix', { exact: true }).first()).toBeVisible();
});

test('workbench exposes Work and Code modes', async ({ page }) => {
  await page.addInitScript(() => {
    try {
      localStorage.setItem('fnixagent-onboarded-v1', '1');
    } catch {
      /* ignore */
    }
  });
  await page.goto('/');
  await expect(page.getByText('Fnix', { exact: true }).first()).toBeVisible({ timeout: 15_000 });
  await expect(page.getByText('Work', { exact: true }).first()).toBeVisible();
  await expect(page.getByText('Code', { exact: true }).first()).toBeVisible();
});
