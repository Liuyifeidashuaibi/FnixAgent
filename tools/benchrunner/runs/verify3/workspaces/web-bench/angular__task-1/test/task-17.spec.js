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

test('Test Focus in Comment TextArea with "Charming Blog!"', async ({ page }) => {
  await page.getByText('Fast Comment').click()
  // Comment will not be submitted
  await expect(page.locator('.comment-item:has-text("Charming Blog!")')).toBeHidden()

  // TextArea is focused with text 'Charming Blog!'
  const textArea = page.getByPlaceholder('Enter Your Comment')
  await expect(textArea).toBeFocused()
  await expect(textArea).toHaveValue('Charming Blog!')
})

test('Submit "Fast Comment"', async ({ page }) => {
  await page.getByText('Fast Comment').click()
  await page.locator('.comment-btn').click()

  // Comment will not be submitted
  await expect(page.locator('.comment-item:has-text("Charming Blog!")')).toBeVisible()
})
