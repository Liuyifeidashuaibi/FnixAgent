import { test, expect } from '@playwright/test';
import { electronMock } from './electron-mock';

test.beforeEach(async ({ page }) => {
  await page.addInitScript(electronMock);
});

test('opens workbench without login (Hermes-style)', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByText('Fnix', { exact: true }).first()).toBeVisible({ timeout: 15_000 });
  await expect(page.getByRole('button', { name: /登录|Sign in/i })).toHaveCount(0);
});

test('backend offline shows retry when health fails', async ({ page }) => {
  await page.addInitScript(() => {
    window.electron.backend.health = async () => ({ ok: false, error: 'mock offline' });
  });
  await page.goto('/');
  await expect(page.getByText(/后端|offline|未响应|重试/i).first()).toBeVisible({
    timeout: 15_000,
  });
});
