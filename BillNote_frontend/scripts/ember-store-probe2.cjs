const { chromium } = require('playwright')
const EXE =
  'C:/Users/Administrator/AppData/Local/ms-playwright/chromium-1248/chrome-win64/chrome.exe'
;(async () => {
  const b = await chromium.launch({ executablePath: EXE, args: ['--no-sandbox'] })
  const p = await (await b.newContext({ viewport: { width: 1400, height: 900 } })).newPage()
  await p.goto('http://127.0.0.1:3015/', { waitUntil: 'domcontentloaded' })
  await p.waitForSelector('main', { timeout: 45000 })
  await p.waitForTimeout(5000)
  const r1 = await p.evaluate(async () => {
    const mod = await import('/src/store/taskStore/index.ts')
    window.__s = mod.useTaskStore
    window.__log = []
    window.__s.subscribe(st => window.__log.push(st.tasks.length))
    return { before: window.__s.getState().tasks.length }
  })
  await p.evaluate(async () => {
    await window.__s.getState().loadTasks()
  })
  await p.waitForTimeout(1500)
  const r2 = await p.evaluate(() => ({
    after: window.__s.getState().tasks.length,
    log: window.__log.slice(-6),
  }))
  const rail = await p.locator('[style*="--rail-w"]').innerText()
  console.log(
    JSON.stringify(
      {
        r1,
        r2,
        railEmpty: rail.includes('还没有历史记录'),
        railHead: rail.split('\n').slice(0, 8),
      },
      null,
      1
    )
  )
  await b.close()
})()
