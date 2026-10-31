const { chromium } = require('playwright')
const EXE =
  'C:/Users/Administrator/AppData/Local/ms-playwright/chromium-1248/chrome-win64/chrome.exe'
;(async () => {
  const b = await chromium.launch({ executablePath: EXE, args: ['--no-sandbox'] })
  const p = await (await b.newContext({ viewport: { width: 1400, height: 900 } })).newPage()
  await p.goto('http://127.0.0.1:3015/', { waitUntil: 'domcontentloaded' })
  await p.waitForSelector('main', { timeout: 45000 })
  await p.waitForTimeout(5000)
  const out = await p.evaluate(async () => {
    const res = performance.getEntriesByType('resource').map(e => e.name)
    const noteUrls = res.filter(n => n.includes('/src/services/note.ts'))
    const storeUrls = res.filter(n => n.includes('/src/store/taskStore/'))
    const zustandUrls = res.filter(n => n.includes('zustand'))
    const reactUrls = res.filter(n => /\/react\/|react-dom/.test(n))
    const noteUrl = noteUrls[0]
    const storeUrl = storeUrls[0]
    const noteMod = await import(noteUrl)
    const storeMod = await import(storeUrl)
    const before = storeMod.useTaskStore.getState().tasks.length
    const payload = await noteMod.listTasks()
    const keys = payload && typeof payload === 'object' ? Object.keys(payload) : String(payload)
    const rowCount = payload && payload.tasks ? payload.tasks.length : -1
    await storeMod.useTaskStore.getState().loadTasks()
    const after = storeMod.useTaskStore.getState().tasks.length
    return {
      noteUrls,
      storeUrls,
      zustandCount: zustandUrls.length,
      reactCount: reactUrls.length,
      before,
      keys,
      rowCount,
      after,
    }
  })
  await p.waitForTimeout(1200)
  out.railText = (await p.locator('[style*="--rail-w"]').innerText()).split('\n').slice(0, 9)
  console.log(JSON.stringify(out, null, 1))
  await b.close()
})()
