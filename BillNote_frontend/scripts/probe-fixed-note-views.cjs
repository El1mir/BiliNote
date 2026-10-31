#!/usr/bin/env node
/** Viewport-sized shots of the reader with the regenerated inline screenshots. */
const { chromium } = require('playwright');
const fs = require('node:fs');
const EXE = 'C:/Users/Administrator/AppData/Local/ms-playwright/chromium-1248/chrome-win64/chrome.exe';
const OUT = 'C:/Users/Administrator/Downloads';
(async () => {
  const browser = await chromium.launch({ executablePath: EXE, args: ['--no-sandbox'] })
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, locale: 'zh-CN', deviceScaleFactor: 1 })
  const page = await ctx.newPage()
  await page.goto('http://127.0.0.1:3015/', { waitUntil: 'domcontentloaded' })
  await page.waitForFunction(() => !document.querySelector('[data-boot-state]'), { timeout: 30000 })
  await page.waitForTimeout(2000)
  await page.locator('main button', { hasText: '需求和架构' }).first().click()
  await page.waitForTimeout(3500)
  const noteTab = page.locator('[role=tab]', { hasText: '笔记' }).first()
  if (await noteTab.count()) { await noteTab.click(); await page.waitForTimeout(1500) }
  const img = page.locator('main img').first()
  await img.scrollIntoViewIfNeeded()
  await page.waitForTimeout(2000)
  await page.screenshot({ path: OUT + '/reader-fixed-viewport.png' })
  await img.click()
  await page.waitForTimeout(1500)
  await page.screenshot({ path: OUT + '/reader-fixed-zoom-viewport.png' })
  await page.keyboard.press('Escape')
  await page.waitForTimeout(600)
  // 再滚到第二张图，确认不是只有第一张能出
  const imgs = page.locator('main img')
  const n = await imgs.count()
  if (n > 1) { await imgs.nth(1).scrollIntoViewIfNeeded(); await page.waitForTimeout(2000); await page.screenshot({ path: OUT + '/reader-fixed-viewport-2.png' }) }
  console.log(JSON.stringify({ images: n }))
  await browser.close()
})().catch(e => { console.error('FAILED', e); process.exit(1) })
