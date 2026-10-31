import { describe, expect, it } from 'vitest'

import {
  DEFAULT_GENERATION_SETTINGS,
  toPayloadSettings,
} from '@/ember/features/workspace/generationSettings'
import { buildBatchPayload } from '@/utils/batchPayload'

/**
 * spec 020：批量面板原来根本没有生成设置，只能吃写死的 DEFAULT_PROFILE。
 * 现在两处共用一套设置，这里钉住「UI 三态 ocr_assist → 接口 true/false/null」
 * 的折算，以及设置真的能流进批量请求体。
 */
describe('generationSettings', () => {
  it('默认值覆盖面板需要的全部字段', () => {
    expect(DEFAULT_GENERATION_SETTINGS).toMatchObject({
      quality: 'medium',
      scene: 'life',
      detail: 'detailed',
      video_understanding: false,
      sampling_mode: 'interval',
      ocr_assist: 'global',
    })
    expect(DEFAULT_GENERATION_SETTINGS.grid_size).toHaveLength(2)
  })

  it('ocr_assist 三态折成 true / false / null', () => {
    const base = DEFAULT_GENERATION_SETTINGS
    expect(toPayloadSettings({ ...base, ocr_assist: 'global' }).ocr_assist).toBeNull()
    expect(toPayloadSettings({ ...base, ocr_assist: 'on' }).ocr_assist).toBe(true)
    expect(toPayloadSettings({ ...base, ocr_assist: 'off' }).ocr_assist).toBe(false)
  })

  it('其余设置原样透传给请求体', () => {
    const settings = {
      ...DEFAULT_GENERATION_SETTINGS,
      quality: 'slow' as const,
      scene: 'academic',
      detail: 'brief',
      format: ['toc', 'screenshot'],
      extras: '多写例题',
      video_understanding: true,
      video_interval: 10,
      max_frames: 30,
      grid_size: [3, 2] as [number, number],
    }
    expect(toPayloadSettings(settings)).toMatchObject({
      quality: 'slow',
      scene: 'academic',
      detail: 'brief',
      format: ['toc', 'screenshot'],
      extras: '多写例题',
      video_understanding: true,
      video_interval: 10,
      max_frames: 30,
      grid_size: [3, 2],
    })
  })

  it('批量请求体带上设置；合并时依然不带 group_name', () => {
    const profile = toPayloadSettings({ ...DEFAULT_GENERATION_SETTINGS, quality: 'fast' })
    const items = [{ bvid: 'BV1', p: 1, video_id: 'BV1', url: 'https://b23.tv/x' }]
    const plain = buildBatchPayload(profile, items, { merge: false, groupName: '组' })
    expect(plain.quality).toBe('fast')
    expect(plain.group_name).toBe('组')
    expect(plain.ocr_assist).toBeNull()
    const merged = buildBatchPayload(profile, items, { merge: true, mergeTitle: '合并' })
    expect(merged.group_name).toBeUndefined()
    expect(merged.merge).toBe(true)
  })
})
