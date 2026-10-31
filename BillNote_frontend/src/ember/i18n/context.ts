import { createContext, useContext } from 'react'
import type { Locale, MessageKey } from './strings'

export type I18nValue = {
  locale: Locale
  setLocale: (locale: Locale) => void
  /** Look up a message; unknown keys fall back to the key itself (never throws). */
  t: (key: MessageKey, values?: Record<string, string | number>) => string
}

export const I18nContext = createContext<I18nValue | null>(null)

export function useI18n(): I18nValue {
  const value = useContext(I18nContext)
  if (!value) throw new Error('useI18n must be used inside <EmberI18nProvider>')
  return value
}
