import { useState } from 'react'
import { RotateCcw } from 'lucide-react'
import type { Task } from '@/store/taskStore'
import { useI18n } from '@/ember/i18n/context'
import { Card } from '@/ember/ui/Card'
import { Progress } from '@/ember/ui/Progress'
import { Button } from '@/ember/ui/Button'
import { Spinner } from '@/ember/ui/Spinner'
import { StatusBadge } from './StatusBadge'
import { detailSummary, stageKey, statusKey, taskProgress, taskTitle } from './taskState'

type TaskProgressCardProps = {
  task: Task
  /** 重试失败任务；返回的 promise 结束前按钮保持 busy。 */
  onRetry?: () => void | Promise<void>
}

/**
 * Live progress for the selected task. The percentage and the bar are driven by
 * one number, so they can never disagree; the bar animates on transform only.
 *
 * 阶段行优先显示后端写的 `stage_label`（"音频转写""拼接网格图"这种），回落到
 * 前端 14 阶段映射，最后才回落到状态文案 —— 三档回退保证任何一条历史记录都
 * 不会出现空行。`detail` 里的计数（切片/帧/网格）单独一行，只在认得出来时渲染。
 *
 * 重试按钮自带 busy：重试接口按"范围内所有失败任务"排队，双击会让同一批失败
 * 任务排两次队。`retrying` 同时挡住第二次点击并把按钮切到 loading。
 */
export function TaskProgressCard({ task, onRetry }: TaskProgressCardProps) {
  const { t } = useI18n()
  const [retrying, setRetrying] = useState(false)
  const value = taskProgress(task)
  const running = !['SUCCESS', 'FAILED', 'FAILD'].includes(String(task.status))
  const failed = ['FAILED', 'FAILD'].includes(String(task.status))
  const stage = stageKey(task.stage)
  const stageLabel = task.stageLabel || (stage ? t(stage) : t(statusKey(task.status)))
  const detail = detailSummary(task.detail, t)
  // 失败的进度条停在出错的位置；`progress` 为 null 时（后端对该阶段没有权重）
  // 只显示阶段名，不伪造一个 0% 或 100%。
  const showProgress = task.progress !== null && task.progress !== undefined

  const retry = async () => {
    if (!onRetry || retrying) return
    setRetrying(true)
    try {
      await onRetry()
    } finally {
      setRetrying(false)
    }
  }

  return (
    <Card>
      <div className="flex flex-col gap-3 p-4 sm:p-6">
        <div className="flex items-start gap-3">
          <div className="flex min-w-0 flex-1 flex-col gap-1">
            <span className="ember-overline text-ink-muted">{t('workspace.title')}</span>
            <p className="line-clamp-1 text-card leading-snug font-semibold text-ink">
              {taskTitle(task)}
            </p>
            <p className="line-clamp-1 text-caption text-ink-soft" data-testid="task-stage">
              {stageLabel}
            </p>
            {detail ? (
              <p className="truncate text-caption tabular-nums text-ink-muted" data-testid="task-detail">
                {detail}
              </p>
            ) : null}
          </div>
          <StatusBadge status={task.status} className="shrink-0" />
        </div>

        {showProgress ? (
          <Progress value={value} label={t('task.progress')} />
        ) : running ? (
          // 后端对这个阶段没有权重（`global_progress` 返回 None）时**不画进度条**：
          // 一条停在 0% 或凭空 100% 的条比没有条更误导人。
          <Spinner label={t('task.progressIndeterminate')} className="text-ink-soft" />
        ) : null}

        {task.message ? (
          <p className="rounded-control border border-danger/20 bg-danger-soft px-3 py-2 text-caption text-danger">
            {task.message}
          </p>
        ) : null}

        {failed && onRetry ? (
          <div>
            <Button
              size="sm"
              variant="secondary"
              loading={retrying}
              aria-busy={retrying || undefined}
              onClick={retry}
            >
              <RotateCcw className="size-3.5" aria-hidden="true" />
              {t('task.retryFailed')}
            </Button>
          </div>
        ) : null}
      </div>
    </Card>
  )
}
