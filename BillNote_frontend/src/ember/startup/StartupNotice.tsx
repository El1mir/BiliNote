import { useEffect, useMemo, useState } from 'react'
import { AlertTriangle, Info, X, XCircle } from 'lucide-react'
import { useI18n } from '@/ember/i18n/context'

type Severity = 'info' | 'warning' | 'error'

interface DiagnosticPayload {
  exe_path?: string
  path_has_non_ascii?: boolean
  path_has_space?: boolean
  parent_writable?: boolean
  platform?: string
}

/**
 * What the sidecar reported, stored as data rather than as rendered text.
 * Keeping the raw event means a language switch re-renders the same warning in
 * the new locale instead of losing it.
 */
type NoticeEvent =
  | { kind: 'path'; payload: DiagnosticPayload }
  | { kind: 'terminated'; exitCode: number | null }

const isTauri = typeof window !== 'undefined' && '__TAURI_INTERNALS__' in window

/** Tone map — warm surfaces only, never a cool grey or a raw Tailwind hue. */
const TONE: Record<Severity, string> = {
  info: 'border-ember/25 bg-ember-soft text-ink',
  warning: 'border-warn/30 bg-[#fffbeb] text-ink',
  error: 'border-danger/30 bg-[#fef2f2] text-ink',
}

const ICON_TONE: Record<Severity, string> = {
  info: 'text-ember',
  warning: 'text-warn',
  error: 'text-danger',
}

const ICON: Record<Severity, typeof Info> = {
  info: Info,
  warning: AlertTriangle,
  error: XCircle,
}

/**
 * Desktop-only startup diagnostics.
 *
 * The Rust sidecar emits these before (or instead of) a successful boot, and
 * they carry information the readiness probe cannot see: a non-ASCII install
 * path, a read-only parent directory, a crashed process with an exit code.
 * Rendered above the boot surface, so it uses the same warm palette.
 */
export function StartupNotice() {
  const { t } = useI18n()
  const [event, setEvent] = useState<NoticeEvent | null>(null)
  const [dismissed, setDismissed] = useState(false)

  useEffect(() => {
    if (!isTauri) return

    let unlisteners: Array<() => void> = []
    let cancelled = false

    void (async () => {
      const { listen } = await import('@tauri-apps/api/event')
      if (cancelled) return

      // Tauri hands the callback an Event envelope, not the bare payload.
      const offWarning = await listen<DiagnosticPayload>('backend-warning', event => {
        setDismissed(false)
        setEvent({ kind: 'path', payload: event.payload || {} })
      })

      const offTerminated = await listen<number | null>('backend-terminated', event => {
        setDismissed(false)
        setEvent({ kind: 'terminated', exitCode: event.payload ?? null })
      })

      // A restart or a late readiness probe clears a stale "terminated" banner,
      // which would otherwise sit there forever after a successful recovery.
      const clearTerminated = () =>
        setEvent(current => (current?.kind === 'terminated' ? null : current))
      const offRestarted = await listen('backend-restarted', clearTerminated)
      const offReady = await listen('backend-ready', clearTerminated)

      if (cancelled) {
        ;[offWarning, offTerminated, offRestarted, offReady].forEach(off => off())
        return
      }
      unlisteners = [offWarning, offTerminated, offRestarted, offReady]
    })()

    return () => {
      cancelled = true
      unlisteners.forEach(off => off())
    }
  }, [])

  const view = useMemo(() => {
    if (!event) return null
    if (event.kind === 'terminated') {
      return {
        severity: 'error' as Severity,
        title: t('startup.notice.terminatedTitle'),
        detail: t('startup.notice.terminatedDetail', {
          code: event.exitCode ?? t('startup.notice.unknown'),
        }),
        dismissible: false,
      }
    }
    const parts: string[] = []
    if (event.payload.path_has_non_ascii) parts.push(t('startup.notice.pathNonAscii'))
    if (event.payload.path_has_space) parts.push(t('startup.notice.pathSpace'))
    if (event.payload.parent_writable === false) parts.push(t('startup.notice.pathReadonly'))
    return {
      severity: 'warning' as Severity,
      title: t('startup.notice.pathTitle'),
      detail:
        `${parts.join('；')}。\n` +
        `${t('startup.notice.pathAdvice')}\n` +
        `${t('startup.notice.currentPath')}：${event.payload.exe_path || t('startup.notice.unknown')}`,
      dismissible: true,
    }
  }, [event, t])

  if (!view || dismissed) return null

  const Icon = ICON[view.severity]

  return (
    <div
      role="status"
      className={`ember-enter shadow-raise fixed inset-x-0 top-0 z-50 flex items-start gap-3 border-b px-4 py-3 sm:px-6 ${TONE[view.severity]}`}
    >
      <Icon className={`mt-0.5 size-4 shrink-0 ${ICON_TONE[view.severity]}`} aria-hidden="true" />
      <div className="min-w-0 flex-1">
        <p className="text-small font-semibold">{view.title}</p>
        <pre className="text-caption text-ink-soft mt-0.5 font-sans break-words whitespace-pre-wrap">
          {view.detail}
        </pre>
      </div>
      {view.dismissible && (
        <button
          type="button"
          onClick={() => setDismissed(true)}
          aria-label={t('startup.notice.dismiss')}
          className="ember-press rounded-control text-ink-mute hover:text-ink -mr-1 grid size-11 shrink-0 place-items-center hover:bg-white/60"
        >
          <X className="size-3.5" aria-hidden="true" />
        </button>
      )}
    </div>
  )
}
