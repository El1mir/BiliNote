import { useState } from 'react'
import toast from 'react-hot-toast'
import { addProvider, updateProviderById, type ProviderSummary } from '@/services/model'
import { useI18n } from '@/ember/i18n/context'
import { Button } from '@/ember/ui/Button'
import { Field } from '@/ember/ui/Field'
import { Input } from '@/ember/ui/Input'
import { Select } from '@/ember/ui/Select'

/**
 * Create or edit a provider. Both flows share one form on purpose: the fields are the
 * same, and a user who just fixed a base URL should not have to retype the key.
 *
 * api_key always starts empty in edit mode. The list endpoint only ever hands out a
 * masked key, and an empty field means "leave it alone" — the backend drops keys that
 * still contain an asterisk, so a masked value can never overwrite the real one.
 */
type ProviderDialogProps = {
  provider?: ProviderSummary
  onDone: () => void
}

const TYPES = [
  { value: 'openai', label: 'openai-compatible' },
  { value: 'ollama', label: 'Ollama' },
  { value: 'anthropic', label: 'Anthropic' },
  { value: 'gemini', label: 'Gemini' },
]

export function ProviderDialog({ provider, onDone }: ProviderDialogProps) {
  const { t } = useI18n()
  const editing = Boolean(provider)
  const [name, setName] = useState(provider?.name ?? '')
  const [baseUrl, setBaseUrl] = useState(provider?.base_url ?? '')
  const [apiKey, setApiKey] = useState('')
  const [type, setType] = useState(provider?.type ?? 'openai')
  const [saving, setSaving] = useState(false)

  const submit = async () => {
    if (!name.trim() || !baseUrl.trim()) return
    setSaving(true)
    try {
      if (provider) {
        await updateProviderById({
          id: provider.id,
          name: name.trim(),
          base_url: baseUrl.trim(),
          type,
          ...(apiKey.trim() ? { api_key: apiKey.trim() } : {}),
        })
      } else {
        await addProvider({ name: name.trim(), base_url: baseUrl.trim(), api_key: apiKey, type, logo: '' })
      }
      toast.success(t('settings.saved'))
      onDone()
    } catch {
      toast.error(t('settings.saveFailed'))
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <Field label={t('settings.model.providerName')} htmlFor="provider-name" required>
        <Input id="provider-name" value={name} onChange={event => setName(event.target.value)} />
      </Field>
      <Field label={t('settings.model.baseUrl')} htmlFor="provider-url" required>
        <Input
          id="provider-url"
          value={baseUrl}
          placeholder="https://api.openai.com/v1"
          onChange={event => setBaseUrl(event.target.value)}
        />
      </Field>
      <Field
        label={t('settings.model.apiKey')}
        htmlFor="provider-key"
        hint={editing ? t('settings.model.apiKeyKeep') : undefined}
      >
        <Input
          id="provider-key"
          type="password"
          autoComplete="off"
          value={apiKey}
          placeholder={editing ? provider?.api_key ?? '' : ''}
          onChange={event => setApiKey(event.target.value)}
        />
      </Field>
      <Field label={t('settings.model.type')} htmlFor="provider-type">
        <Select id="provider-type" value={type} options={TYPES} onChange={event => setType(event.target.value)} />
      </Field>
      <div className="flex justify-end gap-2">
        <Button variant="primary" onClick={submit} loading={saving} disabled={!name.trim() || !baseUrl.trim()}>
          {t('common.save')}
        </Button>
      </div>
    </div>
  )
}