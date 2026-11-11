import { AlertTriangle, CheckCircle2, Clock, Loader2 } from 'lucide-react'
import { Badge } from '@/ember/ui/Badge'
import { useI18n } from '@/ember/i18n/context'
import { cn } from '@/ember/lib/cn'
import { statusIconKind, statusKey, statusTone } from './taskState'

type StatusBadgeProps = {
  status: string | undefined
  className?: string
}

/**
 * Status as **two channels**: a shape and a word.
 *
 * Colour alone fails for roughly one in twelve users, and in a dense list the
 * tint of a 12px chip is the first thing to disappear. The icon carries the
 * meaning, the label says it, and the tone only reinforces.
 */
export function StatusBadge({ status, className }: StatusBadgeProps) {
  const { t } = useI18n()
  const kind = statusIconKind(status)
  const Icon =
    kind === 'done' ? CheckCircle2 : kind === 'failed' ? AlertTriangle : kind === 'queued' ? Clock : Loader2

  return (
    <Badge tone={statusTone(status)} className={className}>
      <Icon
        aria-hidden="true"
        className={cn('size-3 shrink-0', kind === 'running' && 'ember-spin')}
      />
      <span>{t(statusKey(status))}</span>
    </Badge>
  )
}
