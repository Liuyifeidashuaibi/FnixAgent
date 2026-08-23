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

const pos = (page, x, y) => {
  return page.locator(`.chess-pos-${x}-${y}`)
}

const drop = async (page, x, y) => {
  await pos(page, x, y).click()
}

test.setTimeout(5000)

test.beforeEach(async ({ page }) => {
  await page.goto('/game')
})

test('Save Chess Record', async ({ page }) => {
  await drop(page, 0, 0)
  await drop(page, 1, 0)
  await drop(page, 0, 1)
  await drop(page, 1, 1)
  await drop(page, 0, 2)
  await drop(page, 1, 2)
  await drop(page, 0, 3)
  await drop(page, 1, 3)
  await drop(page, 0, 4)

  await page.getByText('Post Game Records').click()

  // Jump back
  await expect(page).toHaveURL('/')

  await expect(page.locator('h1:has-text("Black is Winner!")')).toBeVisible()
  await expect(page.getByText('Black(0,0);')).toBeVisible()
  await expect(page.getByText('White(1,0);')).toBeVisible()
  await expect(page.getByText('Black(0,1);')).toBeVisible()
  await expect(page.getByText('White(1,1);')).toBeVisible()
  await expect(page.getByText('Black(0,2);')).toBeVisible()
  await expect(page.getByText('White(1,2);')).toBeVisible()
  await expect(page.getByText('Black(0,3);')).toBeVisible()
  await expect(page.getByText('White(1,3);')).toBeVisible()
  await expect(page.getByText('Black(0,4);')).toBeVisible()
})
