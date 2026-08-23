const { test, expect } = require('@playwright/test');

// Test for API Key auth with 'in: query'
test('should import Postman collection with API Key in query', async ({ page }) => {
  // Navigate to Bruno app
  await page.goto('/');
  
  // Click import button
  await page.getByRole('button', { name: 'Import' }).click();
  
  // Select Postman import option
  await page.getByText('Postman Collection').click();
  
  // Upload fixture collection with query API Key
  const fileChooserPromise = page.waitForEvent('filechooser');
  await page.getByRole('button', { name: 'Choose File' }).click();
  const fileChooser = await fileChooserPromise;
  await fileChooser.setFiles('fixtures/postman/query-apikey-collection.json');
  
  // Wait for import to complete
  await page.getByRole('button', { name: 'Import' }).click();
  
  // Open the imported request
  await page.getByRole('link', { name: 'API Key Query Request' }).click();
  
  // Go to Auth tab
  await page.getByRole('tab', { name: 'Auth' }).click();
  
  // Verify placement is set to queryparams
  const placementSelect = page.getByLabel('Placement');
  await expect(placementSelect).toHaveValue('queryparams');
});