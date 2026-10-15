import { describe, expect, it } from 'vitest'
import { noteDetails, noteFormats, noteScenes } from '@/constant/note'

/**
 * spec 015：笔记预设是「场景 × 详略」两个正交维度。
 * 这份测试盯的是**词表本身**，防止有人再把一个维度塞回另一个里。
 */
describe('笔记预设词表（spec 015）', () => {
  it('场景恰好是 life / academic / professional', () => {
    expect(noteScenes.map(scene => scene.value)).toEqual(['life', 'academic', 'professional'])
  })

  it('详略恰好是 brief / detailed', () => {
    expect(noteDetails.map(detail => detail.value)).toEqual(['brief', 'detailed'])
  })

  it('每个维度的标签非空且互不重复', () => {
    for (const axis of [noteScenes, noteDetails]) {
      const labels = axis.map(item => item.label)
      expect(labels.every(label => label.length > 0)).toBe(true)
      expect(new Set(labels).size).toBe(labels.length)
    }
  })

  it('两个维度没有重叠取值（重叠就不是正交组合）', () => {
    const scenes = new Set<string>(noteScenes.map(scene => scene.value))
    const overlap = noteDetails.map(detail => detail.value).filter(value => scenes.has(value))
    expect(overlap).toEqual([])
  })

  it('不再导出旧的九个风格常量', async () => {
    const module = await import('@/constant/note')
    expect(Object.keys(module)).not.toContain('noteStyles')
  })

  it('笔记格式常量不受本 ticket 影响', () => {
    expect(noteFormats.map(format => format.value)).toEqual(['toc', 'link', 'screenshot', 'summary'])
  })
})
