const { chromium } = require('playwright')
const EXE =
  'C:/Users/Administrator/AppData/Local/ms-playwright/chromium-1248/chrome-win64/chrome.exe'
;(async () => {
  const b = await chromium.launch({ executablePath: EXE, args: ['--no-sandbox'] })
  const ctx = await b.newContext({ viewport: { width: 1440, height: 900 } })
  const p = await ctx.newPage()
  const errs = []
  p.on('pageerror', e => errs.push('PAGEERROR ' + String(e).slice(0, 300)))
  p.on('console', m => {
    if (m.type() === 'error') errs.push('CONSOLE ' + m.text().slice(0, 300))
  })
  const resp = []
  p.on('response', r => {
    if (r.status() >= 400) resp.push(r.status() + ' ' + r.url())
  })
  await p.goto('http://127.0.0.1:4174/', { waitUntil: 'domcontentloaded' })
  await p.waitForTimeout(8000)
  const state = await p.evaluate(() => ({
    boot: document.querySelector('[data-boot-state]')
      ? document.querySelector('[data-boot-state]').getAttribute('data-boot-state')
      : null,
    rootLen: document.getElementById('root')
      ? document.getElementById('root').innerHTML.length
      : -1,
    bodyText: document.body.innerText.replace(/\n+/g, ' | ').slice(0, 400),
    apiBase: window.__VITE_API_BASE__ || null,
  }))
  console.log(JSON.stringify({ state, errs, resp }, null, 1))
  await b.close()
})()
