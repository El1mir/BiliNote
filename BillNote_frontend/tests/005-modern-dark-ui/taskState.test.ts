import { describe, expect, it } from 'vitest'
import { dictionaries, format } from '../../src/ember/i18n/strings'
import type { MessageKey } from '../../src/ember/i18n/strings'
import { detailSummary, stageKey, statusKey, taskProgress } from '../../src/ember/features/workspace/taskState'

/** 与 `src/ember/i18n/locale.ts` 的 `translate` 同义，但没有 localStorage 依赖。 */
const t = (key: MessageKey, values?: Record<string, string | number>) =>
  format(dictionaries['zh-CN'][key] ?? key, values)

/**
 * spec 005 ticket 12 第 2 条：未知阶段必须回退，而不是被当成"已完成"。
 *
 * 这条正是工单 08 缺陷 2/3 漏掉的那个断点 —— 原先 `success` / `failed` 都不在
 * 映射表里，返回 -1 之后时间线把 12 个阶段全画成待处理。
 */
describe('stageKey', () => {
  it('maps every in-flight stage the backend can write', () => {
    expect(stageKey('queued')).toBe('task.stage.queued')
    expect(stageKey('fetching_subtitles')).toBe('task.stage.downloading')
    expect(stageKey('downloading_video')).toBe('task.stage.downloading')
    expect(stageKey('downloading_audio')).toBe('task.stage.downloading')
    expect(stageKey('transcribing')).toBe('task.stage.transcribing')
    expect(stageKey('extracting_frames')).toBe('task.stage.frames')
    expect(stageKey('building_grids')).toBe('task.stage.frames')
    expect(stageKey('summarizing')).toBe('task.stage.summarizing')
    expect(stageKey('post_processing')).toBe('task.stage.postProcessing')
    expect(stageKey('saving')).toBe('task.stage.saving')
  })

  it('keeps the terminal stages distinguishable', () => {
    // 成功仍显示"完成"，失败必须单独有一条，否则失败的任务看起来像走完了。
    expect(stageKey('success')).toBe('task.stage.done')
    expect(stageKey('failed')).toBe('task.stage.failed')
  })

  it('returns null for unknown, empty and missing stages', () => {
    expect(stageKey('brand_new_stage')).toBeNull()
    expect(stageKey('')).toBeNull()
    expect(stageKey(null)).toBeNull()
    expect(stageKey(undefined)).toBeNull()
  })
})

describe('statusKey', () => {
  it('keeps the legacy FAILD spelling on the failed copy', () => {
    expect(statusKey('SUCCESS')).toBe('task.status.succeeded')
    expect(statusKey('FAILED')).toBe('task.status.failed')
    expect(statusKey('FAILD')).toBe('task.status.failed')
    expect(statusKey('PENDING')).toBe('task.status.queued')
    expect(statusKey('TRANSCRIBING')).toBe('task.status.running')
    expect(statusKey(undefined)).toBe('task.status.queued')
  })
})

/**
 * spec 005 ticket 12 第 3 条：`progress` 为 null 时不能伪造数值。
 *
 * `taskProgress` 返回的是 0–1 的给进度条用的数，这里只钉住"没有进度就是 0，
 * 但有进度时不能被当成比例再乘一次"这条容易写错的分支。
 */
describe('taskProgress', () => {
  it('passes a backend 0-100 percentage straight through', () => {
    expect(taskProgress({ progress: 40 } as never)).toBeCloseTo(0.4)
    expect(taskProgress({ progress: 100 } as never)).toBe(1)
    expect(taskProgress({ progress: 0 } as never)).toBe(0)
  })

  it('scales a legacy 0-1 fraction up before clamping', () => {
    expect(taskProgress({ progress: 0.5 } as never)).toBeCloseTo(0.5)
  })

  it('falls back to the stage-level number when the task-level one is missing', () => {
    expect(taskProgress({ progress: null, stageProgress: 60 } as never)).toBeCloseTo(0.6)
  })

  it('returns 0 when there is no progress at all, never NaN', () => {
    expect(taskProgress({ progress: null, stageProgress: null } as never)).toBe(0)
    expect(taskProgress({} as never)).toBe(0)
    expect(taskProgress(undefined)).toBe(0)
  })
})

/**
 * 工单 08 缺陷 1：切片数 / 帧数 / 网格数就藏在 detail 里，必须能读出来。
 */
describe('detailSummary', () => {
  it('renders the counted unit with both numbers', () => {
    expect(detailSummary({ current: 3, total: 12, unit: 'frames' }, t)).toBe('3 / 12 帧')
    expect(detailSummary({ current: 2, total: 8, unit: 'grids' }, t)).toBe('2 / 8 个网格图')
    expect(detailSummary({ current: 5, total: 20, unit: 'segments' }, t)).toBe('5 / 20 段')
  })

  it('degrades to plain numbers for an unknown unit', () => {
    expect(detailSummary({ current: 3, total: 12, unit: 'whatever' }, t)).toBe('3 / 12')
    expect(detailSummary({ current: 3, total: 12 }, t)).toBe('3 / 12')
  })

  it('shows a lone counter when the total is missing', () => {
    expect(detailSummary({ current: 7 }, t)).toBe('7')
  })

  it('renders nothing for details it cannot read', () => {
    expect(detailSummary(null, t)).toBeNull()
    expect(detailSummary(undefined, t)).toBeNull()
    expect(detailSummary({}, t)).toBeNull()
    expect(detailSummary({ stage: 'pick_frames' }, t)).toBeNull()
    expect(detailSummary({ candidates: ['a', 'b'] }, t)).toBeNull()
  })
})
