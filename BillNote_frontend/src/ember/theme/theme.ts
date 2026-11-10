import { useCallback, useSyncExternalStore } from 'react'

export type Theme = 'light' | 'dark'

const STORAGE_KEY = 'bilinote-theme'
const listeners = new Set<() => void>()

function readStored(): Theme {
  if (typeof window === 'undefined') return 'light'
  return window.localStorage.getItem(STORAGE_KEY) === 'dark' ? 'dark' : 'light'
}

let current: Theme = readStored()

/** Apply a theme to <html>. Exported so the boot path can run it before React
 *  mounts and avoid a flash of the wrong palette. */
export function applyTheme(theme: Theme) {
  if (typeof document === 'undefined') return
  const root = document.documentElement
  root.classList.toggle('dark', theme === 'dark')
  root.style.colorScheme = theme
}

/** Read the stored choice and paint it. Call once from main.tsx. */
export function initTheme() {
  current = readStored()
  applyTheme(current)
}

export function setTheme(theme: Theme) {
  current = theme
  try {
    window.localStorage.setItem(STORAGE_KEY, theme)
  } catch {
    /* private mode / storage disabled: the session still switches, it just
       will not survive a reload. Not worth a visible error. */
  }
  applyTheme(theme)
  listeners.forEach(listener => listener())
}

function subscribe(listener: () => void) {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

export function useTheme() {
  const theme = useSyncExternalStore(subscribe, () => current, () => 'light' as Theme)
  const toggle = useCallback(() => setTheme(theme === 'dark' ? 'light' : 'dark'), [theme])
  return { theme, setTheme, toggle }
}