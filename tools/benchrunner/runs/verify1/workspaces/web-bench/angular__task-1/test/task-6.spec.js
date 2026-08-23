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

test('Check Submit Work Blog', async ({ page }) => {
  await page.getByText('Add Blog').click()
  await page.getByLabel('title').fill('Work')
  await page.getByLabel('detail').fill('Work in ByteDance is pleasant!')
  await page.locator('.submit-btn').click()

  await expect(page.locator('.list-item:has-text("Work")')).toBeVisible()
  await expect(page.getByText('Work in ByteDance is pleasant!')).toBeVisible()
})

test('Check Submit Family Blog', async ({ page }) => {
  await page.getByText('Add Blog').click()
  await page.getByLabel('title').fill('Family')
  await page.getByLabel('detail').fill('I love my family!')
  await page.locator('.submit-btn').click()

  await expect(page.locator('.list-item:has-text("Family")')).toBeVisible()
  await expect(page.getByText('I love my family!')).toBeVisible()
})

test('Check Keep Mock Data', async ({ page }) => {
  await expect(page.locator('.list-item:has-text("Morning")')).toBeVisible()
  await expect(page.locator('.list-item:has-text("Travel")')).toBeVisible()
})
