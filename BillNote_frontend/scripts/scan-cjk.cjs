const fs = require('fs'),
  path = require('path')
const root = 'src/ember'
const cjk = /[\u4e00-\u9fff]/
const out = []
function walk(d) {
  for (const e of fs.readdirSync(d, { withFileTypes: true })) {
    const p = path.join(d, e.name)
    if (e.isDirectory()) walk(p)
    else if (/\.(ts|tsx)$/.test(e.name)) {
      if (p.includes('i18n' + path.sep + 'strings.ts')) continue
      const lines = fs.readFileSync(p, 'utf8').split(/\r?\n/)
      lines.forEach((l, i) => {
        if (cjk.test(l)) out.push(p + ':' + (i + 1) + ': ' + l.trim().slice(0, 120))
      })
    }
  }
}
walk(root)
console.log(JSON.stringify({ count: out.length, items: out.slice(0, 60) }, null, 1))
