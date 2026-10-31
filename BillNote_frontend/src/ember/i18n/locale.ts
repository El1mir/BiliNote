import { dictionaries, format as formatTemplate, type Locale, type MessageKey } from './strings'

/**
 * The one storage key both the provider and the non-React helper read.
 *
 * It lives here, not in index.tsx, because a module that exports a component
 * must not also export plain functions: React Fast Refresh can only hot-swap a
 * file whose every export is a component, and mixing the two silently downgrades
 * the whole file to a full reload.
 */
export const LOCALE_STORAGE_KEY = 'bilinote-locale'

export const readStoredLocale = (): Locale => {
  if (typeof window === 'undefined') return 'zh-CN'
  try {
    return window.localStorage.getItem(LOCALE_STORAGE_KEY) === 'en-US' ? 'en-US' : 'zh-CN'
  } catch {
    return 'zh-CN'
  }
}

/**
 * Translate outside React.
 *
 * The preserved data layer (src/services, src/hooks, src/store) raises toasts
 * from plain modules that have no component to read context from — a task that
 * finishes while the user is looking elsewhere still has to speak their
 * language. The locale is read from the same storage key the provider writes,
 * so the two never drift.
 */
export function translate(key: MessageKey, values?: Record<string, string | number>): string {
  return formatTemplate(dictionaries[readStoredLocale()][key] ?? key, values)
}
