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

test('Jump to game when click "🎮"', async ({ page }) => {
  await page.getByText('🎮').click()
  await expect(page).toHaveURL('/game')
  await expect(page.getByText('Hello Game')).toBeVisible()
  await expect(page.getByText('Hello Blog')).toBeHidden()
})

test('Page switched when page goBack and goForward', async ({ page }) => {
  await page.getByText('🎮').click()
  await page.goBack()

  await expect(page).toHaveURL('/')
  await expect(page.getByText('Hello Game')).toBeHidden()
  await expect(page.getByText('Hello Blog')).toBeVisible()

  await page.goForward()
  await expect(page).toHaveURL('/game')
  await expect(page.getByText('Hello Game')).toBeVisible()
  await expect(page.getByText('Hello Blog')).toBeHidden()
})

test('show Game Page when goto /game directly', async ({ page }) => {
  await page.goto('/game')
  await expect(page.getByText('Hello Game')).toBeVisible()
  await expect(page.getByText('Hello Blog')).toBeHidden()
})
