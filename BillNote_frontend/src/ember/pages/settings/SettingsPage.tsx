import { NavLink, Navigate, Route, Routes } from 'react-router-dom'
import { Activity, AudioLines, Cpu, FileText, HardDrive, Info, ScanText, Settings as SettingsIcon, SlidersHorizontal, Download as DownloadIcon } from 'lucide-react'
import { useI18n } from '@/ember/i18n/context'
import type { MessageKey } from '@/ember/i18n/strings'
import { AppShell } from '@/ember/shell/AppShell'
import { LanguageSwitcher } from '@/ember/shell/LanguageSwitcher'
import { cn } from '@/ember/lib/cn'
import { GeneralSection } from '@/ember/pages/settings/sections/GeneralSection'
import { ModelSection } from '@/ember/pages/settings/sections/ModelSection'
import { TranscriberSection } from '@/ember/pages/settings/sections/TranscriberSection'
import { OcrSection } from '@/ember/pages/settings/sections/OcrSection'
import { MediaSection } from '@/ember/pages/settings/sections/MediaSection'
import { DownloadSection } from '@/ember/pages/settings/sections/DownloadSection'
import { MonitorSection } from '@/ember/pages/settings/sections/MonitorSection'
import { AboutSection } from '@/ember/pages/settings/sections/AboutSection'

type SectionDef = { id: string; labelKey: MessageKey; icon: React.ReactNode }

const SECTIONS: SectionDef[] = [
  { id: 'general', labelKey: 'settings.general', icon: <SlidersHorizontal className="size-4" /> },
  { id: 'model', labelKey: 'settings.model', icon: <Cpu className="size-4" /> },
  { id: 'transcriber', labelKey: 'settings.transcriber', icon: <AudioLines className="size-4" /> },
  { id: 'ocr', labelKey: 'settings.ocr', icon: <ScanText className="size-4" /> },
  { id: 'media', labelKey: 'settings.media', icon: <HardDrive className="size-4" /> },
  { id: 'download', labelKey: 'settings.download', icon: <DownloadIcon className="size-4" /> },
  { id: 'monitor', labelKey: 'settings.monitor', icon: <Activity className="size-4" /> },
  { id: 'about', labelKey: 'settings.about', icon: <Info className="size-4" /> },
]

/**
 * Settings. The section list is a horizontal scroll strip on narrow screens and
 * a vertical list beside the content on wide ones — the same DOM, no duplicate
 * markup, so a viewport change never remounts a section and drops form state.
 */
export default function SettingsPage() {
  const { t } = useI18n()

  return (
    <AppShell
      nav={[
        { to: '/', label: t('nav.workspace'), icon: <FileText className="size-4" />, end: true },
        { to: '/settings', label: t('nav.settings'), icon: <SettingsIcon className="size-4" /> },
      ]}
      sidebarFooter={<LanguageSwitcher />}
    >
      <div className="flex flex-col gap-6">
        <header className="flex flex-col gap-1">
          <h1 className="font-display text-section leading-tight">{t('settings.title')}</h1>
          <p className="text-small text-ink-soft">{t('settings.subtitle')}</p>
        </header>

        <div className="flex min-w-0 flex-col gap-6 lg:flex-row lg:gap-8">
          <nav
            aria-label={t('settings.title')}
            className="ember-scroll-fade-x -mx-4 flex shrink-0 gap-1 overflow-x-auto px-4 pb-1 lg:mx-0 lg:w-56 lg:flex-col lg:overflow-visible lg:px-0 lg:[mask-image:none]"
          >
            {SECTIONS.map(section => (
              <NavLink
                key={section.id}
                to={`/settings/${section.id}`}
                className={({ isActive }) =>
                  cn(
                    'ember-press flex shrink-0 items-center gap-2.5 rounded-control px-3 py-2 text-small font-semibold whitespace-nowrap',
                    isActive ? 'bg-ember-soft text-ember' : 'text-ink-soft hover:bg-surface hover:text-ink',
                  )
                }
              >
                <span className="shrink-0">{section.icon}</span>
                {t(section.labelKey)}
              </NavLink>
            ))}
          </nav>

          <div className="min-w-0 flex-1">
            <Routes>
              <Route index element={<Navigate to="general" replace />} />
              <Route path="general" element={<GeneralSection />} />
              <Route path="model" element={<ModelSection />} />
              <Route path="transcriber" element={<TranscriberSection />} />
              <Route path="ocr" element={<OcrSection />} />
              <Route path="media" element={<MediaSection />} />
              <Route path="download" element={<DownloadSection />} />
              <Route path="monitor" element={<MonitorSection />} />
              <Route path="about" element={<AboutSection />} />
              <Route path="*" element={<Navigate to="general" replace />} />
            </Routes>
          </div>
        </div>
      </div>
    </AppShell>
  )
}
