// Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
// 
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
// 
//     http://www.apache.org/licenses/LICENSE-2.0
// 
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

const { test, expect } = require('@playwright/test')

test.beforeEach(async ({ page }) => {
  await page.goto('/')
})

test('Check Blog Length', async ({ page }) => {
  await expect(page.locator('.blog-list-len')).toContainText('2')

  await page.getByText('Add Blog').click()
  await page.getByLabel('title').fill('Len Check')
  await page.getByLabel('detail').fill('Len Check 1')
  await page.locator('.submit-btn').click()
  await expect(page.locator('.blog-list-len')).toContainText('3')

  await page.getByText('Add Blog').click()
  await page.getByLabel('title').fill('Len Check 2')
  await page.getByLabel('detail').fill('Len Check 2')
  await page.locator('.submit-btn').click()
  await expect(page.locator('.blog-list-len')).toContainText('4')
})

test('Check Submit Blog With Check Duplication', async ({ page }) => {
  await page.getByText('Add Blog').click()
  await page.getByLabel('title').fill('DuplicationCheck')
  await page.getByLabel('detail').fill('DuplicationCheck Content 1')

  await page.locator('.submit-btn').click()

  const duplicationCheckListItem = page.locator('.list-item:has-text("DuplicationCheck")')
  await expect(duplicationCheckListItem).toBeVisible()
  await duplicationCheckListItem.click()
  await expect(page.getByText('DuplicationCheck Content 1')).toBeVisible()
  await expect(page.locator('.blog-list-len')).toContainText('3')

  await page.getByText('Add Blog').click()
  await page.getByLabel('title').fill('DuplicationCheck')
  await page.getByLabel('detail').fill('DuplicationCheck Content 2')

  const submitButton = page.locator('.submit-btn')

  // Check if the button is clickable, in some case will prevent
  if (!(await submitButton.isEnabled())) {
    // Submit button is not clickable, returning early.
    return
  }

  // If the button is clickable, click it
  await submitButton.click()

  expect(await page.locator('.list-item:has-text("DuplicationCheck")').count()).toBe(1)
  await expect(page.locator('.blog-list-len')).toContainText('3')
})
