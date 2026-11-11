import { expect, test } from './fixtures'

// 扩展三面（spec 017 重写后的真实 UI）——原 vitesse-webext 模板断言
// （Vitesse WebExt h1 / Open Options / extension icon）已随模板 UI 一起删除。
test('popup page', async ({ page, extensionId }) => {
  await page.goto(`chrome-extension://${extensionId}/dist/popup/index.html`)

  await expect(page.getByRole('button', { name: '生成笔记' })).toBeVisible()
})

test('options page', async ({ page, extensionId }) => {
  await page.goto(`chrome-extension://${extensionId}/dist/options/index.html`)

  await expect(page.getByRole('heading', { name: '后端地址' })).toBeVisible()
  await expect(page.getByRole('button', { name: '模型供应商' })).toBeVisible()
})
