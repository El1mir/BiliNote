const { chromium } = require('playwright')
const EXE =
  'C:/Users/Administrator/AppData/Local/ms-playwright/chromium-1248/chrome-win64/chrome.exe'
;(async () => {
  const b = await chromium.launch({ executablePath: EXE, args: ['--no-sandbox'] })
  const p = await (await b.newContext({ viewport: { width: 1400, height: 900 } })).newPage()
  const net = []
  const bodies = []
  p.on('response', async r => {
    if (r.url().includes('/api/')) {
      net.push(r.status() + ' ' + r.url().replace('http://127.0.0.1:3015', ''))
      if (r.url().includes('task_list')) {
        try {
          const t = await r.text()
          bodies.push(t.slice(0, 300))
        } catch (e) {}
      }
    }
  })
  const errs = []
  p.on('pageerror', e => errs.push('PAGEERROR ' + String(e).slice(0, 200)))
  p.on('console', m => {
    if (m.type() === 'warning' || m.type() === 'error')
      errs.push(m.type() + ': ' + m.text().slice(0, 300))
  })
  await p.goto('http://127.0.0.1:3015/', { waitUntil: 'domcontentloaded' })
  await p.waitForSelector('main', { timeout: 45000 })
  await p.waitForTimeout(5000)
  console.log(
    JSON.stringify(
      { net, errs, bodies, railText: await p.locator('[style*="--rail-w"]').innerText() },
      null,
      1
    )
  )
  await b.close()
})()
