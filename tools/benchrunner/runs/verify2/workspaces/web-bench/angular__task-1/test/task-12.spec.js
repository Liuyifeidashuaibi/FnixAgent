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

  page.setDefaultTimeout(500)
})

test('Check Comments Component Existed', async ({ page }) => {
  await expect(page.getByText('Comments').first()).toBeVisible()
})

test('Check Submit Comments in Current Blog', async ({ page }) => {
  await page.getByPlaceholder('Enter Your Comment').fill('Morning is Good! I love Morning!')
  await page.locator('.comment-btn').click()
  await page.getByPlaceholder('Enter Your Comment').fill('I love Morning too!')
  await page.locator('.comment-btn').click()

  await expect(page.getByText('Morning is Good! I love Morning!')).toBeVisible()
  await expect(page.getByText('I love Morning too!')).toBeVisible()

  // When switch to new blog, the comment disappeared
  await page.locator('.list-item:has-text("Travel")').click()
  await expect(page.getByText('Morning is Good! I love Morning!')).toBeHidden()
})

test('When Blog Edited, the comments still existed', async ({ page }) => {
  await page.getByPlaceholder('Enter Your Comment').fill('Morning is Good! I love Morning!')
  await page.locator('.comment-btn').click()
  await expect(page.getByText('Morning is Good! I love Morning!')).toBeVisible()

  // When delete blog and create blog with same title, the comment disappeared
  await page.locator('.edit-btn:text("Edit")').click()
  await page.getByLabel('title').fill('Morning2')
  await page.getByLabel('detail').fill('Morning Again')
  await page.locator('.submit-btn').click()
  await page.locator('.list-item:has-text("Morning")').click()
  await expect(page.getByText('Morning is Good! I love Morning!')).toBeVisible()
})

test('When Blog Deleted, the comments will be deleted', async ({ page }) => {
  await page.getByPlaceholder('Enter Your Comment').fill('Morning is Good! I love Morning!')
  await page.locator('.comment-btn').click()
  await expect(page.getByText('Morning is Good! I love Morning!')).toBeVisible()

  // When delete blog and create blog with same title, the comment disappeared
  await page.locator('.delete-btn:text("Delete")').click()

  await page.getByText('Add Blog').click()
  await page.getByLabel('title').fill('Morning')
  await page.getByLabel('detail').fill('Morning Again')
  await page.locator('.submit-btn').click()
  await page.locator('.list-item:has-text("Morning")').click()

  await expect(page.getByText('Morning is Good! I love Morning!')).toBeHidden()
})
