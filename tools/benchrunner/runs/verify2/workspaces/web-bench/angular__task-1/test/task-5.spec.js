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

test('Check Record open Modal times', async ({ page }) => {
  await page.getByText('Add Blog').click()
  await expect(page.locator('.visible-count')).toContainText('1')
  await page.locator('.close-btn').click()

  await page.getByText('Add Blog').click()
  await expect(page.locator('.visible-count')).toContainText('2')
  await page.locator('.close-btn').click()

  await page.getByText('Add Blog').click()
  await expect(page.locator('.visible-count')).toContainText('3')
  await page.locator('.close-btn').click()
})

test('Check .visible-count in the top left of Modal', async ({ page }) => {
  await page.getByText('Add Blog').click()

  const c1 = await getOffset(page, '.visible-count')
  const c2 = await getOffset(page, ':text("Create Blog")')

  expect(c1.centerX).toBeLessThanOrEqual(c2.centerX)
})
