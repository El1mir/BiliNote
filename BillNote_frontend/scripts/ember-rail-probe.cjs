const { chromium } = require('playwright')
const EXE =
  'C:/Users/Administrator/AppData/Local/ms-playwright/chromium-1248/chrome-win64/chrome.exe'
;(async () => {
  const b = await chromium.launch({ executablePath: EXE, args: ['--no-sandbox'] })
  const p = await (await b.newContext({ viewport: { width: 1400, height: 900 } })).newPage()
  await p.goto('http://127.0.0.1:3015/', { waitUntil: 'domcontentloaded' })
  await p.waitForSelector('main', { timeout: 45000 })
  await p.waitForFunction(() => !document.querySelector('[data-boot-state]'), null, {
    timeout: 45000,
  })
  await p.waitForTimeout(3500)
  const info = await p.evaluate(() => {
    const rail = document.querySelector('[style*="--rail-w"]')
    const btns = rail
      ? Array.from(rail.querySelectorAll('button')).map(x => ({
          cls: x.className.slice(0, 60),
          disabled: x.disabled,
          text: x.textContent.trim().slice(0, 30),
        }))
      : []
    return {
      hasRail: !!rail,
      railClass: rail ? rail.className : null,
      buttonCount: btns.length,
      btns: btns.slice(0, 6),
      railText: rail ? rail.textContent.trim().slice(0, 200) : null,
    }
  })
  console.log(JSON.stringify(info, null, 1))
  await b.close()
})()
