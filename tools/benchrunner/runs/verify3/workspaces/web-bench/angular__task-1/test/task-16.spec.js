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

const LONG_TITLE =
  'LongLongLongLongLongLongLongLongLongLongLongLongLongLongLongLongLongLongLongLongLong'

const checkShowLongTextTooltip = async (page, show) => {
  const tooltipClassName = `.tooltip:has-text("${LONG_TITLE}")`

  expect(
    await page
      .locator(tooltipClassName)
      .evaluateAll((_tooltips) => _tooltips.some((_tooltip) => _tooltip.checkVisibility()))
  ).toBe(show)
}

test.beforeEach(async ({ page }) => {
  await page.goto('/')

  // Input a blog with long title
  await page.getByText('Add Blog').click()
  await page.getByLabel('title').fill(LONG_TITLE)
  await page.getByLabel('detail').fill('ContentContentContentContent')
  await page.locator('.submit-btn').click()
})

test('Show Tooltip For Hover Long Title List Item', async ({ page }) => {
  await page.locator('.list-item:has-text("Long")').hover()

  await checkShowLongTextTooltip(page, true)

  await page.getByText('Hello Blog').hover()

  await checkShowLongTextTooltip(page, false)
})

test('Show Tooltip For Blog Title With List Item', async ({ page }) => {
  await page.locator('.blog-title').hover()
  await checkShowLongTextTooltip(page, true)

  await page.getByText('Hello Blog').hover()
  await checkShowLongTextTooltip(page, false)
})

test('Show Tooltip For Normal Title', async ({ page }) => {
  await page.locator('.blog-title').hover()
  await checkShowLongTextTooltip(page, true)

  // Click Normal Title
  await page.locator('.list-item:has-text("Morning")').click()
  await page.locator('.blog-title').hover()
  await checkShowLongTextTooltip(page, false)
})
