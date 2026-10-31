const { chromium } = require('playwright')
const EXE =
  'C:/Users/Administrator/AppData/Local/ms-playwright/chromium-1248/chrome-win64/chrome.exe'
;(async () => {
  const b = await chromium.launch({ executablePath: EXE, args: ['--no-sandbox'] })
  const p = await (await b.newContext({ viewport: { width: 1400, height: 900 } })).newPage()
  await p.goto('http://127.0.0.1:3015/', { waitUntil: 'domcontentloaded' })
  await p.waitForSelector('main', { timeout: 45000 })
  await p.waitForTimeout(4000)
  const info = await p.evaluate(async () => {
    const mod = await import('/src/store/taskStore/index.ts')
    const st = mod.useTaskStore.getState()
    const direct = await (await fetch('/api/task_list')).json()
    return {
      storeTaskCount: st.tasks.length,
      storeIds: st.tasks.slice(0, 3).map(x => x.id),
      currentTaskId: st.currentTaskId,
      backendCount: direct && direct.data && direct.data.tasks ? direct.data.tasks.length : -1,
      hasLoadTasks: typeof st.loadTasks,
    }
  })
  console.log(JSON.stringify(info, null, 1))
  const after = await p.evaluate(async () => {
    const mod = await import('/src/store/taskStore/index.ts')
    await mod.useTaskStore.getState().loadTasks()
    return {
      storeTaskCount: mod.useTaskStore.getState().tasks.length,
      ids: mod.useTaskStore
        .getState()
        .tasks.slice(0, 3)
        .map(x => x.id),
    }
  })
  console.log('AFTER_MANUAL_LOAD ' + JSON.stringify(after))
  await p.waitForTimeout(1500)
  console.log('RAIL ' + (await p.locator('[style*="--rail-w"]').innerText()).replace(/\n/g, ' | '))
  await b.close()
})()
