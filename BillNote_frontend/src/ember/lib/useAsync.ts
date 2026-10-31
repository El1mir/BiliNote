import { useCallback, useEffect, useState } from 'react'

type AsyncState<T> = {
  data: T | undefined
  loading: boolean
  error: unknown
  reload: () => void
}

/**
 * Minimal data-fetch hook for settings screens: one request on mount, an
 * explicit reload, and a cancelled flag so a slow response can never write
 * into an unmounted component.
 */
export function useAsync<T>(load: () => Promise<T>, deps: unknown[] = []): AsyncState<T> {
  const [data, setData] = useState<T | undefined>(undefined)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<unknown>(undefined)
  const [nonce, setNonce] = useState(0)

  const reload = useCallback(() => setNonce(value => value + 1), [])

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(undefined)
    load()
      .then(result => {
        if (cancelled) return
        setData(result)
      })
      .catch(cause => {
        if (cancelled) return
        setError(cause)
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [nonce, ...deps])

  return { data, loading, error, reload }
}
