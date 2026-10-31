import { useMemo, useState } from 'react'
import { AlertTriangle, Copy, RefreshCw, RotateCcw, TriangleAlert } from 'lucide-react'
import { useBackendEvents } from '@/ember/startup/useBackendEvents'
import { Button } from '@/ember/ui/Button'
import { Spinner } from '@/ember/ui/Spinner'
import { LanguageSwitcher } from '@/ember/shell/LanguageSwitcher'
import { useI18n } from '@/ember/i18n/context'
import type { BootFailureReason } from '@/hooks/useCheckBackend'

/** Mirrors TOTAL_TIMEOUT_MS in useCheckBackend — the readiness budget shown to the user. */
const READINESS_BUDGET_S = 60

/** How many stderr lines the failure card previews before pointing at Copy. */
const STDERR_PREVIEW_LINES = 6

type Props = {
  /** The backend is still being probed. */
  loading: boolean
  /** The probe gave up — show the recovery card instead of the spinner. */
  failed: boolean
  /** Human-readable reason, straight from useCheckBackend (fallback text only). */
  lastError: string | null
  /** Structured cause — rendered through i18n so the card follows the locale. */
  reason?: BootFailureReason | null
  /** Re-run the readiness probe without restarting the sidecar. */
  onRetry?: () => void
}

/**
 * Full-screen boot surface.
 *
 * The app cannot render a single route until the backend answers, so this is
 * the first thing every user sees — it carries the wordmark, the wait state,
 * and the recovery path when the wait fails. It is deliberately chrome-free:
 * one centred column, one card, and the language switcher so a user who cannot
 * read the default locale can still change it before anything else loads.
 */
