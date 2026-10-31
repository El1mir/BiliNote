import { useId, type ReactNode } from 'react'
import { cn } from '@/ember/lib/cn'

export type TabItem = { id: string; label: ReactNode; badge?: ReactNode }

type TabsProps = {
  items: TabItem[]
  value: string
  onChange: (id: string) => void
  className?: string
}

/** Underline tabs — active tab is terracotta with a 2px bottom border. */
export function Tabs({ items, value, onChange, className }: TabsProps) {
  const groupId = useId()
  return (
    <div role="tablist" aria-orientation="horizontal" className={cn('flex items-center gap-1 border-b border-line', className)}>
      {items.map(item => {
        const active = item.id === value
        return (
          <button
            key={item.id}
            type="button"
            role="tab"
            id={`${groupId}-${item.id}`}
            aria-selected={active}
            onClick={() => onChange(item.id)}
            className={cn(
              'ember-press relative -mb-px inline-flex items-center gap-1.5 rounded-t-control px-3 py-2 text-small font-semibold',
              active ? 'text-ember' : 'text-ink-soft hover:bg-surface hover:text-ink',
            )}
          >
            {item.label}
            {item.badge}
            {active ? <span aria-hidden="true" className="absolute inset-x-2 -bottom-px h-0.5 rounded-full bg-ember" /> : null}
          </button>
        )
      })}
    </div>
  )
}
