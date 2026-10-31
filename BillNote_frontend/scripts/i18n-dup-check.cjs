const fs = require('fs')
const p = 'src/ember/i18n/strings.ts'
const lines = fs.readFileSync(p, 'utf8').split(/\r?\n/)
// find the two top-level dictionaries: zhCN and enUS
const marks = []
lines.forEach((l, i) => {
  if (/^export const (zhCN|enUS)\b/.test(l)) marks.push([i + 1, l.trim().slice(0, 40)])
})
console.log('DICT MARKERS', JSON.stringify(marks))
const seen = new Map()
const dups = []
let dict = null
lines.forEach((l, i) => {
  const m = /^export const (zhCN|enUS)\b/.exec(l)
  if (m) {
    dict = m[1]
    seen.set(dict, new Map())
    return
  }
  if (/^}/.test(l)) {
    dict = null
    return
  }
  if (!dict) return
  const k = /^  '?([A-Za-z0-9_.]+)'?:/.exec(l)
  if (!k) return
  const map = seen.get(dict)
  if (map.has(k[1])) dups.push({ dict, key: k[1], first: map.get(k[1]), again: i + 1 })
  else map.set(k[1], i + 1)
})
console.log('DUP_COUNT', dups.length)
console.log(JSON.stringify(dups.slice(0, 6)))
console.log(JSON.stringify(dups.slice(-4)))
const byDict = {}
dups.forEach(d => {
  byDict[d.dict] = (byDict[d.dict] || 0) + 1
})
console.log('BY_DICT', JSON.stringify(byDict))
