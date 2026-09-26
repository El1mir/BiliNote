import { describe, expect, it } from 'vitest'
import { toPercent } from '@/utils/progress'

describe('toPercent', () => {
  it('keeps backend 0-100 percentages as-is', () => {
    expect(toPercent(0)).toBe(0)
    expect(toPercent(40)).toBe(40)
    expect(toPercent(100)).toBe(100)
  })

  it('clamps out-of-range values instead of multiplying them', () => {
    expect(toPercent(120)).toBe(100)
    expect(toPercent(-5)).toBe(0)
  })

  it('returns null for missing or non-numeric progress', () => {
    expect(toPercent(null)).toBeNull()
    expect(toPercent(undefined)).toBeNull()
    expect(toPercent(Number.NaN)).toBeNull()
    expect(toPercent('40' as unknown)).toBeNull()
  })
})
