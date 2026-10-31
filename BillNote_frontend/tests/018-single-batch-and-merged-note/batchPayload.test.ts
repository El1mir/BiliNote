import { describe, expect, it } from 'vitest'

import { buildBatchPayload } from '../../src/utils/batchPayload'

const profile = {
  quality: 'medium',
  scene: 'life',
  detail: 'detailed',
  format: ['toc'],
  video_understanding: false,
  video_interval: 6,
  sampling_mode: 'interval',
  max_frames: 60,
  frames_per_second: 2,
  frame_limit_mode: 'total',
  grid_size: [2, 2],
  ocr_assist: null,
}

const items = [
  {
    bvid: 'BV1a',
    p: 1,
    video_id: 'BV1a_p1',
    url: 'https://www.bilibili.com/video/BV1a?p=1',
    title: '第一集',
  },
  {
    bvid: 'BV1a',
    p: 2,
    video_id: 'BV1a_p2',
    url: 'https://www.bilibili.com/video/BV1a?p=2',
    title: '第二集',
  },
]

describe('buildBatchPayload', () => {
  it('不合并时带分组名，且不带 merge 字段', () => {
    const payload = buildBatchPayload(profile, items, { merge: false, groupName: '  我的合集  ' })

    expect(payload.platform).toBe('bilibili')
    expect(payload.items).toEqual(items)
    expect(payload.group_name).toBe('我的合集')
    expect(payload.merge).toBeUndefined()
    expect(payload.merge_title).toBeUndefined()
    expect(payload.quality).toBe('medium')
  })

  it('合并时不带分组名（后端不建组）', () => {
    const payload = buildBatchPayload(profile, items, {
      merge: true,
      groupName: '不该出现的组名',
      mergeTitle: '  合并标题  ',
    })

    expect(payload.merge).toBe(true)
    expect(payload.merge_title).toBe('合并标题')
    expect(payload.merge_polish).toBe(false)
    expect('group_name' in payload).toBe(false)
  })

  it('合并润色开关透传为布尔值', () => {
    const payload = buildBatchPayload(profile, items, {
      merge: true,
      mergeTitle: 't',
      mergePolish: true,
    })
    expect(payload.merge_polish).toBe(true)
  })

  it('缺省标题时给空串，由调用方校验必填', () => {
    const payload = buildBatchPayload(profile, items, { merge: true })
    expect(payload.merge_title).toBe('')
  })
})
