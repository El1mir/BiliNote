import { useEffect, useState } from 'react'
import { FileText, Settings } from 'lucide-react'
import toast from 'react-hot-toast'
import { useTaskStore } from '@/store/taskStore'
import { retryFailedTasks } from '@/services/note'
import { retryResultKind, retrySelectedFailedTasks } from '@/ember/features/workspace/retryFailed'
import { useTaskPolling } from '@/hooks/useTaskPolling'
import { useI18n } from '@/ember/i18n/context'
import { AppShell } from '@/ember/shell/AppShell'
import { LanguageSwitcher } from '@/ember/shell/LanguageSwitcher'
import { EmptyState } from '@/ember/ui/EmptyState'
import { IntakePanel } from '@/ember/features/workspace/IntakePanel'
import { GroupPanel } from '@/ember/features/workspace/GroupPanel'
import { TaskList } from '@/ember/features/workspace/TaskList'
import { TaskProgressCard } from '@/ember/features/workspace/TaskProgressCard'
import { useNoteGroups } from '@/ember/features/workspace/useNoteGroups'
import { NotePanel } from '@/ember/features/reader/NotePanel'

/**
 * The workspace: compose on the left, read in the middle, history on the right.
 * Below 1280px the history rail folds under the content instead of disappearing,
 * so no feature becomes unreachable on a tablet.
 */
export function WorkspacePage() {
  const { t } = useI18n()
  const tasks = useTaskStore(state => state.tasks)
  const currentTaskId = useTaskStore(state => state.currentTaskId)
  const loadTasks = useTaskStore(state => state.loadTasks)
  const setCurrentTask = useTaskStore(state => state.setCurrentTask)
  const [listLoading, setListLoading] = useState(true)
  const noteGroups = useNoteGroups()

  useTaskPolling(3000)

  useEffect(() => {
    let cancelled = false
    void loadTasks().finally(() => {
      if (!cancelled) setListLoading(false)
    })
    return () => {
      cancelled = true
    }
  }, [loadTasks])

  const currentTask = tasks.find(task => task.id === currentTaskId)

  const retryFailedInScope = async (
    selectedIds: string[],
    scope: 'all' | 'group',
    groupId: string | null,
  ) => {
    try {
      const result = await retrySelectedFailedTasks(
        tasks,
        selectedIds,
        scope,
        groupId,
        retryFailedTasks,
        loadTasks,
      )
      if (!result) return
      const skipped = result.skipped.length + result.missing.length
      const scopeLabel =
        scope === 'all'
          ? t('history.retryScopeAll')
          : groupId
            ? noteGroups.groups.find(group => group.id === groupId)?.name ?? t('history.retryScopeGroup')
            : t('history.retryScopeUngrouped')
      const kind = retryResultKind(result)
      if (kind === 'none') {
        toast(t('history.retryNone', { scope: scopeLabel, skipped }))
      } else if (kind === 'partial') {
        toast.success(t('history.retryPartial', { scope: scopeLabel, requeued: result.requeued.length, skipped }))
      } else {
        toast.success(t('history.retryDone', { scope: scopeLabel, requeued: result.requeued.length }))
      }
    } catch (error) {
      toast.error(
        t('history.retryFailedError', {
          message: error instanceof Error ? error.message : String(error),
        }),
      )
    }
  }

  return (
    <AppShell
      nav={[
        { to: '/', label: t('nav.workspace'), icon: <FileText className="size-4" />, end: true },
        { to: '/settings', label: t('nav.settings'), icon: <Settings className="size-4" /> },
      ]}
      sidebarFooter={<LanguageSwitcher />}
      rail={
        <div className="flex flex-col gap-3 lg:sticky lg:top-8 lg:max-h-[calc(100vh-4rem)]">
          <GroupPanel state={noteGroups} totalCount={tasks.length} />
          <TaskList
            loading={listLoading}
            activeGroupId={noteGroups.activeGroupId}
            onDragTasks={noteGroups.setDraggingIds}
            onDragEnd={() => noteGroups.setDropTargetId(null)}
            groups={noteGroups.groups}
            onMoveTasks={(ids, groupId) => void noteGroups.moveTasks(ids, groupId)}
            onRetryFailedTasks={retryFailedInScope}
          />
        </div>
      }
    >
      <div className="flex flex-col gap-6">
        <header className="flex flex-wrap items-start justify-between gap-3">
          <div className="flex min-w-0 flex-col gap-1">
            <h1 className="font-display text-section leading-tight">{t('workspace.title')}</h1>
            <p className="text-small text-ink-soft">{t('workspace.subtitle')}</p>
          </div>
        </header>

        {/* spec 018：单集/批量在输入区内用 Tab 切换，页头不再放第二套入口。 */}
        <IntakePanel onSubmitted={() => void loadTasks()} />

        {currentTask ? (
          <>
            <TaskProgressCard
              task={currentTask}
              onRetry={() => {
                setCurrentTask(currentTask.id)
                void loadTasks()
              }}
            />
            <NotePanel task={currentTask} />
          </>
        ) : (
          <EmptyState
            icon={<FileText className="size-6" />}
            title={t('workspace.noTaskTitle')}
            description={t('workspace.noTaskDescription')}
          />
        )}
      </div>
    </AppShell>
  )
}
