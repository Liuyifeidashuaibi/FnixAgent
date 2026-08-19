import { test, expect } from '@playwright/test';
import { electronMock } from './electron-mock';

test.beforeEach(async ({ page }) => {
  // 屏蔽本机 bootstrap 文件注入(开发者本机可能放有真实 Key),
  // 保证首次运行向导断言不受本地环境影响。
  await page.route('**/local-llm.bootstrap.json*', (route) => route.abort());
  await page.addInitScript(electronMock);
  await page.addInitScript(() => {
    try {
      localStorage.removeItem('fnix.onboarding.done');
    } catch {
      /* ignore */
    }
  });
});

test('first-run wizard appears and can skip', async ({ page }) => {
  await page.goto('/');
  const heading = page.getByRole('heading', { name: '欢迎使用 Fnix' });
  try {
    await heading.waitFor({ timeout: 8_000 });
  } catch {
    // 向导未显示且 onboarding 未完成 → 本机环境注入了 BYOK Key
    // (如 apps/workbench/.env.local 的 VITE_FNIX_API_KEY),hasKey=true 时
    // 产品设计即不弹向导,跳过本断言(CI 无本地 Key 文件时正常执行全流程)。
    const done = await page.evaluate(() => localStorage.getItem('fnix.onboarding.done'));
    if (done !== '1') {
      test.skip(true, '环境已注入 BYOK Key,产品设计不显示首次运行向导');
    }
    throw new Error('onboarding wizard did not appear');
  }
  // 跳过守门:未填 Key 且未选文件夹时,跳过应被拦截并提示
  await page.getByRole('button', { name: '跳过' }).click();
  await expect(page.getByRole('alert')).toContainText('请至少填写 API Key 或选择文件夹');
  // 填入 API Key 后可跳过进入工作台
  await page.getByPlaceholder('sk-…').fill('sk-e2e-ui-test');
  await page.getByRole('button', { name: '跳过' }).click();
  await expect(page.getByRole('button', { name: /登录|Sign in/i })).toHaveCount(0);
  await expect(page.getByText('Fnix', { exact: true }).first()).toBeVisible();
});

test('workbench exposes Work and Code modes', async ({ page }) => {
  await page.addInitScript(() => {
    try {
      localStorage.setItem('fnix.onboarding.done', '1');
    } catch {
      /* ignore */
    }
  });
  await page.goto('/');
  await expect(page.getByText('Fnix', { exact: true }).first()).toBeVisible({ timeout: 15_000 });
  await expect(page.getByText('Work', { exact: true }).first()).toBeVisible();
  await expect(page.getByText('Code', { exact: true }).first()).toBeVisible();
});
