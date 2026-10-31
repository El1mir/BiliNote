import { describe, expect, it } from 'vitest'
import { FINISHED_TASK_STATUSES, isTaskInFlight } from '../../src/utils/taskStatus'

describe('isTaskInFlight', () => {
  it('treats only SUCCESS and FAILED as finished', () => {
    expect(FINISHED_TASK_STATUSES).toEqual(['SUCCESS', 'FAILED'])
    expect(isTaskInFlight('SUCCESS')).toBe(false)
    expect(isTaskInFlight('FAILED')).toBe(false)
  })

  it('treats every in-progress status as in flight', () => {
    const inFlight = [
      'PENDING',
      'PARSING',
      'DOWNLOADING',
      'TRANSCRIBING',
      'SUMMARIZING',
      'FORMATTING',
      'SAVING',
    ]
    for (const status of inFlight) {
      expect(isTaskInFlight(status)).toBe(true)
    }
  })

  it('treats missing or unknown status as not in flight', () => {
    // 未知状态按「可删」处理是刻意的：真正的判定在后端，前端这份只用来置灰按钮。
    // 若这里返回 true，后端新增一个状态就会让一批任务在前端永远删不掉。
    expect(isTaskInFlight(null)).toBe(false)
    expect(isTaskInFlight(undefined)).toBe(false)
    expect(isTaskInFlight('')).toBe(false)
    expect(isTaskInFlight('SOMETHING_NEW')).toBe(false)
  })
})
