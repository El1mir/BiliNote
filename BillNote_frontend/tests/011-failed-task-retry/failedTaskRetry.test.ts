import { describe, expect, it, vi } from 'vitest'

import {
  failedTasksInScope,
  retryFailedTasksInScope,
  retryScopeForGroup,
} from '../../src/ember/features/workspace/taskRetry'
import type { Task } from '../../src/store/taskStore'
import type { RetryFailedResult } from '../../src/services/note'

const makeTask = (id: string, status: string, groupId: string | null): Task =>
  ({
    id,
    status: status as Task['status'],
    groupId,
    groupName: '',
    platform: 'bilibili',
    markdown: '',
    transcript: { full_text: '', language: '', raw: null, segments: [] },
    audioMeta: { cover_url: '', duration: 0, file_path: '', platform: '', raw_info: null, title: id, video_id: id },
    createdAt: '',
    formData: {},
  }) as Task

const result: RetryFailedResult = {
  scope: 'group',
  group_id: 'group-a',
  candidates: 2,
  requeued: ['task-a'],
  skipped: [{ task_id: 'task-b', reason: 'in_progress' }],
  missing: [],
}

describe('failed task retry scope', () => {
  const tasks = [
    makeTask('task-a', 'FAILED', 'group-a'),
    makeTask('task-b', 'FAILD', 'group-a'),
    makeTask('task-c', 'FAILED', null),
    makeTask('task-d', 'SUCCESS', 'group-a'),
    makeTask('task-e', 'FAILED', 'group-b'),
  ]

  it('counts only failed tasks in the currently visible group scope', () => {
    expect(failedTasksInScope(tasks, null).map(task => task.id)).toEqual([
      'task-a', 'task-b', 'task-c', 'task-e',
    ])
    expect(failedTasksInScope(tasks, 'group-a').map(task => task.id)).toEqual(['task-a', 'task-b'])
    expect(failedTasksInScope(tasks, '__ungrouped__').map(task => task.id)).toEqual(['task-c'])
  })

  it('maps all, named-group and ungrouped filters to the supported API scope', () => {
    expect(retryScopeForGroup(null)).toEqual({ scope: 'all' })
    expect(retryScopeForGroup('group-a')).toEqual({ scope: 'group', groupId: 'group-a' })
    expect(retryScopeForGroup('__ungrouped__')).toEqual({ scope: 'group', groupId: null })
  })

  it('does not call retry or refresh for an empty failure set and reports empty feedback', async () => {
    const retry = vi.fn(async () => result)
    const refresh = vi.fn(async () => {})
    const feedback = vi.fn()

    await retryFailedTasksInScope(
      [makeTask('done', 'SUCCESS', null)], null, retry, refresh, feedback
    )

    expect(retry).not.toHaveBeenCalled()
    expect(refresh).not.toHaveBeenCalled()
    expect(feedback).toHaveBeenCalledWith({ kind: 'empty' })
  })

  it('uses the current group scope, refreshes on success and reports requeued count source', async () => {
    const retry = vi.fn(async () => result)
    const refresh = vi.fn(async () => {})
    const feedback = vi.fn()

    await retryFailedTasksInScope(tasks, 'group-a', retry, refresh, feedback)

    expect(retry).toHaveBeenCalledWith('group', 'group-a')
    expect(refresh).toHaveBeenCalledOnce()
    expect(feedback).toHaveBeenCalledWith({ kind: 'success', result })
  })

  it('reports request errors without refreshing', async () => {
    const retry = vi.fn(async () => { throw new Error('network') })
    const refresh = vi.fn(async () => {})
    const feedback = vi.fn()

    await retryFailedTasksInScope(tasks, null, retry, refresh, feedback)

    expect(retry).toHaveBeenCalledWith('all', undefined)
    expect(refresh).not.toHaveBeenCalled()
    expect(feedback).toHaveBeenCalledWith({ kind: 'failure' })
  })
})
