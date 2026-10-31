const { chromium } = require('playwright')
const EXE =
  'C:/Users/Administrator/AppData/Local/ms-playwright/chromium-1248/chrome-win64/chrome.exe'
;(async () => {
  const b = await chromium.launch({ executablePath: EXE, args: ['--no-sandbox'] })
  const ctx = await b.newContext({ viewport: { width: 1440, height: 900 } })
  await ctx.addInitScript(loc => window.localStorage.setItem('bilinote-locale', loc), 'zh-CN')
  const p = await ctx.newPage()
  await p.goto('http://127.0.0.1:4174/', { waitUntil: 'domcontentloaded' })
  await p.waitForTimeout(9000)
  const info = await p.evaluate(() => ({
    mainCount: document.querySelectorAll('main').length,
    mainVisible: document.querySelector('main')
      ? document.querySelector('main').getBoundingClientRect().width
      : -1,
    tags: Array.from(document.querySelectorAll('#root > *')).map(
      x => x.tagName + '.' + (x.className || '').slice(0, 40)
    ),
  }))
  console.log(JSON.stringify(info))
  await b.close()
})()
