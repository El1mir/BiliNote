const { chromium } = require('playwright')
const EXE =
  'C:/Users/Administrator/AppData/Local/ms-playwright/chromium-1248/chrome-win64/chrome.exe'
;(async () => {
  const b = await chromium.launch({ executablePath: EXE, args: ['--no-sandbox'] })
  const ctx = await b.newContext({ viewport: { width: 390, height: 844 } })
  const p = await ctx.newPage()
  await p.goto('http://127.0.0.1:3015/settings/model', { waitUntil: 'domcontentloaded' })
  await p.waitForSelector('main', { timeout: 45000 })
  await p.waitForFunction(() => !document.querySelector('[data-boot-state]'), null, {
    timeout: 45000,
  })
  await p.waitForTimeout(800)
  const info = await p.evaluate(() => {
    const links = Array.from(document.querySelectorAll('a[href^="/settings/"]'))
    const strip = links[0] ? links[0].parentElement : null
    return {
      order: links.map(a => a.getAttribute('href') + '=' + a.textContent.trim()),
      stripScrollLeft: strip ? strip.scrollLeft : -1,
      stripScrollWidth: strip ? strip.scrollWidth : -1,
      stripClientWidth: strip ? strip.clientWidth : -1,
      activeVisible: (() => {
        const act = document.querySelector('a[aria-current="page"]')
        if (!act) return 'no-active'
        const r = act.getBoundingClientRect()
        return [Math.round(r.left), Math.round(r.right), window.innerWidth].join(',')
      })(),
    }
  })
  await p.screenshot({ path: 'C:/Users/Administrator/Downloads/focus-nav-probe.png' })
  const rects = await p.evaluate(() =>
    Array.from(document.querySelectorAll('a[href^="/settings/"]'))
      .slice(0, 4)
      .map(a => {
        const r = a.getBoundingClientRect()
        return a.textContent.trim() + '@' + Math.round(r.left) + '-' + Math.round(r.right)
      })
  )
  console.log(JSON.stringify({ ...info, rects }, null, 1))
  await b.close()
})()
