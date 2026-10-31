import type { ReactNode } from 'react'
import { cn } from '@/ember/lib/cn'

type SettingsSectionProps = {
  title: ReactNode
  description?: ReactNode
  actions?: ReactNode
  children: ReactNode
  className?: string
}

/** A titled block inside a settings screen. Headings are the only Playfair text here. */
export function SettingsSection({ title, description, actions, children, className }: SettingsSectionProps) {
  return (
    <section className={cn('flex flex-col gap-4', className)}>
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div className="flex flex-col gap-1">
          <h2 className="font-display text-section leading-tight">{title}</h2>
          {description ? <p className="max-w-2xl text-small text-ink-soft">{description}</p> : null}
        </div>
        {actions ? <div className="flex items-center gap-2">{actions}</div> : null}
      </div>
      {children}
    </section>
  )
}

type SettingRowProps = {
  label: ReactNode
  hint?: ReactNode
  control: ReactNode
  className?: string
}

/** Label + hint on the left, control on the right; stacks on narrow screens. */
export function SettingRow({ label, hint, control, className }: SettingRowProps) {
  return (
    <div
      className={cn(
        'flex flex-col gap-3 border-b border-line/70 py-4 last:border-b-0 sm:flex-row sm:items-center sm:justify-between',
        className,
      )}
    >
      <div className="flex min-w-0 flex-col gap-0.5">
        <span className="text-small font-semibold text-ink">{label}</span>
        {hint ? <span className="text-caption text-ink-soft">{hint}</span> : null}
      </div>
      <div className="shrink-0 sm:w-64">{control}</div>
    </div>
  )
}