export function StartupScreen({ loading, failed, lastError, reason, onRetry }: Props) {
  const { t } = useI18n()
  const { isTauri, restart, copyLogs, logs } = useBackendEvents()
  const [restarting, setRestarting] = useState(false)
  const [copyState, setCopyState] = useState<'idle' | 'ok' | 'fail'>('idle')

  // The hook's own lastError is a summary; the ring buffer usually holds the
  // Python traceback tail, which names the real failure.
  const stderrPreview = useMemo(() => {
    if (!failed || !logs?.length) return []
    return logs
      .filter(line => line.level === 'error')
      .slice(-STDERR_PREVIEW_LINES)
      .map(line => line.text)
  }, [failed, logs])

  const handleRestart = async () => {
    setRestarting(true)
    try {
      await restart()
    } catch {
      // restart() already appended the failure to the log ring buffer.
    } finally {
      setRestarting(false)
      onRetry?.()
    }
  }

  const handleCopy = async () => {
    const ok = await copyLogs()
    setCopyState(ok ? 'ok' : 'fail')
    window.setTimeout(() => setCopyState('idle'), 2000)
  }

  const causes = [
    t('startup.failed.causePath'),
    t('startup.failed.causePort'),
    t('startup.failed.causeModel'),
  ]

  // The hook reports a code plus raw detail; the sentence itself is built here so
  // the failure card speaks the locale the user picked instead of the backend's.
  const failureMessage = useMemo(() => {
    if (!failed) return ''
    const detail = reason?.detail || lastError || t('startup.failed.fallback')
    const code = reason?.code ?? 'unknown'
    switch (code) {
      case 'timeout':
        return t('startup.failed.reason.timeout', { seconds: READINESS_BUDGET_S, detail })
      case 'connect':
        return t('startup.failed.reason.connect', { detail })
      case 'http':
        return t('startup.failed.reason.http', { detail })
      case 'terminated':
        return t('startup.failed.reason.terminated', { detail })
      case 'startup_timeout':
        return t('startup.failed.reason.startup_timeout', { detail })
      default:
        return t('startup.failed.reason.unknown', { detail })
    }
  }, [failed, reason, lastError, t])

  return (
    <div
      data-boot-state={failed ? 'failed' : loading ? 'loading' : 'idle'}
      data-boot-error={lastError ?? ''}
      className="ember-grain flex min-h-screen flex-col bg-canvas"
    >
      <header className="flex shrink-0 items-center justify-end px-4 py-4 sm:px-6">
        <LanguageSwitcher />
      </header>

      <main className="flex flex-1 items-start justify-center px-4 pb-16 sm:items-center sm:px-6">
        <div className="ember-enter w-full max-w-[460px]">
          <Wordmark overline={t('startup.overline')} />

          {failed ? (
            <section
              aria-labelledby="startup-failed-title"
              className="mt-8 overflow-hidden rounded-surface border border-line bg-canvas shadow-raise"
            >
              <div className="flex items-start gap-3 border-b border-line bg-[#fef2f2] px-5 py-4">
                <span className="mt-0.5 grid size-8 shrink-0 place-items-center rounded-full bg-danger/10 text-danger">
                  <TriangleAlert className="size-4" aria-hidden="true" />
                </span>
                <div className="min-w-0">
                  <h1 id="startup-failed-title" className="text-subhead">
                    {t('startup.failed.title')}
                  </h1>
                  <p className="mt-1 text-small break-words text-ink-soft">
                    {failureMessage}
                  </p>
                </div>
              </div>

              <div className="space-y-5 px-5 py-5">
                {stderrPreview.length > 0 && (
                  <section>
                    <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
                      <h2 className="ember-overline">{t('startup.failed.logTitle')}</h2>
                      <span className="text-caption text-ink-mute">
                        {t('startup.failed.logHint')}
                      </span>
                    </div>
                    <pre className="mt-2 max-h-36 overflow-auto rounded-control bg-ink px-3 py-2 font-mono text-caption leading-relaxed text-[#fca5a5]">
                      {stderrPreview.join('\n')}
                    </pre>
                  </section>
                )}

                <section>
                  <h2 className="ember-overline">{t('startup.failed.causesTitle')}</h2>
                  <ul className="mt-2 space-y-1.5">
                    {causes.map(cause => (
                      <li key={cause} className="flex gap-2.5 text-small text-ink-soft">
                        <span
                          aria-hidden="true"
                          className="mt-[7px] size-1.5 shrink-0 rounded-full bg-ember/60"
                        />
                        <span className="min-w-0">{cause}</span>
                      </li>
                    ))}
                  </ul>
                </section>
              </div>

              <div className="flex flex-wrap gap-2 border-t border-line bg-surface px-5 py-4">
                {isTauri && (
                  <Button
                    variant="primary"
                    size="sm"
                    onClick={handleRestart}
                    loading={restarting}
                    className="gap-1.5"
                  >
                    {!restarting && <RotateCcw className="size-3.5" aria-hidden="true" />}
                    {restarting ? t('startup.restarting') : t('startup.restart')}
                  </Button>
                )}
                <Button variant="secondary" size="sm" onClick={handleCopy} className="gap-1.5">
                  <Copy className="size-3.5" aria-hidden="true" />
                  {copyState === 'ok'
                    ? t('startup.copied')
                    : copyState === 'fail'
                      ? t('startup.copyFailed')
                      : t('startup.copyLogs')}
                </Button>
                <Button variant="ghost" size="sm" onClick={onRetry} className="gap-1.5">
                  <RefreshCw className="size-3.5" aria-hidden="true" />
                  {t('startup.retry')}
                </Button>
              </div>
            </section>
          ) : (
            <section
              aria-labelledby="startup-loading-title"
              aria-busy={loading}
              className="mt-8 rounded-surface border border-line bg-canvas px-5 py-5 shadow-raise"
            >
              <div className="flex items-center gap-3">
                <Spinner className="text-ember" />
                <h1 id="startup-loading-title" className="text-subhead">
                  {t('startup.loading.title')}
                </h1>
              </div>
              <p className="mt-3 text-small text-ink-soft">{t('startup.loading.description')}</p>
              <div className="mt-5 h-1 overflow-hidden rounded-full bg-raised">
                <div className="ember-indeterminate h-full w-1/3 rounded-full bg-ember" />
              </div>
            </section>
          )}

          {/* Install-path advice is a desktop (Tauri) concern: a browser deployment has
              no install directory, so showing it there is noise the user cannot act on. */}
          {isTauri && (
            <p className="mt-6 flex items-start gap-2 text-caption text-ink-mute">
              <AlertTriangle className="mt-px size-3.5 shrink-0" aria-hidden="true" />
              <span>{t('startup.notice.pathAdvice')}</span>
            </p>
          )}
        </div>
      </main>
    </div>
  )
}

/** Terracotta tile + Playfair wordmark. Shared by both boot states. */
function Wordmark({ overline }: { overline: string }) {
  return (
    <div className="flex items-center gap-3">
      <span className="grid size-11 shrink-0 place-items-center rounded-surface bg-ember font-display text-subhead font-bold text-white shadow-ember">
        B
      </span>
      <span className="min-w-0">
        <span className="block font-display text-subhead leading-tight font-bold">BiliNote</span>
        <span className="ember-overline block">{overline}</span>
      </span>
    </div>
  )
}
