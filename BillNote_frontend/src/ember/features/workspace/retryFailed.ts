import type { RetryFailedResult } from '@/services/note'
import type { Task } from '@/store/taskStore'
import { UNGROUPED_ID } from '@/services/noteGroup'

export type RetryScope = { scope: 'all' | 'group'; groupId: string | null }

export const retryScopeForGroup = (activeGroupId: string | null): RetryScope =>
  activeGroupId === null
    ? { scope: 'all', groupId: null }
    : { scope: 'group', groupId: activeGroupId === UNGROUPED_ID ? null : activeGroupId }

export const retryResultKind = (result: RetryFailedResult): 'none' | 'partial' | 'done' => {
  const skipped = result.skipped.length + result.missing.length
  if (result.requeued.length === 0) return 'none'
  return skipped > 0 ? 'partial' : 'done'
}

/** Empty selections and selections without FAILED tasks never reach the API. */
export async function retrySelectedFailedTasks(
  tasks: Task[],
  selectedIds: string[],
  scope: 'all' | 'group',
  groupId: string | null,
  retry: (scope: 'all' | 'group', groupId: string | null) => Promise<RetryFailedResult>,
  refresh: () => Promise<unknown>,
): Promise<RetryFailedResult | null> {
  const selected = new Set(selectedIds)
  if (!tasks.some(task => selected.has(task.id) && ['FAILED', 'FAILD'].includes(String(task.status)))) {
    return null
  }

  const result = await retry(scope, groupId)
  await refresh()
  return result
}
