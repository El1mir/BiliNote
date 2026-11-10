import { Component, Fragment, type ErrorInfo, type ReactNode } from 'react'
import { Copy, RefreshCw, TriangleAlert } from 'lucide-react'
import { I18nContext, type I18nValue } from '@/ember/i18n/context'
import { Button } from '@/ember/ui/Button'

type Props = {
  children: ReactNode
  /** Optional label rendered above the title — keeps the card reusable per surface. */
  scope?: string
}

type State = {
  error: Error | null
  componentStack: string
  /** Bumped on retry so the failed subtree remounts instead of re-rendering the same state. */
  attempt: number
  copyState: 'idle' | 'ok' | 'fail'
}

/**
 * Last-resort render guard for the whole routed tree.
 *
 * Before this existed a throw anywhere below the router unmounted the entire
 * tree and left a blank page — no message, no way back, nothing to report. The
 * fallback deliberately reuses the boot failure card's vocabulary (one column,
 * one card, danger-tinted header, actions in the footer) so a crash reads as
 * the same class of event as a failed backend probe, and gives the user the two
 * things that actually help: retry, and a copyable trace to paste into an issue.
 *
 * It reads the locale through `contextType` rather than `useI18n` because a
 * class component cannot call hooks, and it must keep working if the provider
 * itself is what failed.
 */
export class ErrorBoundary extends Component<Props, State> {
  static contextType = I18nContext
  declare context: I18nValue | null

  state: State = { error: null, componentStack: '', attempt: 0, copyState: 'idle' }

  static getDerivedStateFromError(error: Error): Partial<State> {
    return { error }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    // Keep the console trace: the on-screen card is for the user, the console is
    // for whoever is running the app with devtools open.
    console.error('[ember] render error', error, info.componentStack)
    this.setState({ componentStack: info.componentStack ?? '' })
  }

  private traceText = (): string => {
    const { error, componentStack } = this.state
    if (!error) return ''
    return [`${error.name}: ${error.message}`, error.stack ?? '', componentStack].filter(Boolean).join('\n\n')
  }

  private handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(this.traceText())
      this.setState({ copyState: 'ok' })
    } catch {
      this.setState({ copyState: 'fail' })
    }
    window.setTimeout(() => this.setState({ copyState: 'idle' }), 2000)
  }

  private handleRetry = () => {
    this.setState(state => ({
      error: null,
      componentStack: '',
      attempt: state.attempt + 1,
      copyState: 'idle',
    }))
  }

  render() {
    const { error, attempt, copyState } = this.state
    if (!error) {
      // Remounting the subtree on retry is the only thing that can clear a
      // render-time throw; a plain re-render would hit the same bad state again.
      return <Fragment key={attempt}>{this.props.children}</Fragment>
    }

    // The provider may be the thing that blew up, so every string has a literal fallback.
    const t: I18nValue['t'] = this.context?.t ?? (key => String(key))
    const zh = this.context?.locale !== 'en-US'
    const title = t('boundary.title')
    const body = t('boundary.description')
    const detail = `${error.name}: ${error.message}`

    return (
      <div
        data-boundary-state="error"
        data-boundary-error={detail}
        className="ember-grain flex min-h-screen flex-col bg-canvas"
      >
        <main className="flex flex-1 items-start justify-center px-4 py-10 sm:items-center sm:px-6">
          <section
            aria-labelledby="boundary-title"
            className="w-full max-w-[560px] overflow-hidden rounded-surface border border-line bg-canvas shadow-raise"
          >
            <div className="flex items-start gap-3 border-b border-line bg-danger-soft px-5 py-4">
              <span className="mt-0.5 grid size-8 shrink-0 place-items-center rounded-full bg-danger/10 text-danger">
                <TriangleAlert className="size-4" aria-hidden="true" />
              </span>
              <div className="min-w-0">
                <h1 id="boundary-title" className="text-subhead text-ink">
                  {title}
                </h1>
                {this.props.scope ? (
                  <p className="mt-0.5 font-mono text-caption text-ink-mute">{this.props.scope}</p>
                ) : null}
              </div>
            </div>

            <div className="flex flex-col gap-3 px-5 py-4">
              <p className="text-small text-ink-soft">{body}</p>
              <pre
                data-boundary-detail
                className="max-h-40 overflow-auto rounded-control bg-raised px-3 py-2 font-mono text-caption leading-relaxed text-danger"
              >
                {detail}
              </pre>
              <p className="text-caption text-ink-mute">
                {zh
                  ? '页面其余部分仍然可用；若反复出现，请复制日志并反馈。'
                  : 'The rest of the page is unaffected. If this repeats, copy the logs and report it.'}
              </p>
            </div>

            <div className="flex flex-wrap gap-2 border-t border-line bg-surface px-5 py-4">
              <Button variant="primary" size="sm" onClick={this.handleRetry} className="gap-1.5">
                <RefreshCw className="size-3.5" aria-hidden="true" />
                {t('boundary.retry')}
              </Button>
              <Button variant="secondary" size="sm" onClick={this.handleCopy} className="gap-1.5">
                <Copy className="size-3.5" aria-hidden="true" />
                {copyState === 'ok' ? t('boundary.copied') : copyState === 'fail' ? t('boundary.copyFailed') : t('boundary.copyLogs')}
              </Button>
            </div>
          </section>
        </main>
      </div>
    )
  }
}
