import { describe, expect, it } from 'vitest'
import { isTaskTerminal, normalizeTaskStatus, shouldPollTaskStatus, toDetailPayload } from '../../src/utils/taskStatus'

/**
 * spec 005 ticket 12 第 1 条：轻量状态适配。
 *
 * 后端两个端点用两套命名（手写的 `/task_status/batch` 用下划线，pydantic 的
 * read model 用驼峰），前端必须两套都吃 —— 认错一套的表现是整片字段变 null，
 * 界面上就是"任务在跑但阶段、进度、详情全空"。
 */
describe('task terminal and polling status', () => {
  it.each(['SUCCESS', 'FAILED', 'CANCELLED', 'CANCELED'])('recognizes %s as terminal', status => {
    expect(isTaskTerminal(status)).toBe(true)
  })

  it('keeps successful tasks pollable only when markdown is missing', () => {
    expect(shouldPollTaskStatus('SUCCESS', false)).toBe(true)
    expect(shouldPollTaskStatus('SUCCESS', true)).toBe(false)
  })

  it('does not poll cancelled tasks and continues polling active tasks', () => {
    expect(shouldPollTaskStatus('CANCELLED', false)).toBe(false)
    expect(shouldPollTaskStatus('CANCELED', false)).toBe(false)
    expect(shouldPollTaskStatus('PENDING', false)).toBe(true)
    expect(shouldPollTaskStatus('FAILED', false)).toBe(false)
  })
})

describe('normalizeTaskStatus', () => {
  it('reads the snake_case shape written by /task_status/batch', () => {
    const result = normalizeTaskStatus({
      status: 'TRANSCRIBING',
      stage: 'transcribing',
      stage_label: '音频转写',
      progress: 62,
      stage_progress: 40,
      message: '正在转写 3/10',
      detail: { current: 3, total: 10, unit: 'segments' },
      updated_at: '2026-10-05T10:00:00+00:00',
    })

    expect(result).toEqual({
      status: 'TRANSCRIBING',
      stage: 'transcribing',
      stageLabel: '音频转写',
      progress: 62,
      stageProgress: 40,
      message: '正在转写 3/10',
      detail: { current: 3, total: 10, unit: 'segments' },
      updatedAt: '2026-10-05T10:00:00+00:00',
    })
  })

  it('reads the camelCase shape returned by the read model endpoint', () => {
    const result = normalizeTaskStatus({
      status: 'SUCCESS',
      stage: 'saving',
      stageLabel: '保存结果',
      progress: 100,
      stageProgress: 100,
      message: null,
      detail: { current: 12, total: 12, unit: 'grids' },
      updatedAt: '2026-10-05T10:00:00+00:00',
    })

    expect(result.stageLabel).toBe('保存结果')
    expect(result.stageProgress).toBe(100)
    expect(result.detail).toEqual({ current: 12, total: 12, unit: 'grids' })
    expect(result.updatedAt).toBe('2026-10-05T10:00:00+00:00')
  })

  it('prefers the snake_case value when both spellings are present', () => {
    const result = normalizeTaskStatus({
      stage_label: '音频转写',
      stageLabel: 'WRONG',
      stage_progress: 40,
      stageProgress: 99,
    })

    expect(result.stageLabel).toBe('音频转写')
    expect(result.stageProgress).toBe(40)
  })

  it('leaves absent fields null instead of inventing values', () => {
    const result = normalizeTaskStatus({ status: 'PENDING' })

    expect(result.stage).toBeNull()
    expect(result.stageLabel).toBeNull()
    expect(result.progress).toBeNull()
    expect(result.stageProgress).toBeNull()
    expect(result.message).toBeNull()
    expect(result.detail).toBeNull()
    expect(result.updatedAt).toBeNull()
  })
})

/**
 * detail 的形状由后端自由决定，但**只有 dict 能渲染**。历史上它被声明成
 * `string | null`，于是所有数字都被吞掉（工单 08 缺陷 1）。
 */
describe('toDetailPayload', () => {
  it('keeps a mapping as-is', () => {
    expect(toDetailPayload({ current: 3, total: 12 })).toEqual({ current: 3, total: 12 })
  })

  it('rejects every shape the card cannot render', () => {
    expect(toDetailPayload(null)).toBeNull()
    expect(toDetailPayload(undefined)).toBeNull()
    expect(toDetailPayload('3 / 12')).toBeNull()
    expect(toDetailPayload([1, 2, 3])).toBeNull()
    expect(toDetailPayload(7)).toBeNull()
  })

  it('treats an empty mapping as nothing to show', () => {
    // 后端 `detail or {}` 会写空 dict —— 前端必须当"没有详情"，否则会渲染空行。
    expect(toDetailPayload({})).toEqual({})
  })
})
