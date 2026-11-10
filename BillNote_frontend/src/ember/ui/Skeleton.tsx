import { cn } from '@/ember/lib/cn'

/** Neutral placeholder that marks loading without moving layout. */
export function Skeleton({ className }: { className?: string }) {
  return <div aria-hidden="true" className={cn('ember-pulse rounded-control bg-raised', className)} />
}
