import { Globe, Info } from 'lucide-react'
import { getProxyConfig, updateProxyConfig } from '@/services/proxy'
import { canSaveProxy, proxyUrlError, type ProxyDraft } from '@/ember/pages/settings/proxyUrl'
import { useAsync } from '@/ember/lib/useAsync'
import { useI18n } from '@/ember/i18n/context'
import { Badge } from '@/ember/ui/Badge'
import { Button } from '@/ember/ui/Button'
import { Card } from '@/ember/ui/Card'
import { Field } from '@/ember/ui/Field'
import { Input } from '@/ember/ui/Input'
import { Skeleton } from '@/ember/ui/Skeleton'
import { Switch } from '@/ember/ui/Switch'
import { SaveStatus, SettingsLoadError, SettingRow, SettingsSection } from '@/ember/pages/settings/Section'
import { useSectionDraft } from '@/ember/pages/settings/useSectionDraft'
import { useSaveFeedback } from '@/ember/pages/settings/saveFeedback'

/** 草稿在设置页内跨分区保留时用的 key。 */
const DRAFT_KEY = 'proxy'

/**
 * 代理配置（上游 UI 计划 §4 F2 的人裁决：后端早有 /proxy_config 与 settings.proxy.* 的
 * 需求，但设置页一直没有入口，用户只能改环境变量）。
 *
 * 契约按后端 ProxyConfigManager：GET 回 {enabled, url, effective}，
 * POST 收 {enabled, url}；effective 是"实际生效"的值（配置为空时可能是环境变量兜底），
 * 所以两者要分开显示 —— 否则用户会以为填了没生效。
 */
export function ProxySection() {
  const { t } = useI18n()
  const { data, loading, error, reload } = useAsync(getProxyConfig)
  const [draft, setDraft] = useSectionDraft<ProxyDraft>(DRAFT_KEY)
  const { state: saveState, saving, run: runSave } = useSaveFeedback()

  // draft !== undefined 表示用户改过（url 允许为空串）；没改过就跟随后端值。
  const current: ProxyDraft = draft ?? { enabled: data?.enabled ?? false, url: data?.url ?? '' }
  const invalid = current.enabled ? proxyUrlError(current.url) : null

  const save = async () => {
    if (error || !canSaveProxy(current)) return
    await runSave(async () => {
      await updateProxyConfig({ enabled: current.enabled, url: current.url })
      setDraft(undefined)
      reload()
    })
  }

  if (loading && !data) return <Skeleton className="h-64 w-full" />

  if (error) {
    return (
      <SettingsSection title={t('settings.proxy')} description={t('settings.proxy.description')}>
        <SettingsLoadError onRetry={reload} />
      </SettingsSection>
    )
  }

  const errorText =
    invalid === 'empty'
      ? t('settings.proxy.errorEmpty')
      : invalid === 'scheme'
        ? t('settings.proxy.errorScheme')
        : invalid === 'malformed'
          ? t('settings.proxy.errorMalformed')
          : null

  return (
    <SettingsSection
      title={t('settings.proxy')}
      description={t('settings.proxy.description')}
      actions={
        <>
          <SaveStatus state={saveState} />
          <Button
            variant="primary"
            size="sm"
            onClick={save}
            loading={saving}
            disabled={Boolean(error) || !canSaveProxy(current)}
          >
            {t('common.save')}
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-4">
        <Card className="bg-canvas px-4 sm:px-5">
          <SettingRow
            label={t('settings.proxy.enabled')}
            hint={t('settings.proxy.enabledHint')}
            control={
              <Switch
                checked={current.enabled}
                label={t('settings.proxy.enabled')}
                onChange={enabled => setDraft({ ...current, enabled })}
              />
            }
          />
          <SettingRow
            label={t('settings.proxy.url')}
            hint={t('settings.proxy.urlHint')}
            control={
              <Field label={t('settings.proxy.url')} error={errorText ?? undefined} htmlFor="proxy-url">
                <Input
                  id="proxy-url"
                  value={current.url}
                  spellCheck={false}
                  placeholder="http://127.0.0.1:7890"
                  onChange={event => setDraft({ ...current, url: event.target.value })}
                />
              </Field>
            }
          />
        </Card>

        <Card className="bg-canvas p-4 sm:p-5">
          <div className="flex flex-wrap items-center gap-2">
            <Globe className="size-4 text-ink-mute" />
            <span className="ember-overline">{t('settings.proxy.effective')}</span>
            {data?.effective ? (
              <Badge tone="success">{data.effective}</Badge>
            ) : (
              <Badge tone="neutral">{t('settings.proxy.effectiveNone')}</Badge>
            )}
          </div>
          <p className="mt-2 flex items-start gap-2 text-caption text-ink-soft">
            <Info className="mt-0.5 size-3.5 shrink-0" />
            {t('settings.proxy.effectiveHint')}
          </p>
        </Card>
      </div>
    </SettingsSection>
  )
}
