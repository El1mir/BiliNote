/**
 * Deduplicate the flat i18n dictionaries.
 *
 * Why this exists: a duplicated key is a silent bug in JavaScript — the LAST
 * assignment wins, so the file a reviewer reads is not the dictionary the app
 * uses. TypeScript flags it (TS1117) but only under `tsc -b`, and the runtime
 * contract script cannot see it at all because the object literal has already
 * collapsed. This removes later duplicates and refuses to touch a key whose
 * duplicate value differs from the first, because that would change copy.
 */
const fs = require('fs')
const path = require('path')

const FILE = path.join(__dirname, '..', 'src', 'ember', 'i18n', 'strings.ts')
const APPLY = process.argv.includes('--apply')

const lines = fs.readFileSync(FILE, 'utf8').split(/\r?\n/)

// Dictionary boundaries: `const zhCN = {` … `} as const` and `const enUS: Dictionary = {` … `}`.
const starts = []
lines.forEach((l, i) => {
  if (/^const (zhCN|enUS)\b/.test(l)) starts.push(i)
})
if (starts.length !== 2) throw new Error('expected 2 dictionaries, found ' + starts.length)

const drop = new Set()
const conflicts = []
const removed = []

for (let s = 0; s < starts.length; s += 1) {
  const from = starts[s] + 1
  let to = from
  while (to < lines.length && !/^\}/.test(lines[to])) to += 1
  const seen = new Map()
  for (let i = from; i < to; i += 1) {
    const m = /^  '([^']+)':\s*(.*?),?$/.exec(lines[i])
    if (!m) continue
    const [, key, value] = m
    if (seen.has(key)) {
      if (seen.get(key).value !== value) {
        conflicts.push({ line: i + 1, key, first: seen.get(key).value, again: value })
      }
      drop.add(i)
      removed.push({ line: i + 1, key })
    } else {
      seen.set(key, { line: i + 1, value })
    }
  }
}

console.log(
  JSON.stringify(
    {
      duplicates: drop.size,
      conflictingValues: conflicts.length,
      sampleRemoved: removed.slice(0, 5),
      conflicts: conflicts.slice(0, 5),
    },
    null,
    1
  )
)

if (conflicts.length) {
  console.log(
    'REFUSING: a duplicate has a DIFFERENT value; that is a copy decision, not a cleanup.'
  )
  process.exit(2)
}

if (!APPLY) {
  console.log('dry run — pass --apply to write')
  process.exit(0)
}

const kept = lines.filter((_, i) => !drop.has(i))
fs.writeFileSync(FILE, kept.join('\n'))
console.log('wrote ' + kept.length + ' lines (removed ' + drop.size + ')')
