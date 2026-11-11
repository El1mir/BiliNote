// W0 contrast audit. Reads the shipped tokens.css so the numbers can never
// drift from what the app actually paints, and fails loudly (exit 1) when a
// pair drops below its WCAG threshold.
//
//   node docs/ui-audit/021/contrast-audit.mjs
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, resolve } from 'node:path'
import { contrast, parseThemes } from './contrast-lib.mjs'

const here = dirname(fileURLToPath(import.meta.url))
const css = readFileSync(resolve(here, '../../../BillNote_frontend/src/ember/tokens.css'), 'utf8')
const { light, dark } = parseThemes(css)

const PAIRS = [
  ['ink', 'canvas', 4.5, 'body text on the page'],
  ['ink', 'surface', 4.5, 'body text on a card'],
  ['ink', 'raised', 4.5, 'body text on a raised panel'],
  ['ink-soft', 'surface', 4.5, 'secondary text'],
  ['ink-muted', 'canvas', 4.5, 'muted helper text'],
  ['ink', 'accent-soft', 4.5, 'current nav item text'],
  ['on-accent', 'accent', 4.5, 'label on a solid accent button'],
  ['success', 'surface', 4.5, 'success text'],
  ['warning', 'surface', 4.5, 'warning text'],
  ['danger', 'surface', 4.5, 'error text'],
  ['info', 'surface', 4.5, 'info text'],
  ['line-strong', 'surface', 3, 'control border (non-text)'],
  ['accent', 'surface', 3, 'focus ring / accent marks (non-text)'],
]

let failures = 0
const lines = []
for (const [name, theme] of [['light', light], ['dark', dark]]) {
  lines.push(`\n## ${name}`)
  lines.push('| pair | ratio | required | verdict | role |')
  lines.push('|---|---|---|---|---|')
  for (const [fg, bg, min, role] of PAIRS) {
    const fgv = theme[fg]
    const bgv = theme[bg]
    if (!fgv || !bgv || !fgv.startsWith('#') || !bgv.startsWith('#')) {
      lines.push(`| ${fg} on ${bg} | — | ${min} | MISSING | ${role} |`)
      failures++
      continue
    }
    const ratio = contrast(fgv, bgv)
    const ok = ratio >= min
    if (!ok) failures++
    lines.push(`| ${fg} on ${bg} | ${ratio.toFixed(2)}:1 | ${min}:1 | ${ok ? 'PASS' : 'FAIL'} | ${role} |`)
  }
}

lines.push(`\nResult: ${failures === 0 ? 'all pairs pass' : failures + ' failing pairs'}`)
console.log(lines.join('\n'))
process.exit(failures === 0 ? 0 : 1)