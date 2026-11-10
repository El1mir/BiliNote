import { useState } from 'react'
import { CheckCircle2, ScanText, XCircle } from 'lucide-react'
import { getOcrConfig, testOcrConfig, updateOcrConfig, type OcrConfigInput, type OcrTestResult } from '@/services/ocr'
import { useAsync } from '@/ember/lib/useAsync'
import { useI18n } from '@/ember/i18n/context'
import { Badge } from '@/ember/ui/Badge'
import { Button } from '@/ember/ui/Button'
import { Card } from '@/ember/ui/Card'
import { Field } from '@/ember/ui/Field'
import { Input } from '@/ember/ui/Input'
import { Skeleton } from '@/ember/ui/Skeleton'
import { Switch } from '@/ember/ui/Switch'
import { SaveStatus, SettingRow, SettingsLoadError, SettingsSection } from '@/ember/pages/settings/Section'
import { useSectionDraft } from '@/ember/pages/settings/useSectionDraft'
import { useSaveFeedback } from '@/ember/pages/settings/saveFeedback'

/** 草稿在设置页内跨分区保留时用的 key。 */
const DRAFT_KEY = 'ocr'

/** OCR assist. A failed test shows the upstream body verbatim — that is the only useful diagnostic. */
export function OcrSection() {
  const { t } = useI18n()
  const { data, loading, error, reload } = useAsync(getOcrConfig)
  // 草稿跨分区保留（切走再切回不丢未保存的 OCR 改动）。
  const [draft, setDraft] = useSectionDraft<OcrConfigInput>(DRAFT_KEY)
  const [testing, setTesting] = useState(false)
  const { state: saveState, saving, run: runSave } = useSaveFeedback()
  const [result, setResult] = useState<OcrTestResult | null>(null)

  const patch: OcrConfigInput = draft ?? {}
  const enabled = patch.enabled ?? data?.enabled ?? false
  const value = <K extends keyof OcrConfigInput>(key: K): string =>
    String(patch[key] ?? data?.[key as keyof typeof data] ?? '')

  const setPatch = (next: OcrConfigInput) => setDraft(current => ({ ...current, ...next }))

  const save = async () => {
    // 读失败时 patch 是全空，保存等于把服务商地址/密钥清空，所以直接拦住。
    if (error) return
    await runSave(async () => {
      await updateOcrConfig(patch)
      setDraft(undefined)
      reload()
    })
  }

  const test = async () => {
    setTesting(true)
    setResult(null)
    try {
      setResult(await testOcrConfig(patch))
    } catch (error) {
      setResult({
        ok: false,
        message: t('settings.saveFailed'),
        detail: String((error as { message?: string })?.message ?? error),
        code: null,
        status_code: null,
      })
    } finally {
      setTesting(false)
    }
  }

  if (loading && !data) return <Skeleton className="h-72 w-full" />

  if (error) {
    return (
      <SettingsSection title={t('settings.ocr')} description={t('settings.ocr.enabledHint')}>
        <SettingsLoadError onRetry={reload} />
      </SettingsSection>
    )
  }

  return (
    <SettingsSection
      title={t('settings.ocr')}
      description={t('settings.ocr.enabledHint')}
      actions={
        <div className="flex items-center gap-2">
          <SaveStatus state={saveState} />
          <Button
            size="sm"
            variant="secondary"
            onClick={test}
            loading={testing}
            aria-busy={testing}
          >
            {t('settings.ocr.test')}
          </Button>
          <Button size="sm" variant="primary" onClick={save} loading={saving} disabled={Boolean(error)}>
            {t('common.save')}
          </Button>
        </div>
      }
    >
      <div className="flex flex-col gap-4">
        <Card className="bg-canvas px-4 sm:px-5">
          <SettingRow
            label={t('settings.ocr.enabled')}
            hint={t('settings.ocr.enabledHint')}
            control={
              <div className="flex justify-start sm:justify-end">
                <Switch checked={enabled} label={t('settings.ocr.enabled')} onChange={next => setPatch({ enabled: next })} />
              </div>
            }
          />
        </Card>

        {!enabled ? (
          <p className="flex items-center gap-2 text-caption text-ink-soft">
            <ScanText className="size-3.5" />
            {t('settings.ocr.disabledHint')}
          </p>
        ) : null}

        <Card className="bg-canvas p-4 sm:p-5">
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label={t('settings.ocr.endpoint')} htmlFor="ocr-url" className="sm:col-span-2">
              <Input
                id="ocr-url"
                value={value('base_url')}
                placeholder={data?._defaults.base_url}
                onChange={event => setPatch({ base_url: event.target.value })}
              />
            </Field>
            <Field label={t('settings.ocr.apiKey')} htmlFor="ocr-key">
              <Input
                id="ocr-key"
                type="password"
                value={value('api_key')}
                onChange={event => setPatch({ api_key: event.target.value })}
              />
            </Field>
            <Field label={t('settings.ocr.model')} htmlFor="ocr-model">
              <Input
                id="ocr-model"
                value={value('model_name')}
                placeholder={data?._defaults.model_name}
                onChange={event => setPatch({ model_name: event.target.value })}
              />
            </Field>
            <Field label="timeout" htmlFor="ocr-timeout">
              <Input
                id="ocr-timeout"
                type="number"
                min={1}
                value={value('timeout')}
                onChange={event => setPatch({ timeout: Number(event.target.value) })}
              />
            </Field>
            <Field label="max_file_mb" htmlFor="ocr-size">
              <Input
                id="ocr-size"
                type="number"
                min={1}
                value={value('max_file_mb')}
                onChange={event => setPatch({ max_file_mb: Number(event.target.value) })}
              />
            </Field>
            <Field label="max_pages" htmlFor="ocr-pages">
              <Input
                id="ocr-pages"
                type="number"
                min={1}
                value={value('max_pages')}
                onChange={event => setPatch({ max_pages: Number(event.target.value) })}
              />
            </Field>
          </div>
        </Card>

        {result ? (
          <Card className="ember-enter bg-canvas p-4 sm:p-5">
            <div className="flex flex-col gap-2">
              <span className="flex items-center gap-2">
                {result.ok ? (
                  <Badge tone="success">
                    <CheckCircle2 className="size-3" />
                    {result.message}
                  </Badge>
                ) : (
                  <Badge tone="danger">
                    <XCircle className="size-3" />
                    {result.message}
                  </Badge>
                )}
                {!result.ok && result.status_code ? <Badge tone="neutral">{result.status_code}</Badge> : null}
              </span>
              {result.ok ? (
                <pre className="max-h-40 overflow-auto rounded-control bg-surface p-3 font-mono text-caption whitespace-pre-wrap text-ink-soft">
                  {result.preview}
                </pre>
              ) : (
                <pre className="max-h-40 overflow-auto rounded-control bg-surface p-3 font-mono text-caption whitespace-pre-wrap text-danger">
                  {result.detail}
                </pre>
              )}
            </div>
          </Card>
        ) : null}
      </div>
    </SettingsSection>
  )
}
