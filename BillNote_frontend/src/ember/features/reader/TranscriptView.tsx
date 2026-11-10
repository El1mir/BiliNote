import { useMemo, useState } from 'react'
import { Clock, Search, SearchX, X } from 'lucide-react'
import type { Task } from '@/store/taskStore'
import { useI18n } from '@/ember/i18n/context'
import { Button } from '@/ember/ui/Button'
import { EmptyState } from '@/ember/ui/EmptyState'
import { Input } from '@/ember/ui/Input'
import { cn } from '@/ember/lib/cn'

const formatTime = (seconds: number): string => {
  const total = Math.max(0, Math.floor(seconds))
  const h = Math.floor(total / 3600)
  const m = Math.floor((total % 3600) / 60)
  const s = total % 60
  const mm = String(m).padStart(2, '0')
  const ss = String(s).padStart(2, '0')
  return h > 0 ? `${h}:${mm}:${ss}` : `${mm}:${ss}`
}

/** Timestamped transcript with an in-place filter. */
export function TranscriptView({ task }: { task: Task | undefined }) {
  const { t } = useI18n()
  const [query, setQuery] = useState('')
  // Memoised: `?? []` would hand useMemo a fresh array on every render and defeat it.
  const segments = useMemo(() => task?.transcript?.segments ?? [], [task?.transcript?.segments])

  const visible = useMemo(() => {
    const needle = query.trim().toLowerCase()
    if (!needle) return segments
    return segments.filter(segment => segment.text.toLowerCase().includes(needle))
  }, [segments, query])

  if (!segments.length) {
    return <EmptyState icon={<Clock className="size-6" />} title={t('common.empty')} />
  }

  return (
    <div className="flex min-h-0 flex-col gap-3">
      <div className="relative max-w-sm">
        <Search aria-hidden="true" className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-ink-mute" />
        <Input
          value={query}
          onChange={event => setQuery(event.target.value)}
          placeholder={t('common.search')}
          className="h-9 pl-9"
          aria-label={t('common.search')}
        />
      </div>
      {visible.length ? (
        <div className="flex flex-col divide-y divide-line/70 rounded-surface border border-line bg-surface">
          {visible.map((segment, index) => (
            <div key={`${segment.start}-${index}`} className="flex gap-4 px-4 py-3">
              <span className={cn('w-14 shrink-0 pt-0.5 font-mono text-caption text-ink-mute tabular-nums')}>
                {formatTime(segment.start)}
              </span>
              <p className="min-w-0 flex-1 text-small leading-relaxed text-ink">{segment.text}</p>
            </div>
          ))}
        </div>
      ) : (
        // A filter with no hits used to render an empty bordered box: the
        // container looked broken instead of saying "nothing matched".
        <EmptyState
          icon={<SearchX className="size-6" />}
          title={t('transcript.noResults', { query: query.trim() })}
          description={t('transcript.noResultsHint', { count: segments.length })}
          className="rounded-surface border border-line bg-surface py-8"
          action={
            <Button size="sm" variant="ghost" onClick={() => setQuery('')}>
              <X className="size-3.5" />
              {t('transcript.clearSearch')}
            </Button>
          }
        />
      )}
    </div>
  )
}
