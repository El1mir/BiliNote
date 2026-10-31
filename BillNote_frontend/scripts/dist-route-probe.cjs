const { chromium } = require('playwright')
const EXE =
  'C:/Users/Administrator/AppData/Local/ms-playwright/chromium-1248/chrome-win64/chrome.exe'
;(async () => {
  const b = await chromium.launch({ executablePath: EXE, args: ['--no-sandbox'] })
  for (const route of ['/', '/settings/general', '/settings/model']) {
    const ctx = await b.newContext({ viewport: { width: 1440, height: 900 } })
    const p = await ctx.newPage()
    const bad = []
    p.on('response', r => {
      if (r.status() >= 400 || r.url().includes('/assets/'))
        bad.push(r.status() + ' ' + r.url().replace('http://127.0.0.1:4174', ''))
    })
    await p.goto('http://127.0.0.1:4174' + route, { waitUntil: 'domcontentloaded' })
    await p.waitForTimeout(6000)
    const mainCount = await p.evaluate(() => document.querySelectorAll('main').length)
    console.log(JSON.stringify({ route, mainCount, assetResp: bad.slice(0, 6) }))
    await ctx.close()
  }
  await b.close()
})()
