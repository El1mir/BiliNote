import type { HTMLAttributes } from 'react'
import { cn } from '@/ember/lib/cn'

type BadgeProps = HTMLAttributes<HTMLSpanElement> & {
  tone?: 'neutral' | 'ember' | 'accent' | 'success' | 'warning' | 'danger'
}

const TONE: Record<NonNullable<BadgeProps['tone']>, string> = {
  neutral: 'bg-raised text-ink-soft',
  ember: 'bg-ember-soft text-ember',
  accent: 'bg-accent/15 text-warn',
  success: 'bg-ok/10 text-ok',
  warning: 'bg-warn/10 text-warn',
  danger: 'bg-danger/10 text-danger',
}

/** Small 4px-radius status marker. Amber is reserved for attention-drawing badges. */
export function Badge({ className, tone = 'neutral', ...rest }: BadgeProps) {
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1 rounded-inline px-2 py-0.5 text-caption font-semibold',
        TONE[tone],
        className,
      )}
      {...rest}
    />
  )
}
