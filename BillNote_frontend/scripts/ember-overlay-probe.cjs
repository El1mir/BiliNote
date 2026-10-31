const { chromium } = require('playwright')
const EXE =
  'C:/Users/Administrator/AppData/Local/ms-playwright/chromium-1248/chrome-win64/chrome.exe'
;(async () => {
  const b = await chromium.launch({ executablePath: EXE, args: ['--no-sandbox'] })
  const p = await (await b.newContext({ viewport: { width: 1400, height: 900 } })).newPage()
  await p.goto('http://127.0.0.1:3015/', { waitUntil: 'domcontentloaded' })
  await p.waitForTimeout(4000)
  const msg = await p.evaluate(() => {
    const o = document.querySelector('vite-error-overlay')
    if (!o || !o.shadowRoot) return 'no-overlay'
    return o.shadowRoot.textContent.slice(0, 600)
  })
  console.log(msg)
  await b.close()
})()
