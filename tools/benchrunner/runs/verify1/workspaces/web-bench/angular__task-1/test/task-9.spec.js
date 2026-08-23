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
const { getOffset } = require('@web-bench/test-util')

test.beforeEach(async ({ page }) => {
  await page.goto('/')
})

test('Check Edit Form Title Change', async ({ page }) => {
  const editBtn = page.locator('.edit-btn:text("Edit")')
  await editBtn.click()
  await expect(page.getByText('Edit Blog')).toBeVisible()
  await expect(page.getByText('Create Blog')).toBeHidden()
  await page.locator('.close-btn').click()

  await page.getByText('Add Blog').click()
  await expect(page.getByText('Edit Blog')).toBeHidden()
  await expect(page.getByText('Create Blog')).toBeVisible()
  await page.locator('.close-btn').click()
})

test('Check Edit Directly', async ({ page }) => {
  const editBtn = page.locator('.edit-btn:text("Edit")')
  await editBtn.click()
  await page.getByLabel('title').fill('Night')
  await page.getByLabel('detail').fill('Good Night bro!')
  await page.locator('.submit-btn').click()

  await expect(page.locator('.list-item:has-text("Morning")')).toBeHidden()
  await expect(page.getByText('Morning My Friends')).toBeHidden()

  await expect(page.locator('.list-item:has-text("Night")')).toBeVisible()
  await expect(page.getByText('Good Night bro!')).toBeVisible()
})

test('Check Edit Duplication Check', async ({ page }) => {
  const editBtn = page.locator('.edit-btn:text("Edit")')
  await editBtn.click()
  await page.getByLabel('title').fill('Travel') // Travel Blog Exist
  await page.getByLabel('detail').fill('Travel Duplication Check!')

  const submitButton = page.locator('.submit-btn')

  // Check if the button is clickable, in some case will prevent
  if (!(await submitButton.isEnabled())) {
    // Submit button is not clickable, returning early.
    return
  }

  // If the button is clickable, click it
  await submitButton.click()
  expect(await page.locator('.list-item:has-text("Travel")').count()).toBe(1)
})

test('Test Edit Button in the top right of Main', async ({ page }) => {
  const c1 = await getOffset(page, '.edit-btn:text("Edit")')
  const c2 = await getOffset(page, ':text("Morning My Friends")')
  const c3 = await getOffset(page, ':text("Hello Blog")')

  // The button is positioned far to the left to ensure it does not overlap with the text "Morning My Friends"
  expect(c1.centerX).toBeGreaterThan(c2.centerX)
  expect(c1.centerY).toBeLessThan(c2.centerY)

  // The button is positioned below the header
  expect(c1.top).toBeGreaterThanOrEqual(c3.bottom)
})
