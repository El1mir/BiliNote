import { Link } from 'react-router-dom'
import { Compass } from 'lucide-react'
import { useI18n } from '@/ember/i18n/context'
import { AppShell } from '@/ember/shell/AppShell'
import { EmptyState } from '@/ember/ui/EmptyState'
import { FileText, Settings } from 'lucide-react'

export function NotFoundPage() {
  const { t } = useI18n()
  return (
    <AppShell
      nav={[
        { to: '/', label: t('nav.workspace'), icon: <FileText className="size-4" />, end: true },
        { to: '/settings', label: t('nav.settings'), icon: <Settings className="size-4" /> },
      ]}
    >
      <div className="grid min-h-[60vh] place-items-center">
        <EmptyState
          icon={<Compass className="size-8" />}
          title={t('notFound.title')}
          description={t('notFound.description')}
          action={
            // A link styled as the primary button: wrapping it in <Button> would nest
            // an <a> inside a <button>, which is invalid and breaks middle-click.
            <Link
              to="/"
              className="ember-press inline-flex h-10 shrink-0 items-center justify-center rounded-control border border-transparent bg-ember px-4 text-body font-semibold whitespace-nowrap text-white hover:bg-ember-hover hover:shadow-ember"
            >
              {t('notFound.back')}
            </Link>
          }
        />
      </div>
    </AppShell>
  )
}
