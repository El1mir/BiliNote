import { describe, expect, it } from 'vitest'
import { nextTheme, resolveTheme, type Theme } from '@/ember/theme/theme'

/**
 * spec 021 / W0: the theme preference has three states but only two paints.
 * The pure resolution is the part worth pinning — a wrong resolution flashes
 * the opposite palette on load, and 'system' silently stops following the OS.
 */
describe('theme resolution', () => {
  it('paints explicit choices regardless of the OS', () => {
    expect(resolveTheme('light', true)).toBe('light')
    expect(resolveTheme('light', false)).toBe('light')
    expect(resolveTheme('dark', true)).toBe('dark')
    expect(resolveTheme('dark', false)).toBe('dark')
  })

  it('follows the OS when the preference is system', () => {
    expect(resolveTheme('system', true)).toBe('dark')
    expect(resolveTheme('system', false)).toBe('light')
  })

  it('cycles light to dark to system and back', () => {
    const seen: Theme[] = ['light']
    for (let i = 0; i < 3; i++) seen.push(nextTheme(seen[seen.length - 1]))
    expect(seen).toEqual(['light', 'dark', 'system', 'light'])
  })
})