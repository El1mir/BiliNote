import { useCallback, useEffect, useRef, useState } from 'react'

/**
 * Desktop sidecar health.
 *
 * The Tauri shell owns the Python process and emits what it sees on stdout,
 * stderr and process exit; this hook turns that stream into state the startup
 * screen can render. On the web build none of it exists and every value stays
 * inert, so callers never need to branch on the platform.
 */

const isTauri = typeof window !== 'undefined' && '__TAURI_INTERNALS__' in window

const MAX_LOG_LINES = 200

export type LogLevel = 'info' | 'error'

export interface LogEntry {
  level: LogLevel
  text: string
  ts: number
}

export type BackendProcessStatus = 'running' | 'terminated'

export interface BackendEvents {
  status: BackendProcessStatus
  exitCode: number | null
  logs: LogEntry[]
  /** Ask the Rust side to kill and relaunch the sidecar. */
  restart: () => Promise<void>
  /** Copy the buffered log to the clipboard; false when the clipboard is unavailable. */
  copyLogs: () => Promise<boolean>
  isTauri: boolean
}

export function useBackendEvents(): BackendEvents {
  const [status, setStatus] = useState<BackendProcessStatus>('running')
  const [exitCode, setExitCode] = useState<number | null>(null)
  const [logs, setLogs] = useState<LogEntry[]>([])

  // The buffer is kept in a ref as well: the listeners close over it once, and
  // they must always append to the latest array rather than the first render's.
  const bufferRef = useRef<LogEntry[]>([])
  // A restart kills the old process on purpose; the exit that follows is ours,
  // not a crash, so it must not flip the status.
  const expectExitRef = useRef(false)

  const append = useCallback((entry: LogEntry) => {
    const next = bufferRef.current.concat(entry)
    if (next.length > MAX_LOG_LINES) next.splice(0, next.length - MAX_LOG_LINES)
    bufferRef.current = next
    setLogs(next)
  }, [])

  useEffect(() => {
    if (!isTauri) return
    let cancelled = false
    const unlisten: Array<() => void> = []

    void (async () => {
      const { listen } = await import('@tauri-apps/api/event')
      const stops = await Promise.all([
        listen<string>('backend-message', event => {
          append({ level: 'info', text: unwrapQuotes(event.payload), ts: Date.now() })
        }),
        listen<string>('backend-error', event => {
          append({ level: 'error', text: unwrapQuotes(event.payload), ts: Date.now() })
        }),
        listen('backend-restarting', () => {
          expectExitRef.current = true
          window.setTimeout(() => {
            expectExitRef.current = false
          }, 3000)
          append({ level: 'info', text: '[Backend restarting]', ts: Date.now() })
        }),
        listen<number | null>('backend-terminated', event => {
          const code = event.payload ?? 'unknown'
          if (expectExitRef.current) {
            expectExitRef.current = false
            append({
              level: 'info',
              text: `[Backend terminated, restart in progress] code=${code}`,
              ts: Date.now(),
            })
            return
          }
          setStatus('terminated')
          setExitCode(typeof event.payload === 'number' ? event.payload : null)
          append({ level: 'error', text: `[Backend terminated] code=${code}`, ts: Date.now() })
        }),
        listen('backend-restarted', () => {
          setStatus('running')
          setExitCode(null)
          append({ level: 'info', text: '[Backend restarted]', ts: Date.now() })
        }),
      ])
      // Unmounting while the listeners were still registering would otherwise
      // leak all five of them.
      if (cancelled) stops.forEach(stop => stop())
      else unlisten.push(...stops)
    })()

    return () => {
      cancelled = true
      unlisten.forEach(stop => stop())
    }
  }, [append])

  const restart = useCallback(async () => {
    if (!isTauri) return
    const { invoke } = await import('@tauri-apps/api/core')
    try {
      await invoke('restart_backend_sidecar')
    } catch (error) {
      append({
        level: 'error',
        text: `[Restart failed] ${(error as Error)?.message ?? error}`,
        ts: Date.now(),
      })
      throw error
    }
  }, [append])

  const copyLogs = useCallback(async () => {
    const text = bufferRef.current
      .map(
        line =>
          `${new Date(line.ts).toISOString().slice(11, 19)} ${line.level === 'error' ? 'E' : 'I'} ${line.text}`
      )
      .join('\n')
    try {
      await navigator.clipboard.writeText(text)
      return true
    } catch {
      return false
    }
  }, [])

  return { status, exitCode, logs, restart, copyLogs, isTauri }
}

/** Older Rust builds wrapped stdout in single quotes; newer ones send it raw. */
function unwrapQuotes(value: string): string {
  if (typeof value !== 'string') return String(value)
  if (value.length >= 2 && value.startsWith("'") && value.endsWith("'")) return value.slice(1, -1)
  return value
}
