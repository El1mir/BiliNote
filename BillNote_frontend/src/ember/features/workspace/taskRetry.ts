import { UNGROUPED_ID } from '@/services/noteGroup'
import type { Task } from '@/store/taskStore'
import type { RetryFailedResult } from '@/services/note'

export type RetryScope = { scope: 'all' | 'group'; groupId?: string | null }

export type RetryFeedback =
  | { kind: 'empty' }
  | { kind: 'success'; result: RetryFailedResult }
  | { kind: 'failure' }

export const failedTasksInScope = (tasks: Task[], activeGroupId: string | null): Task[] =>
  tasks.filter(task => {
    if (!['FAILED', 'FAILD'].includes(String(task.status))) return false
    if (activeGroupId === null) return true
    if (activeGroupId === UNGROUPED_ID) return !task.groupId
    return task.groupId === activeGroupId
  })

export const retryScopeForGroup = (activeGroupId: string | null): RetryScope => {
  if (activeGroupId === null) return { scope: 'all' }
  return {
    scope: 'group',
    groupId: activeGroupId === UNGROUPED_ID ? null : activeGroupId,
  }
}

export const retryFailedTasksInScope = async (
  tasks: Task[],
  activeGroupId: string | null,
  retry: (scope: 'all' | 'group', groupId?: string | null) => Promise<RetryFailedResult>,
  refresh: () => Promise<void>,
  feedback: (result: RetryFeedback) => void
): Promise<void> => {
  if (failedTasksInScope(tasks, activeGroupId).length === 0) {
    feedback({ kind: 'empty' })
    return
  }

  const scope = retryScopeForGroup(activeGroupId)
  try {
    const result = await retry(scope.scope, scope.groupId)
    await refresh()
    feedback({ kind: 'success', result })
  } catch {
    feedback({ kind: 'failure' })
  }
}
