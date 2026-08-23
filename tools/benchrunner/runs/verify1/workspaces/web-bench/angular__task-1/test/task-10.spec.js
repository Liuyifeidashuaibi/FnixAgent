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

test('Search Input is on the top of List', async ({ page }) => {
  const c1 = await getOffset(page, 'input[placeholder="Search Blogs"]')
  const c2 = await getOffset(page, '.list-item')
  expect(c1.centerY).toBeLessThan(c2.centerY)
})

test('Filter Blogs', async ({ page }) => {
  await page.getByPlaceholder('Search Blogs').fill('Tr')
  await expect(page.locator('.blog-list-len')).toContainText('2')
  await expect(page.locator('.list-item:has-text("Morning")')).toBeHidden()
  await expect(page.locator('.list-item:has-text("Travel")')).toBeVisible()
})

test('Add New Blog And Filter It', async ({ page }) => {
  await page.getByText('Add Blog').click()
  await page.getByLabel('title').fill('TestAdd')
  await page.getByLabel('detail').fill('TestAdd Content')
  await page.locator('.submit-btn').click()

  await page.getByPlaceholder('Search Blogs').fill('TestAdd')
  await expect(page.locator('.list-item:has-text("Morning")')).toBeHidden()
  await expect(page.locator('.list-item:has-text("Travel")')).toBeHidden()
  await expect(page.locator('.list-item:has-text("TestAdd")')).toBeVisible()
})

test('Search Input width should be less than the size of component: 200px', async ({ page }) => {
  const c1 = await getOffset(page, 'input[placeholder="Search Blogs"]')

  expect(c1.width).toBeLessThanOrEqual(200)
})
