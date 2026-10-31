import { AlertTriangle, CheckCircle2, Loader2 } from 'lucide-react'
import type { Task } from '@/store/taskStore'
import { useI18n } from '@/ember/i18n/context'
import { Card } from '@/ember/ui/Card'
import { Progress } from '@/ember/ui/Progress'
import { Button } from '@/ember/ui/Button'
import { Badge } from '@/ember/ui/Badge'
import { stageKey, statusKey, statusTone, taskProgress, taskTitle } from '@/ember/features/workspace/taskState'

type TaskProgressCardProps = {
  task: Task
  onRetry?: () => void
}

/**
 * Live progress for the selected task. The percentage and the bar are driven by
 * one number, so they can never disagree; the bar animates on transform only.
 */
export function TaskProgressCard({ task, onRetry }: TaskProgressCardProps) {
  const { t } = useI18n()
  const value = taskProgress(task)
  const running = !['SUCCESS', 'FAILED', 'FAILD'].includes(String(task.status))
  const failed = ['FAILED', 'FAILD'].includes(String(task.status))
  const stage = stageKey(task.stage)

  return (
    <Card className="bg-canvas">
      <div className="flex flex-col gap-3 p-4 sm:p-5">
        <div className="flex items-start gap-3">
          <span className="mt-0.5 shrink-0">
            {failed ? (
              <AlertTriangle className="size-4 text-danger" />
            ) : running ? (
              <Loader2 className="size-4 animate-spin text-ember" />
            ) : (
              <CheckCircle2 className="size-4 text-ok" />
            )}
          </span>
          <div className="flex min-w-0 flex-1 flex-col gap-0.5">
            <p className="line-clamp-1 text-small font-semibold text-ink">{taskTitle(task)}</p>
            <p className="text-caption text-ink-soft">
              {task.stageLabel || (stage ? t(stage) : t(statusKey(task.status)))}
            </p>
          </div>
          <Badge tone={statusTone(task.status)}>{t(statusKey(task.status))}</Badge>
        </div>

        {running || failed ? <Progress value={value} label={t('task.progress')} /> : null}

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
