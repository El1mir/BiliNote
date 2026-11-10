import { beforeEach, describe, expect, it, vi } from 'vitest'
import {
  clearDraft,
  draftKeys,
  hasDraft,
  readDraft,
  resetDrafts,
  subscribeDrafts,
  writeDraft,
} from '../../src/ember/pages/settings/drafts'

/**
 * T-062 / 上游 UI 计划 §5："切换分区再切回，未保存草稿仍在"。
 *
 * 分区组件会被路由卸载，草稿必须活在组件之外。这里锁的是仓库本身的语义：
 * 写入后可读、清除后彻底消失（"有没有未保存改动"只由 key 是否存在判断）、
 * 以及订阅者能被通知（导航角标要重渲染）。
 */

beforeEach(() => {
  resetDrafts()
})

describe('settings drafts store', () => {
  it('keeps a draft after the section component is gone', () => {
    writeDraft('general', { max_parallel_notes: 4 })
    // 卸载 = 组件不再引用它，仓库里的值不受影响
    expect(readDraft<{ max_parallel_notes: number }>('general')).toEqual({ max_parallel_notes: 4 })
    expect(hasDraft('general')).toBe(true)
  })

  it('treats a saved section as having no draft', () => {
    writeDraft('prompt', 'edited template')
    clearDraft('prompt')
    expect(readDraft('prompt')).toBeUndefined()
    expect(hasDraft('prompt')).toBe(false)
    expect(draftKeys()).toEqual([])
  })

  it('clears on undefined, so one predicate answers "is this section dirty"', () => {
    writeDraft('media', { days: 3 })
    writeDraft('media', undefined)
    expect(hasDraft('media')).toBe(false)
  })

  it('notifies subscribers only when the draft set actually changes', () => {
    const seen = vi.fn()
    const unsubscribe = subscribeDrafts(seen)
    writeDraft('ocr', { enabled: true })
    expect(seen).toHaveBeenCalledTimes(1)
    clearDraft('ocr')
    expect(seen).toHaveBeenCalledTimes(2)
    // 清除一个不存在的 key 不该引起重渲染
    clearDraft('ocr')
    expect(seen).toHaveBeenCalledTimes(2)
    unsubscribe()
    writeDraft('general', {})
    expect(seen).toHaveBeenCalledTimes(2)
  })

  it('tracks drafts per section independently', () => {
    writeDraft('general', { a: 1 })
    writeDraft('prompt', 'x')
    expect(draftKeys().sort()).toEqual(['general', 'prompt'])
    clearDraft('general')
    expect(draftKeys()).toEqual(['prompt'])
  })
})
