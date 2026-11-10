import { useState } from 'react'
import { CloudDownload, Plus, Trash2 } from 'lucide-react'
import toast from 'react-hot-toast'
import {
  addModel,
  deleteModelById,
  fetchEnableModelById,
  fetchModels,
  testConnection,
  type ProviderSummary,
  type RemoteModelList,
  type SavedModel,
} from '@/services/model'
import { useAsync } from '@/ember/lib/useAsync'
import { useI18n } from '@/ember/i18n/context'
import { Badge } from '@/ember/ui/Badge'
import { Button } from '@/ember/ui/Button'
import { Input } from '@/ember/ui/Input'
import { globalModelValue } from '@/utils/globalModel'

type ProviderModelsProps = {
  provider: ProviderSummary
  /** 当前全局模型的 value（providerId::modelName）；空串表示还没选。 */
  activeModelValue: string
  onActivate: (value: string) => void
  onChanged: () => void
}

/**
 * Models under one provider. Two sources, deliberately kept apart:
 *
 *  - saved models are what this app will actually offer when generating notes;
 *  - the provider list is what the endpoint reports, fetched on demand because it is a
 *    live network call to a third party and should not run just because a row opened.
 *
 * Typing a name by hand stays available — plenty of gateways do not implement /models.
 */
export function ProviderModels({
  provider,
  activeModelValue,
  onActivate,
  onChanged,
}: ProviderModelsProps) {
  const { t } = useI18n()
  const saved = useAsync(() => fetchEnableModelById(provider.id), [provider.id])
  const [remote, setRemote] = useState<RemoteModelList | null>(null)
  const [filter, setFilter] = useState('')
  const [fetching, setFetching] = useState(false)
  const [draft, setDraft] = useState('')
  const [busy, setBusy] = useState(false)
  /** 连接测试是真实往服务商发一次请求，实测 30–50s；期间按钮必须锁住。 */
  const [testing, setTesting] = useState(false)

  const models: SavedModel[] = saved.data ?? []

  // 全局模型是「某个服务商下的某个模型」，所以同一个模型名在别的服务商下不算命中
  const isGlobal = (modelName: string) =>
    globalModelValue(provider.id, modelName) === activeModelValue
  const savedNames = new Set(models.map(model => model.model_name))
  // A gateway can advertise a hundred-plus models; the panel stays scrollable and
  // filterable rather than pushing the provider card thousands of pixels tall.
  const needle = filter.trim().toLowerCase()
  const available = (remote?.models ?? []).filter(
    model =>
      model.id && !savedNames.has(model.id) && (!needle || model.id.toLowerCase().includes(needle))
  )

  const loadRemote = async () => {
    setFetching(true)
    try {
      const result = await fetchModels(provider.id)
      setRemote(result)
      if (result.error) toast.error(t('settings.model.fetchFailed', { message: result.error }))
    } catch {
      toast.error(t('settings.model.fetchFailed', { message: '' }))
    } finally {
      setFetching(false)
    }
  }

  const add = async (modelName: string) => {
    const name = modelName.trim()
    if (!name) return
    setBusy(true)
    try {
      await addModel({ provider_id: provider.id, model_name: name })
      setDraft('')
      toast.success(t('settings.saved'))
      saved.reload()
      onChanged()
    } catch {
      toast.error(t('settings.saveFailed'))
    } finally {
      setBusy(false)
    }
  }

  const remove = async (modelId: number) => {
    try {
      await deleteModelById(modelId)
      saved.reload()
      onChanged()
    } catch {
      toast.error(t('settings.saveFailed'))
    }
  }

  const test = async () => {
    if (testing) return
    setTesting(true)
    try {
      await testConnection({ provider_id: provider.id })
      toast.success(t('settings.model.connected'))
    } catch {
      toast.error(t('settings.model.connectFailed'))
    } finally {
      setTesting(false)
    }
  }

  return (
    <div className="ember-enter border-line flex flex-col gap-3 border-t px-4 py-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="ember-overline">{t('settings.model.models')}</span>
        <div className="flex items-center gap-2">
          <Button
            size="sm"
            variant="ghost"
            onClick={test}
            loading={testing}
            disabled={testing}
            title={t('settings.model.testConnectionBusy')}
          >
            {testing ? t('settings.model.testing') : t('settings.model.testConnection')}
          </Button>
          <Button size="sm" variant="secondary" onClick={loadRemote} loading={fetching}>
            <CloudDownload className="size-3.5" />
            {t('settings.model.fetchModels')}
          </Button>
        </div>
      </div>

      {saved.loading && !saved.data ? (
        <span className="text-caption text-ink-mute">{t('common.loading')}</span>
      ) : models.length ? (
        <ul className="flex flex-col gap-1.5">
          {models.map(model => (
            <li
              key={model.id}
              className="rounded-control bg-surface flex items-center justify-between gap-2 px-3 py-2"
            >
              <span className="flex min-w-0 flex-1 items-center gap-2">
                <span className="text-caption text-ink truncate font-mono">{model.model_name}</span>
                {isGlobal(model.model_name) ? (
                  <Badge tone="ember">{t('settings.model.globalBadge')}</Badge>
                ) : (
                  <button
                    type="button"
                    onClick={() => onActivate(globalModelValue(provider.id, model.model_name))}
                    className="rounded-control text-caption text-ink-mute hover:bg-raised hover:text-primary shrink-0 px-1.5 py-0.5 transition-colors duration-[var(--dur-hover)] ease-[var(--ease)]"
                  >
                    {t('settings.model.useAsGlobal')}
                  </button>
                )}
              </span>
              <button
                type="button"
                aria-label={t('common.delete')}
                onClick={() => void remove(model.id)}
                className="ember-press rounded-control text-ink-mute hover:bg-raised hover:text-danger inline-flex size-11 shrink-0 items-center justify-center"
              >
                <Trash2 className="size-3.5" />
              </button>
            </li>
          ))}
        </ul>
      ) : (
        <span className="text-caption text-ink-mute">{t('settings.model.emptyModels')}</span>
      )}

      {remote ? (
        <div className="rounded-control border-line flex flex-col gap-2 border px-3 py-2.5">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <span className="ember-overline">
              {t('settings.model.available')} · {available.length}
            </span>
            <Input
              value={filter}
              onChange={event => setFilter(event.target.value)}
              placeholder={t('common.search')}
              aria-label={t('settings.model.available')}
              className="h-8 w-40"
            />
          </div>
          {available.length ? (
            <div className="ember-scroll-fade flex max-h-64 flex-col gap-1 overflow-y-auto pr-1">
              {available.map(model => (
                <div key={model.id} className="flex items-center justify-between gap-2">
                  <span className="text-caption text-ink-soft truncate font-mono">{model.id}</span>
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => void add(model.id)}
                    disabled={busy}
                  >
                    <Plus className="size-3" />
                    {t('settings.model.addModel')}
                  </Button>
                </div>
              ))}
            </div>
          ) : (
            <span className="text-caption text-ink-mute">
              {remote.models.length
                ? t('settings.model.allAdded')
                : t('settings.model.noRemoteModels')}
            </span>
          )}
        </div>
      ) : null}

      <div className="flex items-center gap-2">
        <Input
          value={draft}
          onChange={event => setDraft(event.target.value)}
          placeholder={t('settings.model.modelName')}
          aria-label={t('settings.model.modelName')}
          className="h-9"
          onKeyDown={event => {
            if (event.key === 'Enter') {
              event.preventDefault()
              void add(draft)
            }
          }}
        />
        <Button
          size="sm"
          variant="secondary"
          onClick={() => void add(draft)}
          loading={busy}
          disabled={!draft.trim()}
        >
          <Plus className="size-3.5" />
          {t('settings.model.addModel')}
        </Button>
      </div>
    </div>
  )
}
