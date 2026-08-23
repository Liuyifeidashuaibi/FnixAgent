const { test, expect } = require('@playwright/test');

/**
 * Playwright tests to validate error handling in draft states
 * across pre-request, post-response, and test scripts
 */

test.describe('Draft Script Error Handling', () => {
  test.beforeEach(async ({ page }) => {
    // Navigate to Bruno app
    await page.goto('/');
    
    // Create a new request for testing
    await page.getByRole('button', { name: 'New Request' }).click();
    await page.getByPlaceholder('Request Name').fill('Draft Error Test');
    await page.getByRole('button', { name: 'Save' }).click();
  });

  test('should display correct context for pre-request script errors', async ({ page }) => {
    // Open pre-request script editor
    await page.getByRole('tab', { name: 'Pre-request Script' }).click();
    
    // Enter draft script with intentional error
    const preRequestScript = `// This is a draft pre-request script
console.log('Starting pre-request');
throw new Error('Pre-request draft error');
console.log('This should not execute');`;
    
    await page.getByRole('textbox', { name: 'Pre-request Script Editor' }).fill(preRequestScript);
    
    // Execute the request
    await page.getByRole('button', { name: 'Send' }).click();
    
    // Verify error is displayed with correct context
    await expect(page.getByText('Pre-request draft error')).toBeVisible();
    await expect(page.getByText('at pre-request-script.js:3')).toBeVisible();
    
    // Verify context lines are shown
    await expect(page.getByText('throw new Error')).toBeVisible();
    await expect(page.getByText('console.log')).toBeVisible();
  });

  test('should display correct context for post-response script errors', async ({ page }) => {
    // Open post-response script editor
    await page.getByRole('tab', { name: 'Post-response Script' }).click();
    
    // Enter draft script with intentional error
    const postResponseScript = `// This is a draft post-response script
console.log('Processing response');
if (response.status !== 200) {
  throw new Error('Post-response draft error: ' + response.status);
}
console.log('Response processed');`;
    
    await page.getByRole('textbox', { name: 'Post-response Script Editor' }).fill(postResponseScript);
    
    // Execute the request
    await page.getByRole('button', { name: 'Send' }).click();
    
    // Verify error is displayed with correct context
    await expect(page.getByText('Post-response draft error')).toBeVisible();
    await expect(page.getByText('at post-response-script.js:4')).toBeVisible();
    
    // Verify context lines are shown
    await expect(page.getByText('throw new Error')).toBeVisible();
  });

  test('should display correct context for test script errors', async ({ page }) => {
    // Open test script editor
    await page.getByRole('tab', { name: 'Tests' }).click();
    
    // Enter draft script with intentional error
    const testScript = `// This is a draft test script
pm.test('Status code is 200', function () {
  pm.response.to.have.status(200);
});

// Intentional error
throw new Error('Test script draft error');`;
    
    await page.getByRole('textbox', { name: 'Test Script Editor' }).fill(testScript);
    
    // Execute the request
    await page.getByRole('button', { name: 'Send' }).click();
    
    // Verify error is displayed with correct context
    await expect(page.getByText('Test script draft error')).toBeVisible();
    await expect(page.getByText('at test-script.js:7')).toBeVisible();
    
    // Verify context lines are shown
    await expect(page.getByText('throw new Error')).toBeVisible();
  });

  test('should handle unsaved changes correctly', async ({ page }) => {
    // Open pre-request script and make changes
    await page.getByRole('tab', { name: 'Pre-request Script' }).click();
    await page.getByRole('textbox', { name: 'Pre-request Script Editor' }).fill('console.log("draft change");');
    
    // Navigate away and back to verify draft state is preserved
    await page.getByRole('tab', { name: 'Headers' }).click();
    await page.getByRole('tab', { name: 'Pre-request Script' }).click();
    
    // Verify content is still there (unsaved)
    await expect(page.getByRole('textbox', { name: 'Pre-request Script Editor' })).toHaveValue('console.log("draft change");');
    
    // Add error and test
    await page.getByRole('textbox', { name: 'Pre-request Script Editor' }).fill('throw new Error("unsaved draft error");');
    await page.getByRole('button', { name: 'Send' }).click();
    
    await expect(page.getByText('unsaved draft error')).toBeVisible();
  });
});