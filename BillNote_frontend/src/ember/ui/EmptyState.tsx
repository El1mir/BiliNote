import type { ReactNode } from 'react'
import { cn } from '@/ember/lib/cn'

type EmptyStateProps = {
  icon?: ReactNode
  title: ReactNode
  description?: ReactNode
  action?: ReactNode
  className?: string
}

/**
 * Rare, high-emotion surface: this is where a gentle entrance earns its place.
 * The wrapper fades and rises once; it never blocks interaction.
 */
export function EmptyState({ icon, title, description, action, className }: EmptyStateProps) {
  return (
    <div className={cn('ember-enter flex flex-col items-center justify-center gap-3 px-6 py-14 text-center', className)}>
      {icon ? <div className="text-ink-mute">{icon}</div> : null}
      <h3 className="font-display text-subhead text-ink">{title}</h3>
      {description ? <p className="max-w-sm text-small text-ink-soft">{description}</p> : null}
      {action ? <div className="mt-1">{action}</div> : null}
    </div>
  )
}
