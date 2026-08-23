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

test('Check Markdown grammar: "#" -> h1, "##" -> h2, "###" -> h3', async ({ page }) => {
  await page.getByText('Add Blog').click()
  await page.getByLabel('title').fill('Markdown')
  await page.getByLabel('detail').fill('# MarkdownH1\n## MarkdownH2\n### MarkdownH3')
  await page.locator('.submit-btn').click()

  await expect(page.locator('h1:text("MarkdownH1")')).toBeVisible()
  await expect(page.locator('h2:text("MarkdownH2")')).toBeVisible()
  await expect(page.locator('h3:text("MarkdownH3")')).toBeVisible()
})

test('Check XSS protection', async ({ page }) => {
  await page.getByText('Add Blog').click()
  await page.getByLabel('title').fill('XSS')
  await page.getByLabel('detail').fill('<script>document.body.innerHTML = ""</script>')
  await page.locator('.submit-btn').click()

  // XSS injection will not break the page
  await expect(page.getByText('Hello Blog')).toBeVisible()
})
