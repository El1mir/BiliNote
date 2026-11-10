import { describe, expect, it } from 'vitest'
import { scopeExpiredOnly } from '../../src/ember/pages/settings/cleanupScopes'

/**
 * T-062 / 上游 UI 计划 §5：清理的预演与执行必须同口径。
 *
 * 改之前 previewMediaCleanup(RESOURCE_TYPES, true) 写死"只算到期"，
 * 而"强制清理全部"走 expired_only=false —— 预演 12 项、实删 300 项。
 * 现在两者都从同一个作用域取值，这里锁的就是"预览与执行不可能分叉"。
 */

describe('清理作用域', () => {
  it('maps each scope to exactly one expired_only value', () => {
    expect(scopeExpiredOnly('expired')).toBe(true)
    expect(scopeExpiredOnly('all')).toBe(false)
  })

  it('is total: every scope has a defined boolean, never undefined', () => {
    // undefined 会被 axios 序列化成 "expired_only="，后端按 false 处理 —— 静默变成"删全部"。
    for (const scope of ['expired', 'all'] as const) {
      expect(typeof scopeExpiredOnly(scope)).toBe('boolean')
    }
  })
})
