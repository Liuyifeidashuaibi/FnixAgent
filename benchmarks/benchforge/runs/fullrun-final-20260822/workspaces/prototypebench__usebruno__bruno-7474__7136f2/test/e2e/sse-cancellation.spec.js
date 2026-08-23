const { test, expect } = require('@playwright/test');

test('SSE connection cancellation on resend', async ({ page }) => {
  // Navigate to Bruno app
  await page.goto('http://localhost:3000');
  
  // Set up SSE request
  await page.getByRole('button', { name: 'New Request' }).click();
  await page.getByLabel('URL').fill('http://localhost:3000/api/sse/stream');
  await page.getByLabel('Method').selectOption('GET');
  
  // Send first SSE request
  await page.getByRole('button', { name: 'Send' }).click();
  
  // Wait for initial SSE events
  await expect(page.getByText('SSE event')).toBeVisible();
  
  // Resend the request (should cancel previous connection)
  await page.keyboard.press('Control+Enter');
  
  // Verify only one active connection
  await page.goto('http://localhost:3000/api/sse/connections');
  const connections = await page.textContent('body');
  expect(connections).toContain('{"connections":1}');
});