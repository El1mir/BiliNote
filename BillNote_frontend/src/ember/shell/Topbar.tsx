import { useI18n } from '@/ember/i18n/context'
import { LanguageSwitcher } from '@/ember/shell/LanguageSwitcher'
import { ThemeToggle } from '@/ember/shell/ThemeToggle'
import { useBackendStatus, type BackendStatus } from '@/ember/shell/useBackendStatus'
import { cn } from '@/ember/lib/cn'

const DOT: Record<BackendStatus, string> = {
  checking: 'bg-ink-mute',
  online: 'bg-success',
  offline: 'bg-danger',
}

/** One line of chrome above the page: where you are, whether the backend is
 *  alive, and the two global switches. The page keeps its own h1 — this is a
 *  location label, not a second title. */
export function Topbar({ label }: { label: string }) {
  const { t } = useI18n()
  const status = useBackendStatus()
  const statusText = t(`shell.backend.${status}` as 'shell.backend.online')

  return (
    <header className="sticky top-0 z-20 hidden h-12 shrink-0 items-center gap-4 border-b border-line bg-canvas/90 px-6 backdrop-blur md:flex">
      <nav aria-label="breadcrumb" className="flex min-w-0 items-center gap-2 text-small">
        <span className="shrink-0 font-semibold text-ink-mute">BiliNote</span>
        <span aria-hidden="true" className="text-line-strong">/</span>
        <span className="truncate font-semibold text-ink">{label}</span>
      </nav>

      <div className="ml-auto flex items-center gap-1">
        {/* Status is dot + words: colour alone would drop the meaning for
            colour-blind users and in a grayscale screenshot. */}
        <span
          className="mr-2 inline-flex items-center gap-1.5 rounded-control px-2 py-1 text-caption font-semibold text-ink-soft"
          role="status"
        >
          <span className={cn('size-1.5 rounded-full', DOT[status])} aria-hidden="true" />
          {statusText}
        </span>
        <ThemeToggle compact />
        <LanguageSwitcher compact />
      </div>
    </header>
  )
}