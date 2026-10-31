const { chromium } = require('playwright')
const EXE =
  'C:/Users/Administrator/AppData/Local/ms-playwright/chromium-1248/chrome-win64/chrome.exe'
;(async () => {
  const b = await chromium.launch({ executablePath: EXE, args: ['--no-sandbox'] })
  const ctx = await b.newContext({ viewport: { width: 1600, height: 1000 } })
  const p = await ctx.newPage()
  const errs = []
  p.on('pageerror', e => errs.push(String(e)))
  await p.goto('http://127.0.0.1:3015/', { waitUntil: 'domcontentloaded' })
  await p.waitForSelector('main', { timeout: 45000 })
  await p.waitForFunction(() => !document.querySelector('[data-boot-state]'), null, {
    timeout: 45000,
  })
  await p.waitForTimeout(1200)
  const card = p.locator('[style*="--rail-w"] button').first()
  await card.click({ timeout: 20000 })
  await p.waitForTimeout(2500)
  const info = await p.evaluate(() => {
    const heads = Array.from(
      document.querySelectorAll('.ember-markdown h2[id], .ember-markdown h3[id]')
    ).map(h => ({ id: h.id, text: h.textContent.trim().slice(0, 40) }))
    const links = Array.from(document.querySelectorAll('nav a[href^="#"]')).map(a =>
      a.getAttribute('href').slice(1)
    )
    const missing = links.filter(id => !document.getElementById(id))
    return {
      headingCount: heads.length,
      linkCount: links.length,
      missing,
      sampleHeads: heads.slice(0, 6),
      sampleLinks: links.slice(0, 6),
    }
  })
  if (info.linkCount) {
    const before = await p.evaluate(() => window.scrollY)
    await p.locator('nav a[href^="#"]').nth(1).click()
    info.clickedAnchor = true
    await p.waitForTimeout(600)
    const after = await p.evaluate(() => window.scrollY)
    info.scrollDelta = after - before
  }
  info.errors = errs
  console.log(JSON.stringify(info, null, 1))
  await b.close()
})()
