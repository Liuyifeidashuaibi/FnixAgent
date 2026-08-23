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

test('Show Big Toast After wins', async ({ page }) => {
  await drop(page, 0, 0)
  await drop(page, 1, 0)

  await drop(page, 0, 1)
  await drop(page, 1, 1)

  await drop(page, 0, 2)
  await drop(page, 1, 2)

  await drop(page, 0, 3)
  await drop(page, 1, 3)

  await drop(page, 0, 4)

  await expect(page.getByText('Black Wins!')).toBeVisible()
  const toast = page.getByText('Congratulations!')
  await expect(toast).toBeVisible()
  await expect(toast).toHaveCSS('font-size', '50px')
})

test('Turn Switched', async ({ page }) => {
  await expect(page.getByText("Black's Turn")).toBeVisible()
  await drop(page, 5, 5)
  await expect(page.getByText("White's Turn")).toBeVisible()
  await drop(page, 4, 4)
  await expect(page.getByText("Black's Turn")).toBeVisible()

  // Same Place can not be clicked
  await drop(page, 5, 5)
  await expect(page.getByText("Black's Turn")).toBeVisible()
  await drop(page, 4, 4)
  await expect(page.getByText("Black's Turn")).toBeVisible()

  await drop(page, 5, 4)
  await expect(page.getByText("White's Turn")).toBeVisible()
})

test('Play a complex game', async ({ page }) => {
  await drop(page, 4, 7)
  await drop(page, 4, 6)
  await drop(page, 3, 6)
  await drop(page, 3, 7)
  await drop(page, 2, 5)
  await drop(page, 5, 8)
  await drop(page, 1, 4)
  await drop(page, 0, 3)
  await drop(page, 3, 4)
  await drop(page, 5, 5)
  await drop(page, 6, 4)
  await drop(page, 2, 8)
  await drop(page, 1, 9)
  await drop(page, 4, 8)
  await drop(page, 3, 8)
  await drop(page, 5, 9)
  await drop(page, 2, 6)
  await drop(page, 5, 6)
  await drop(page, 5, 7)
  await drop(page, 6, 10)
  await drop(page, 7, 11)
  await drop(page, 2, 4)
  await drop(page, 4, 3)
  await drop(page, 5, 2)
  await drop(page, 1, 6)
  await drop(page, 0, 7)
  await drop(page, 3, 3)
  await drop(page, 3, 5)
  await drop(page, 5, 3)
  await drop(page, 6, 3)
  await drop(page, 2, 3)
  await drop(page, 1, 3)
  await drop(page, 0, 2)
  await drop(page, 7, 4)
  await drop(page, 8, 5)
  await drop(page, 4, 1)
  await drop(page, 3, 0)
  await drop(page, 6, 5)
  await drop(page, 3, 2)
  await drop(page, 3, 1)
  await drop(page, 4, 5)
  await drop(page, 8, 3)
  await drop(page, 9, 2)
  await drop(page, 5, 1)
  await drop(page, 2, 1)
  await drop(page, 5, 4)
  await drop(page, 8, 6)
  await drop(page, 6, 1)
  await drop(page, 7, 1)
  await drop(page, 7, 2)
  await drop(page, 9, 4)
  await drop(page, 9, 3)
  await drop(page, 10, 3)
  await drop(page, 7, 6)
  await drop(page, 11, 2)
  await drop(page, 12, 1)
  await drop(page, 10, 2)
  await drop(page, 8, 2)
  await drop(page, 12, 2)
  await drop(page, 13, 2)
  await drop(page, 10, 4)
  await drop(page, 10, 1)
  await drop(page, 10, 5)
  await drop(page, 10, 6)
  await drop(page, 11, 4)
  await drop(page, 8, 4)
  await drop(page, 12, 4)
  await drop(page, 13, 4)
  await drop(page, 11, 3)
  await drop(page, 11, 1)
  await drop(page, 9, 5)

  await expect(page.getByText('Black Wins!')).toBeVisible()
})
