import { useEffect, useState } from 'react'
import { getBackendBase } from '@/hooks/useCheckBackend'

export type BackendStatus = 'checking' | 'online' | 'offline'

const PROBE_TIMEOUT_MS = 5_000
const POLL_INTERVAL_MS = 30_000

/**
 * Cheap liveness indicator for the top bar.
 *
 * The startup gate (`useCheckBackend`) already proved the backend once; this
 * keeps the answer fresh while the app is open so a stopped server is visible
 * without waiting for the next user action to fail.
 *
 * ponytail: one 30s poll and no backoff — a liveness dot does not need a
 * retry policy. Switch to the SSE stream the task list already holds if the
 * polling ever becomes noticeable.
 */
export function useBackendStatus(): BackendStatus {
  const [status, setStatus] = useState<BackendStatus>('checking')

  useEffect(() => {
    let cancelled = false
    const probe = async () => {
      const controller = new AbortController()
      const timer = setTimeout(() => controller.abort(), PROBE_TIMEOUT_MS)
      try {
        const res = await fetch(`${getBackendBase()}/sys_check`, { signal: controller.signal })
        if (!cancelled) setStatus(res.ok ? 'online' : 'offline')
      } catch {
        if (!cancelled) setStatus('offline')
      } finally {
        clearTimeout(timer)
      }
    }
    void probe()
    const id = setInterval(probe, POLL_INTERVAL_MS)
    return () => {
      cancelled = true
      clearInterval(id)
    }
  }, [])

  return status
}