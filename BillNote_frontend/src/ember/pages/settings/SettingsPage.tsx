import { useSyncExternalStore } from 'react'
import { NavLink, Navigate, Route, Routes, useLocation, useNavigate } from 'react-router-dom'
import { FileText, Settings as SettingsIcon } from 'lucide-react'
import { useI18n } from '@/ember/i18n/context'
import { AppShell } from '@/ember/shell/AppShell'
import { LanguageSwitcher } from '@/ember/shell/LanguageSwitcher'
import { cn } from '@/ember/lib/cn'
import { Select } from '@/ember/ui/Select'
import { GeneralSection } from '@/ember/pages/settings/sections/GeneralSection'
import { ModelSection } from '@/ember/pages/settings/sections/ModelSection'
import { TranscriberSection } from '@/ember/pages/settings/sections/TranscriberSection'
import { OcrSection } from '@/ember/pages/settings/sections/OcrSection'
import { PromptSection } from '@/ember/pages/settings/sections/PromptSection'
import { MediaSection } from '@/ember/pages/settings/sections/MediaSection'
import { DownloadSection } from '@/ember/pages/settings/sections/DownloadSection'
import { MonitorSection } from '@/ember/pages/settings/sections/MonitorSection'
import { ProxySection } from '@/ember/pages/settings/sections/ProxySection'
import { AboutSection } from '@/ember/pages/settings/sections/AboutSection'
import { useUnsavedCount } from '@/ember/pages/settings/useSectionDraft'
import {
  SECTIONS,
  sectionIdFromPath,
  sectionOptions,
  type SectionDef,
  type SectionId,
} from '@/ember/pages/settings/sections'
import {
  draftsVersion,
  draftKeys,
  subscribeDrafts,
} from '@/ember/pages/settings/drafts'

/** 单个分区项：草稿角标要订阅仓库，所以这里必须是组件（hook 不能在 map 回调里用）。 */
export function SectionLink({ section }: { section: SectionDef }) {
  const { t } = useI18n()
  const dirty = useDraftKeys()

  return (
    <NavLink
      to={`/settings/${section.id}`}
      className={({ isActive }) =>
        cn(
          'ember-press flex min-h-11 shrink-0 items-center gap-2.5 rounded-control px-3 py-2 text-small font-semibold whitespace-nowrap',
          isActive ? 'bg-primary-soft text-primary' : 'text-ink-soft hover:bg-surface hover:text-ink',
        )
      }
    >
      <section.icon className="size-4 shrink-0" aria-hidden="true" />
      {t(section.labelKey)}
      {dirty.has(section.id) ? (
        <span
          role="status"
          aria-label={t('settings.unsavedBadge')}
          title={t('settings.unsavedBadge')}
          className="ml-auto size-1.5 shrink-0 rounded-full bg-warn"
        />
      ) : null}
    </NavLink>
  )
}

function useDraftKeys(): ReadonlySet<string> {
  useSyncExternalStore(subscribeDrafts, draftsVersion, () => 0)
  return new Set(draftKeys())
}

/**
 * 分区导航：宽屏是左侧竖排列表，窄屏收成原生下拉。
 *
 * 以前窄屏是横向滚动条——10 个分区只露出前 3 个，用户得先猜右边还有东西。
 * 原生 select 一颗控件装下全部选项、自带键盘与移动端行为，且不需要额外的
 * 抽屉状态。两条分支都只切路由；分区切换不卸载草稿（drafts 仓库在 React 之外）。
 */
export function SettingsNav({ current }: { current: SectionId }) {
  const { t } = useI18n()
  const navigate = useNavigate()
  const dirty = useDraftKeys()

  return (
    <>
      <div className="lg:hidden">
        <label htmlFor="settings-section" className="sr-only">
          {t('settings.title')}
        </label>
        <Select
          id="settings-section"
          className="h-11"
          value={current}
          options={sectionOptions(t, dirty)}
          onChange={event => navigate(`/settings/${event.target.value}`)}
        />
      </div>

      <nav
        aria-label={t('settings.title')}
        className="hidden shrink-0 flex-col gap-1 lg:flex lg:w-56"
      >
        {SECTIONS.map(section => (
          <SectionLink key={section.id} section={section} />
        ))}
      </nav>
    </>
  )
}

export default function SettingsPage() {
  const { t } = useI18n()
  const unsaved = useUnsavedCount()
  const location = useLocation()
  const current = sectionIdFromPath(location.pathname)

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
          {unsaved ? (
            <p className="text-caption text-warn">{t('settings.unsavedHint', { count: unsaved })}</p>
          ) : null}
        </header>

        <div className="flex min-w-0 flex-col gap-6 lg:flex-row lg:gap-8">
          <SettingsNav current={current} />

          {/* 触控设备上输入框也要 44px：tokens.css 的 coarse 规则只兜了 button/select，
              设置页表单几乎全是 input，所以在这里按 pointer 类型补一刀。 */}
          <div className="min-w-0 flex-1 pointer-coarse:[&_input]:min-h-11 pointer-coarse:[&_textarea]:min-h-11">
            <Routes>
              <Route index element={<Navigate to="general" replace />} />
              <Route path="general" element={<GeneralSection />} />
              <Route path="model" element={<ModelSection />} />
              <Route path="transcriber" element={<TranscriberSection />} />
              <Route path="ocr" element={<OcrSection />} />
              <Route path="prompt" element={<PromptSection />} />
              <Route path="media" element={<MediaSection />} />
              <Route path="download" element={<DownloadSection />} />
              <Route path="proxy" element={<ProxySection />} />
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
