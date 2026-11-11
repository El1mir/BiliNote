import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'

// The extension mirrors BillNote_frontend/src/ember/tokens.css by hand (no
// shared package), so the numbers are pinned here: a rename or a palette edit
// that forgets one side would otherwise drift silently.
const SRC = join(__dirname, '..')
const TOKENS = readFileSync(join(SRC, 'styles/tokens.css'), 'utf8')

function sourceFiles(dir: string): string[] {
  return readdirSync(dir).flatMap((entry) => {
    const path = join(dir, entry)
    if (statSync(path).isDirectory()) return sourceFiles(path)
    return /\.(vue|ts|css)$/.test(entry) && !path.endsWith('tokens.css') && !path.includes('__tests__') ? [path] : []
  })
}

describe('extension design tokens', () => {
  it('uses the 021 canonical names, not the legacy ones', () => {
    expect(TOKENS).toContain('--accent:')
    expect(TOKENS).toContain('--ink-muted:')
    expect(TOKENS).not.toContain('--primary:')
    expect(TOKENS).not.toMatch(/--ink-mute:/)
  })

  it('defines the full palette in both themes', () => {
    const light = TOKENS.slice(0, TOKENS.indexOf('.dark {'))
    const dark = TOKENS.slice(TOKENS.indexOf('.dark {'), TOKENS.indexOf('@media'))
    const names = (css: string) => [...css.matchAll(/--([a-z-]+):/g)].map(m => m[1])
    const lightNames = new Set(names(light))
    // .dark redefines colours only; every name it sets must already exist in :root.
    for (const name of names(dark)) expect(lightNames.has(name)).toBe(true)
    for (const core of ['canvas', 'surface', 'raised', 'ink', 'ink-soft', 'ink-muted', 'line', 'line-strong', 'accent', 'accent-soft', 'on-accent', 'success', 'warning', 'danger', 'info']) {
      expect(lightNames.has(core)).toBe(true)
      expect(names(dark)).toContain(core)
    }
    expect(light).toContain('#f4f6f7')
    expect(dark).toContain('#111719')
  })

  it('keeps the shared motion ladder', () => {
    expect(TOKENS).toMatch(/--dur-press:\s*120ms/)
    expect(TOKENS).toMatch(/--dur-hover:\s*160ms/)
    expect(TOKENS).toMatch(/--dur-popover:\s*180ms/)
    expect(TOKENS).toMatch(/--dur-menu:\s*200ms/)
    expect(TOKENS).toMatch(/--dur-panel:\s*260ms/)
    expect(TOKENS).toMatch(/--dur-page:\s*300ms/)
  })

  it('has no hardcoded colour outside tokens.css', () => {
    const offenders = sourceFiles(SRC).filter(file => /#[0-9a-f]{6}\b/i.test(readFileSync(file, 'utf8')))
    expect(offenders).toEqual([])
  })

  it('gives touch pointers 44px targets', () => {
    expect(TOKENS).toMatch(/@media \(pointer: coarse\)/)
    expect(TOKENS).toMatch(/min-height:\s*2\.75rem/)
  })
})
