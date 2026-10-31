import { useI18n } from '@/ember/i18n/context'

/**
 * Shell-level copy. Every label goes through the ember dictionary, so the shell
 * itself never hardcodes a language (the old version kept its own two-language
 * map here, which is how the shell drifted from the rest of the app).
 */
export function useEmberNav() {
  const { t } = useI18n()
  return {
    overline: t('startup.overline'),
    workspace: t('nav.workspace'),
    settings: t('nav.settings'),
    history: t('history.title'),
    overview: t('nav.overview'),
    openNav: t('shell.openNav'),
    close: t('common.close'),
  }
}
