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
  const out = { errors: errs }
  // 1. language toggle (sidebar button) must actually switch locale
  const langBtn = p.locator('aside button').first()
  const before = await p.evaluate(() => document.documentElement.lang)
  await langBtn.click()
  await p.waitForTimeout(700)
  out.langBefore = before
  out.langAfter = await p.evaluate(() => document.documentElement.lang)
  out.headingAfter = await p.locator('main h1').first().innerText()
  await langBtn.click()
  await p.waitForTimeout(700)
  out.langBack = await p.evaluate(() => document.documentElement.lang)
  console.log(
    'LANG ' +
      JSON.stringify({
        before: out.langBefore,
        after: out.langAfter,
        heading: out.headingAfter,
        back: out.langBack,
      })
  )
  // 2. open the first task from the history rail
  const card = p.locator('[style*="--rail-w"] button.group').first()
  await card.click({ timeout: 20000 })
  await p.waitForTimeout(3000)
  const info = await p.evaluate(() => {
    const heads = Array.from(
      document.querySelectorAll('.ember-markdown h2[id], .ember-markdown h3[id]')
    ).map(h => ({ id: h.id, text: h.textContent.trim().slice(0, 40) }))
    const links = Array.from(document.querySelectorAll('nav a[href^="#"]')).map(a =>
      a.getAttribute('href').slice(1)
    )
    return {
      headingCount: heads.length,
      linkCount: links.length,
      missing: links.filter(id => !document.getElementById(id)),
      sampleHeads: heads.slice(0, 5),
      sampleLinks: links.slice(0, 5),
    }
  })
  Object.assign(out, info)
  if (info.linkCount > 1) {
    const y0 = await p.evaluate(() => window.scrollY)
    await p.locator('nav a[href^="#"]').nth(1).click()
    await p.waitForTimeout(700)
    out.scrollDelta = (await p.evaluate(() => window.scrollY)) - y0
  }
  out.errors = errs
  console.log(JSON.stringify(out, null, 1))
  await b.close()
})()
