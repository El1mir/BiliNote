import { AlertTriangle, CheckCircle2, Loader2 } from 'lucide-react'
import type { Task } from '@/store/taskStore'
import { useI18n } from '@/ember/i18n/context'
import { Card } from '@/ember/ui/Card'
import { Progress } from '@/ember/ui/Progress'
import { Button } from '@/ember/ui/Button'
import { Badge } from '@/ember/ui/Badge'
import { Spinner } from '@/ember/ui/Spinner'
import {
  detailSummary,
  stageKey,
  statusKey,
  statusTone,
  taskProgress,
  taskTitle,
} from '@/ember/features/workspace/taskState'

type TaskProgressCardProps = {
  task: Task
  onRetry?: () => void
}

/**
 * Live progress for the selected task. The percentage and the bar are driven by
 * one number, so they can never disagree; the bar animates on transform only.
 *
 * 阶段行优先显示后端写的 `stage_label`（"音频转写""拼接网格图"这种），回落到
 * 前端 14 阶段映射，最后才回落到状态文案 —— 三档回退保证任何一条历史记录都
 * 不会出现空行。`detail` 里的计数（切片/帧/网格）单独一行，只在认得出来时渲染。
 */
export function TaskProgressCard({ task, onRetry }: TaskProgressCardProps) {
  const { t } = useI18n()
  const value = taskProgress(task)
  const running = !['SUCCESS', 'FAILED', 'FAILD'].includes(String(task.status))
  const failed = ['FAILED', 'FAILD'].includes(String(task.status))
  const stage = stageKey(task.stage)
  const stageLabel = task.stageLabel || (stage ? t(stage) : t(statusKey(task.status)))
  const detail = detailSummary(task.detail, t)
  // 失败的进度条停在出错的位置；`progress` 为 null 时（后端对该阶段没有权重）
  // 只显示阶段名，不伪造一个 0% 或 100%。
  const showProgress = task.progress !== null && task.progress !== undefined

  return (
    <Card className="bg-canvas">
      <div className="flex flex-col gap-3 p-4 sm:p-5">
        <div className="flex items-start gap-3">
          <span className="mt-0.5 shrink-0">
            {failed ? (
              <AlertTriangle className="text-danger size-4" />
            ) : running ? (
              <Loader2 className="ember-spin text-primary size-4" />
            ) : (
              <CheckCircle2 className="text-ok size-4" />
            )}
          </span>
          <div className="flex min-w-0 flex-1 flex-col gap-0.5">
            <p className="text-small text-ink line-clamp-1 font-semibold">{taskTitle(task)}</p>
            <p className="text-caption text-ink-soft line-clamp-1" data-testid="task-stage">
              {stageLabel}
            </p>
            {detail ? (
              <p
                className="text-caption text-ink-mute truncate tabular-nums"
                data-testid="task-detail"
              >
                {detail}
              </p>
            ) : null}
          </div>
          <Badge tone={statusTone(task.status)}>{t(statusKey(task.status))}</Badge>
        </div>

        {showProgress ? (
          <Progress value={value} label={t('task.progress')} />
        ) : running ? (
          // 后端对这个阶段没有权重（`global_progress` 返回 None）时**不画进度条**：
          // 一条停在 0% 或凭空 100% 的条比没有条更误导人。
          <Spinner label={t('task.progressIndeterminate')} className="text-ink-soft" />
        ) : null}

        {task.message ? <p className="text-caption text-ink-soft">{task.message}</p> : null}

        {failed && onRetry ? (
          <div>
            <Button size="sm" variant="secondary" onClick={onRetry}>
              {t('common.retry')}
            </Button>
          </div>
        ) : null}
      </div>
    </Card>
  )
}
