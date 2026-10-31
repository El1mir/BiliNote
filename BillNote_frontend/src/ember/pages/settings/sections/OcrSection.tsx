import { useState } from 'react'
import toast from 'react-hot-toast'
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
import { SettingRow, SettingsSection } from '@/ember/pages/settings/Section'

/** OCR assist. A failed test shows the upstream body verbatim — that is the only useful diagnostic. */
export function OcrSection() {
  const { t } = useI18n()
  const { data, loading, reload } = useAsync(getOcrConfig)
  const [draft, setDraft] = useState<OcrConfigInput>({})
  const [testing, setTesting] = useState(false)
  const [saving, setSaving] = useState(false)
  const [result, setResult] = useState<OcrTestResult | null>(null)

  const enabled = draft.enabled ?? data?.enabled ?? false
  const value = <K extends keyof OcrConfigInput>(key: K): string =>
    String(draft[key] ?? data?.[key as keyof typeof data] ?? '')

  const patch = (next: OcrConfigInput) => setDraft(current => ({ ...current, ...next }))

  const save = async () => {
    setSaving(true)
    try {
      await updateOcrConfig(draft)
      toast.success(t('settings.saved'))
      setDraft({})
      reload()
    } catch {
      toast.error(t('settings.saveFailed'))
    } finally {
      setSaving(false)
    }
  }

  const test = async () => {
    setTesting(true)
    setResult(null)
    try {
      setResult(await testOcrConfig(draft))
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

  return (
    <SettingsSection
      title={t('settings.ocr')}
      description={t('settings.ocr.enabledHint')}
      actions={
        <div className="flex items-center gap-2">
          <Button size="sm" variant="secondary" onClick={test} loading={testing}>
            {t('settings.ocr.test')}
          </Button>
          <Button size="sm" variant="primary" onClick={save} loading={saving}>
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
                <Switch checked={enabled} label={t('settings.ocr.enabled')} onChange={next => patch({ enabled: next })} />
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
                onChange={event => patch({ base_url: event.target.value })}
              />
            </Field>
            <Field label={t('settings.ocr.apiKey')} htmlFor="ocr-key">
              <Input
                id="ocr-key"
                type="password"
                value={value('api_key')}
                onChange={event => patch({ api_key: event.target.value })}
              />
            </Field>
            <Field label={t('settings.ocr.model')} htmlFor="ocr-model">
              <Input
                id="ocr-model"
                value={value('model_name')}
                placeholder={data?._defaults.model_name}
                onChange={event => patch({ model_name: event.target.value })}
              />
            </Field>
            <Field label="timeout" htmlFor="ocr-timeout">
              <Input
                id="ocr-timeout"
                type="number"
                min={1}
                value={value('timeout')}
                onChange={event => patch({ timeout: Number(event.target.value) })}
              />
            </Field>
            <Field label="max_file_mb" htmlFor="ocr-size">
              <Input
                id="ocr-size"
                type="number"
                min={1}
                value={value('max_file_mb')}
                onChange={event => patch({ max_file_mb: Number(event.target.value) })}
              />
            </Field>
            <Field label="max_pages" htmlFor="ocr-pages">
              <Input
                id="ocr-pages"
                type="number"
                min={1}
                value={value('max_pages')}
                onChange={event => patch({ max_pages: Number(event.target.value) })}
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
