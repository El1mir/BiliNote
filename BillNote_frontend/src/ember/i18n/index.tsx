import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'
import { I18nContext, type I18nValue } from './context'
import { LOCALE_STORAGE_KEY, readStoredLocale } from './locale'
import { dictionaries, format as formatTemplate, type Locale } from './strings'

export function EmberI18nProvider({ children }: { children: ReactNode }) {
  const [locale, setLocaleState] = useState<Locale>(readStoredLocale)

  useEffect(() => {
    document.documentElement.lang = locale
  }, [locale])

  const setLocale = useCallback((next: Locale) => {
    setLocaleState(next)
    try {
      window.localStorage.setItem(LOCALE_STORAGE_KEY, next)
    } catch {
      /* storage disabled — the choice still applies for this session */
    }
  }, [])

  const value = useMemo<I18nValue>(() => {
    const dictionary = dictionaries[locale]
    return {
      locale,
      setLocale,
      t: (key, values) => formatTemplate(dictionary[key] ?? key, values),
    }
  }, [locale, setLocale])

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>
}

export { LOCALES } from './strings'
export type { Locale, MessageKey } from './strings'
