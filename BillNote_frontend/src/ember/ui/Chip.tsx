import type { ButtonHTMLAttributes } from 'react'
import { cn } from '@/ember/lib/cn'

type ChipProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  active?: boolean
  tone?: 'neutral' | 'success' | 'warning' | 'danger'
}

const TONE: Record<NonNullable<ChipProps['tone']>, string> = {
  neutral: 'text-ink-soft',
  success: 'text-ok',
  warning: 'text-warn',
  danger: 'text-danger',
}

/** Pill chip — 9999px radius. Active state is the only place a chip fills with Accent. */
export function Chip({ className, active, tone = 'neutral', children, ...rest }: ChipProps) {
  return (
    <button
      type="button"
      aria-pressed={active}
      className={cn(
        'ember-press inline-flex items-center gap-1.5 rounded-full px-3.5 py-1.5 text-small font-semibold whitespace-nowrap',
        active
          ? 'bg-primary text-on-primary'
          : cn('bg-raised hover:bg-raised-hover', TONE[tone]),
        className,
      )}
      {...rest}
    >
      {children}
    </button>
  )
}