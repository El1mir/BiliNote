import { useEffect, useRef, useState } from 'react'
import { FileText, Settings } from 'lucide-react'
import { useSearchParams } from 'react-router-dom'
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
import { Button } from '@/ember/ui/Button'
import {
  readTaskId,
  shouldProbeTask,
  taskSelectionStatus,
  writeTaskId,
} from '@/ember/lib/taskUrl'

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
  const [searchParams, setSearchParams] = useSearchParams()
  const urlTaskId = readTaskId(searchParams.toString())
  /**
   * 地址栏给的 id 在内存里找不到时，单独问后端一次再下结论。
   * 'unprobed' → 'found' | 'missing'，换个 id 重置；不做第二次，避免死循环。
   */
  const [probe, setProbe] = useState<{ id: string; result: 'found' | 'missing' } | null>(null)

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

  const status = taskSelectionStatus({
    urlTaskId,
    listLoading,
    knownIds: tasks.map(task => task.id),
    probe: probe?.id === urlTaskId ? probe.result : 'unprobed',
  })

  // store 只是 URL 的内存镜像：地址栏说了算，不同意就把它改回来。
  useEffect(() => {
    if (currentTaskId !== urlTaskId) setCurrentTask(urlTaskId)
  }, [urlTaskId, currentTaskId, setCurrentTask])

  // 深链到一条内存里没有的任务：先按 id 单独回填，回填不到才算失效。
  const rehydrateTask = useTaskStore(state => state.rehydrateTask)
  const probingId = useRef<string | null>(null)
  useEffect(() => {
    if (!shouldProbeTask({ status, listLoading, probe: 'unprobed' }) || !urlTaskId) return
    if (probingId.current === urlTaskId) return
    probingId.current = urlTaskId
    let cancelled = false
    void rehydrateTask(urlTaskId).then(task => {
      if (cancelled) return
      setProbe({ id: urlTaskId, result: task ? 'found' : 'missing' })
    })
    return () => {
      cancelled = true
    }
  }, [status, listLoading, urlTaskId, rehydrateTask])

  /** 选中一条任务：只改地址栏，store 的镜像由上面的 effect 负责。 */
  const selectTask = (taskId: string | null) => {
    setSearchParams(prev => new URLSearchParams(writeTaskId(prev.toString(), taskId)), {
      replace: false,
    })
    setProbe(null)
  }

  const currentTask = urlTaskId
    ? tasks.find(task => task.id === urlTaskId)
    : tasks.find(task => task.id === currentTaskId)

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

        {status === 'missing' ? (
          <EmptyState
            icon={<FileText className="size-6" />}
            title={t('workspace.taskMissingTitle')}
            description={t('workspace.taskMissingDescription')}
            action={
              <Button size="sm" variant="secondary" onClick={() => selectTask(null)}>
                {t('workspace.taskMissingAction')}
              </Button>
            }
          />
        ) : currentTask ? (
          <>
            <TaskProgressCard
              task={currentTask}
              onRetry={() => {
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