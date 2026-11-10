import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join, relative } from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'

const ROOT = fileURLToPath(new URL('../..', import.meta.url))
const TOKENS = join(ROOT, 'src/ember/tokens.css')

const SEMANTIC = [
  'canvas', 'surface', 'raised', 'ink', 'ink-soft', 'ink-muted',
  'line', 'accent', 'success', 'warning', 'danger', 'info',
]

type Vars = Record<string, string>

const HEX_VAR = /--([\w-]+):\s*(#[0-9a-fA-F]{6});/g

function block(css: string, selector: string): Vars {
  const start = css.indexOf(selector + ' {')
  expect(start, selector + ' block').toBeGreaterThanOrEqual(0)
  const end = css.indexOf('\n}', start)
  const vars: Vars = {}
  for (const match of css.slice(start, end).matchAll(HEX_VAR)) {
    vars[match[1]] = match[2]
  }
  return vars
}

function luminance(hex: string): number {
  const h = hex.replace('#', '')
  const channels = [0, 2, 4].map(i => parseInt(h.slice(i, i + 2), 16) / 255)
  const lin = channels.map(c => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4))
  return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]
}

function contrast(fg: string, bg: string): number {
  const a = luminance(fg)
  const b = luminance(bg)
  const hi = a > b ? a : b
  const lo = a > b ? b : a
  return (hi + 0.05) / (lo + 0.05)
}

const css = readFileSync(TOKENS, 'utf8')
const light = block(css, ':root')
const dark = block(css, '.dark')

const PAIRS: Array<[string, string, number]> = [
  ['ink', 'canvas', 4.5],
  ['ink', 'surface', 4.5],
  ['ink-soft', 'surface', 4.5],
  ['ink-muted', 'canvas', 4.5],
  ['on-accent', 'accent', 4.5],
  ['success', 'surface', 4.5],
  ['warning', 'surface', 4.5],
  ['danger', 'surface', 4.5],
  ['info', 'surface', 4.5],
  ['line-strong', 'surface', 3],
  ['accent', 'surface', 3],
]

function assertContrast(name: string, vars: Vars) {
  for (const pair of PAIRS) {
    const fg = vars[pair[0]]
    const bg = vars[pair[1]]
    expect(fg, name + ' ' + pair[0]).toBeTruthy()
    expect(bg, name + ' ' + pair[1]).toBeTruthy()
    expect(contrast(fg, bg), name + ' ' + pair[0] + ' on ' + pair[1]).toBeGreaterThanOrEqual(pair[2])
  }
}

describe('semantic tokens', () => {
  it('defines every semantic name in both themes', () => {
    for (const name of SEMANTIC) {
      expect(light[name], 'light ' + name).toMatch(/^#[0-9a-f]{6}$/i)
      expect(dark[name], 'dark ' + name).toMatch(/^#[0-9a-f]{6}$/i)
    }
  })

  it('keeps body text at WCAG AA and non-text UI at 3:1', () => {
    assertContrast('light', light)
    assertContrast('dark', dark)
  })
})

describe('component colour usage', () => {
  it('leaves no raw hex in src/ember except the Bilibili brand mark', () => {
    const offenders: string[] = []

    const walk = (dir: string) => {
      for (const entry of readdirSync(dir)) {
        const path = join(dir, entry)
        if (statSync(path).isDirectory()) {
          walk(path)
          continue
        }
        if (!path.endsWith('.tsx')) continue
        if (path.endsWith('BilibiliMark.tsx')) continue
        if (/#[0-9a-f]{3,6}/i.test(readFileSync(path, 'utf8'))) {
          offenders.push(relative(ROOT, path))
        }
      }
    }

    walk(join(ROOT, 'src/ember'))
    expect(offenders).toEqual([])
  })

  it('keeps terracotta and warm-neutral leftovers out of the src tree', () => {
    const banned = ['#c2410c', 'terracotta', 'playfair']
    const hits: string[] = []

    // W0 owns ui/ and shell/; features/ and pages/ are other work packages and
    // are scanned when those cards land.
    const scan = (path: string) => {
      if (statSync(path).isDirectory()) {
        for (const entry of readdirSync(path)) scan(join(path, entry))
        return
      }
      if (!path.endsWith('.tsx') && !path.endsWith('.ts') && !path.endsWith('.css')) return
      const text = readFileSync(path, 'utf8').toLowerCase()
      for (const needle of banned) {
        if (text.indexOf(needle) >= 0) hits.push(relative(ROOT, path) + ':' + needle)
      }
    }

    scan(join(ROOT, 'src/ember/ui'))
    scan(join(ROOT, 'src/ember/shell'))
    scan(join(ROOT, 'src/ember/tokens.css'))
    scan(join(ROOT, 'src/ember/motion.css'))
    expect(hits).toEqual([])
  })
})