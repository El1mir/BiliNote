import { useCallback, useSyncExternalStore } from 'react'

/** Three preferences, two paint states: the stored choice can be 'system',
 *  which resolves against the OS and is re-resolved when the OS flips. */
export type Theme = 'light' | 'dark' | 'system'
export type ResolvedTheme = 'light' | 'dark'

const STORAGE_KEY = 'bilinote-theme'
const CYCLE: Theme[] = ['light', 'dark', 'system']

const listeners = new Set<() => void>()
const media = typeof window !== 'undefined' ? window.matchMedia?.('(prefers-color-scheme: dark)') : undefined

/** Pure part of the resolution so it can be tested without a DOM. */
export function resolveTheme(theme: Theme, prefersDark: boolean): ResolvedTheme {
  if (theme === 'system') return prefersDark ? 'dark' : 'light'
  return theme
}

/** light → dark → system → light. */
export function nextTheme(theme: Theme): Theme {
  const i = CYCLE.indexOf(theme)
  return CYCLE[(i + 1) % CYCLE.length]
}

function readStored(): Theme {
  if (typeof window === 'undefined') return 'light'
  const stored = window.localStorage.getItem(STORAGE_KEY)
  return stored === 'dark' || stored === 'system' ? stored : 'light'
}

let current: Theme = readStored()

/** Apply a preference to <html>. Exported so the boot path can run it before
 *  React mounts and avoid a flash of the wrong palette. */
export function applyTheme(theme: Theme) {
  if (typeof document === 'undefined') return
  const resolved = resolveTheme(theme, media?.matches ?? false)
  const root = document.documentElement
  root.classList.toggle('dark', resolved === 'dark')
  root.dataset.theme = resolved
  root.style.colorScheme = resolved
}

/** Read the stored choice and paint it. Call once from main.tsx. */
export function initTheme() {
  current = readStored()
  applyTheme(current)

  // 'system' has to follow the OS while the app is open; the listener only
  // does anything when the preference is 'system'.
  media?.addEventListener('change', () => {
    if (current === 'system') applyTheme(current)
  })
}

function emit() {
  for (const listener of listeners) listener()
}

export function setTheme(theme: Theme) {
  current = theme
  if (typeof window !== 'undefined') window.localStorage.setItem(STORAGE_KEY, theme)
  applyTheme(current)
  emit()
}

function subscribe(listener: () => void) {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

export function useTheme() {
  const theme = useSyncExternalStore(
    subscribe,
    () => current,
    () => 'light' as Theme,
  )
  const cycle = useCallback(() => setTheme(nextTheme(theme)), [theme])
  return { theme, resolved: resolveTheme(theme, media?.matches ?? false), setTheme, cycle }
}