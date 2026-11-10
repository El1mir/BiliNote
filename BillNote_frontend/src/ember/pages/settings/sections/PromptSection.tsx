import { useState } from 'react'
import { Braces, Eye, EyeOff, RotateCcw } from 'lucide-react'
import { getGeneralSettings, updateGeneralSettings } from '@/services/general'
import { useAsync } from '@/ember/lib/useAsync'
import { useI18n } from '@/ember/i18n/context'
import { Badge } from '@/ember/ui/Badge'
import { Button } from '@/ember/ui/Button'
import { Card } from '@/ember/ui/Card'
import { Dialog } from '@/ember/ui/Dialog'
import { Field } from '@/ember/ui/Field'
import { Textarea } from '@/ember/ui/Input'
import { Skeleton } from '@/ember/ui/Skeleton'
import { SaveStatus, SettingsLoadError, SettingsSection } from '@/ember/pages/settings/Section'
import { useSaveFeedback } from '@/ember/pages/settings/saveFeedback'
import { useSectionDraft } from '@/ember/pages/settings/useSectionDraft'

/** 草稿在设置页内跨分区保留时用的 key。 */
const DRAFT_KEY = 'prompt'

/**
 * Base prompt editing (spec 005 ticket 11).
 *
 * Two rules shape this screen:
 *
 * 1. **Empty means "use the built-in template".** That is also what the restore
 *    button sends, so the draft is a plain string and never null.
 * 2. **Every required placeholder must survive.** The backend silently rejects a
 *    template that is missing one (it would drop the title or the whole transcript
 *    from the prompt), so the screen blocks the save and says which ones are absent
 *    instead of letting the value disappear without explanation.
 */
export function PromptSection() {
  const { t } = useI18n()
  const { data, loading, error, reload } = useAsync(getGeneralSettings)
  // 草稿放仓库：切到别的分区再回来，未保存的模板还在（undefined = 没有改动）。
  const [draft, setDraft] = useSectionDraft<string>(DRAFT_KEY)
  const { state: saveState, saving, run: runSave } = useSaveFeedback()
  const [showDefault, setShowDefault] = useState(false)

  const value = draft ?? data?.base_prompt_override ?? ''
  const limit = data?.base_prompt_override_limit ?? 20000
  const required = data?.base_prompt_required_placeholders ?? []
  const missing = required.filter(name => !value.includes('{' + name + '}'))
  const tooLong = value.length > limit
  const invalid = missing.length > 0 || tooLong

  const save = async () => {
    // 读失败时 data 为空，value 会是空串；照常保存就会用空串覆盖 base_prompt_override。
    if (error) return
    await runSave(async () => {
      await updateGeneralSettings({ base_prompt_override: value })
      setDraft(undefined)
      reload()
    })
  }

  /** 恢复默认只改本地草稿，但会把整段自定义模板从眼前抹掉，所以先确认。 */
  const [confirmingRestore, setConfirmingRestore] = useState(false)
  const canRestore = value.trim().length > 0

  const restore = () => {
    // Deliberately local: nothing is written until Save, matching every other section.
    setDraft('')
    setConfirmingRestore(false)
  }

  if (loading && !data) return <Skeleton className="h-72 w-full" />

  if (error) {
    return (
      <SettingsSection title={t('settings.prompt')} description={t('settings.prompt.description')}>
        <SettingsLoadError onRetry={reload} />
      </SettingsSection>
    )
  }

  return (
    <SettingsSection
      title={t('settings.prompt')}
      description={t('settings.prompt.description')}
      actions={
        <div className="flex items-center gap-2">
          <SaveStatus state={saveState} />
          <Button
            size="sm"
            variant="secondary"
            onClick={() => setConfirmingRestore(true)}
            disabled={!canRestore}
          >
            <RotateCcw className="size-3.5" />
            {t('settings.prompt.restore')}
          </Button>
          <Button size="sm" variant="primary" onClick={save} loading={saving} disabled={invalid || Boolean(error)}>
            {t('common.save')}
          </Button>
        </div>
      }
    >
      <div className="flex flex-col gap-4">
        <Card className="bg-canvas p-4 sm:p-5">
          <div className="flex flex-col gap-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <Field label={t('settings.prompt.override')} htmlFor="base-prompt" className="flex-1">
                <Textarea
                  id="base-prompt"
                  rows={14}
                  className="font-mono text-caption"
                  value={value}
                  placeholder={t('settings.prompt.placeholder')}
                  onChange={event => setDraft(event.target.value)}
                />
              </Field>
            </div>

            <div className="flex flex-wrap items-center gap-2">
              <Badge tone={value.trim() ? 'ember' : 'neutral'}>
                <Braces className="size-3" />
                {value.trim() ? t('settings.prompt.usingCustom') : t('settings.prompt.usingDefault')}
              </Badge>
              <span className="text-caption text-ink-soft">
                {t('settings.prompt.chars', { current: value.length, limit })}
              </span>
              {tooLong ? <Badge tone="danger">{t('settings.prompt.tooLong', { limit, current: value.length })}</Badge> : null}
              {missing.length > 0 ? (
                <Badge tone="danger">
                  {t('settings.prompt.missing', { names: missing.map(name => '{' + name + '}').join(', ') })}
                </Badge>
              ) : null}
            </div>

            <p className="text-caption text-ink-soft">{t('settings.prompt.overrideHint')}</p>
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-caption text-ink-soft">{t('settings.prompt.required')}</span>
              {required.map(name => (
                <Badge key={name} tone={missing.includes(name) ? 'danger' : 'success'}>
                  {'{' + name + '}'}
                </Badge>
              ))}
            </div>
          </div>
        </Card>

        <Card className="bg-canvas p-4 sm:p-5">
          <div className="flex flex-col gap-3">
            <Button
              size="sm"
              variant="ghost"
              onClick={() => setShowDefault(current => !current)}
              className="self-start"
            >
              {showDefault ? <EyeOff className="size-3.5" /> : <Eye className="size-3.5" />}
              {showDefault ? t('settings.prompt.hideDefault') : t('settings.prompt.viewDefault')}
            </Button>
            {showDefault ? (
              <div className="flex flex-col gap-2">
                <span className="text-caption text-ink-soft">{t('settings.prompt.defaultTitle')}</span>
                <pre className="max-h-72 overflow-auto rounded-control bg-surface p-3 font-mono text-caption whitespace-pre-wrap text-ink-soft">
                  {data?.base_prompt_default ?? ''}
                </pre>
              </div>
            ) : null}
          </div>
        </Card>
      </div>

      <Dialog
        open={confirmingRestore}
        onClose={() => setConfirmingRestore(false)}
        size="sm"
        title={t('settings.prompt.restoreConfirmTitle')}
        description={t('settings.prompt.restoreConfirmBody')}
        footer={
          <div className="flex items-center gap-2">
            <Button size="sm" variant="secondary" onClick={() => setConfirmingRestore(false)}>
              {t('common.cancel')}
            </Button>
            <Button size="sm" variant="destructive" onClick={restore}>
              {t('settings.prompt.restoreConfirmAction')}
            </Button>
          </div>
        }
      >
        <p className="text-small text-ink-soft">{t('settings.prompt.restoreConfirmHint')}</p>
      </Dialog>
    </SettingsSection>
  )
}
