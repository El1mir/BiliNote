const { chromium } = require('playwright')
const EXE =
  'C:/Users/Administrator/AppData/Local/ms-playwright/chromium-1248/chrome-win64/chrome.exe'
;(async () => {
  const b = await chromium.launch({ executablePath: EXE, args: ['--no-sandbox'] })
  const p = await (await b.newContext({ viewport: { width: 1400, height: 900 } })).newPage()
  const reqs = []
  p.on('request', r => {
    if (r.url().includes('task_list')) reqs.push(Date.now() + ' REQ')
  })
  p.on('response', r => {
    if (r.url().includes('task_list')) reqs.push(Date.now() + ' RES ' + r.status())
  })
  await p.goto('http://127.0.0.1:3015/', { waitUntil: 'domcontentloaded' })
  await p.waitForSelector('main', { timeout: 45000 })
  await p.waitForTimeout(5000)
  const info = await p.evaluate(() => {
    const rail = document.querySelector('[style*="--rail-w"]')
    const key = Object.keys(rail).find(k => k.startsWith('__reactFiber$'))
    let f = rail[key]
    const chain = []
    let target = null
    const walk = (node, depth) => {
      if (!node || depth > 6 || target) return
      const name = (node.type && (node.type.name || node.type.displayName)) || null
      if (name === 'TaskList') {
        target = node
        return
      }
      walk(node.child, depth + 1)
      walk(node.sibling, depth)
    }
    walk(f.child, 0)
    let hooks = []
    if (target) {
      let h = target.memoizedState
      let i = 0
      while (h && i < 14) {
        const v = h.memoizedState
        hooks.push({
          i,
          type: typeof v,
          isArray: Array.isArray(v),
          len: Array.isArray(v)
            ? v.length
            : v && typeof v === 'object'
              ? Object.keys(v).slice(0, 4).join(',')
              : String(v).slice(0, 20),
        })
        h = h.next
        i += 1
      }
    }
    return { foundTaskList: !!target, hooks }
  })
  console.log(JSON.stringify({ reqs, info }, null, 1))
  await b.close()
})()
