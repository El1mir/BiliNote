import { useState } from 'react'
import { Pencil, Plus, Server, Zap } from 'lucide-react'
import toast from 'react-hot-toast'
import { activateGlobalModel, getGlobalModelOptions } from '@/services/general'
import { getProviderList, type ProviderSummary } from '@/services/model'
import { useAsync } from '@/ember/lib/useAsync'
import { useI18n } from '@/ember/i18n/context'
import { Button } from '@/ember/ui/Button'
import { Card } from '@/ember/ui/Card'
import { Dialog } from '@/ember/ui/Dialog'
import { EmptyState } from '@/ember/ui/EmptyState'
import { Badge } from '@/ember/ui/Badge'
import { Skeleton } from '@/ember/ui/Skeleton'
import { SettingsSection } from '@/ember/pages/settings/Section'
import { ProviderDialog } from '@/ember/pages/settings/sections/ProviderDialog'
import { ProviderModels } from '@/ember/pages/settings/sections/ProviderModels'
import { GlobalModelPicker } from '@/ember/pages/settings/sections/GlobalModelPicker'
import {
  buildGlobalModelOptions,
  globalModelValue,
  parseGlobalModelValue,
} from '@/utils/globalModel'

/**
 * Providers and their models. Provider rows expand in place rather than pushing
 * a route: the list is short, and staying put keeps the comparison easy.
 *
 * Editing reuses the create dialog. A provider row is a button (it toggles the models),
 * so the edit action is a separate control inside it — nesting buttons would break
 * keyboard activation for both.
 */
export function ModelSection() {
  const { t } = useI18n()
  const { data, loading, reload } = useAsync(getProviderList)
  const [creating, setCreating] = useState(false)
  const [editing, setEditing] = useState<ProviderSummary | null>(null)
  const [expanded, setExpanded] = useState<string | null>(null)
  const [savingGlobal, setSavingGlobal] = useState(false)
  const global = useAsync(getGlobalModelOptions)

  const providers: ProviderSummary[] = data ?? []
  const globalOptions = buildGlobalModelOptions(global.data?.providers ?? [])
  const active = global.data?.active
  const activeValue = active ? globalModelValue(active.provider_id, active.model_name) : ''

  const selectGlobal = async (value: string) => {
    const parsed = parseGlobalModelValue(value)
    if (!parsed) return
    setSavingGlobal(true)
    try {
      await activateGlobalModel(parsed.providerId, parsed.modelName)
      toast.success(t('settings.model.globalSaved'))
      global.reload()
    } catch {
      toast.error(t('settings.saveFailed'))
    } finally {
      setSavingGlobal(false)
    }
  }

  return (
    <SettingsSection
      title={t('settings.model')}
      description={t('settings.model.description')}
      actions={
        <Button size="sm" variant="primary" onClick={() => setCreating(true)}>
          <Plus className="size-3.5" />
          {t('settings.model.addProvider')}
        </Button>
      }
    >
      <GlobalModelPicker
        options={globalOptions}
        activeValue={activeValue}
        saving={savingGlobal}
        onSelect={value => void selectGlobal(value)}
      />

      {loading && !data ? (
        <div className="flex flex-col gap-3">
          <Skeleton className="h-16 w-full" />
          <Skeleton className="h-16 w-full" />
        </div>
      ) : providers.length ? (
        <div className="flex flex-col gap-3">
          {providers.map(provider => (
            <Card key={provider.id} className="bg-canvas">
              <div className="flex items-center gap-2 pr-2">
                <button
                  type="button"
                  onClick={() =>
                    setExpanded(current => (current === provider.id ? null : provider.id))
                  }
                  aria-expanded={expanded === provider.id}
                  className="flex min-w-0 flex-1 items-center gap-3 px-4 py-3.5 text-left"
                >
                  <span className="rounded-control bg-raised text-ink-soft grid size-8 shrink-0 place-items-center">
                    <Server className="size-4" />
                  </span>
                  <span className="flex min-w-0 flex-1 flex-col">
                    <span className="text-small text-ink truncate font-semibold">
                      {provider.name}
                    </span>
                    <span className="text-caption text-ink-soft truncate">{provider.base_url}</span>
                  </span>
                  <Badge tone={provider.enabled ? 'success' : 'neutral'}>
                    {provider.enabled ? <Zap className="size-3" /> : null}
                    {provider.enabled ? t('settings.model.enabled') : t('settings.model.disabled')}
                  </Badge>
                </button>
                <button
                  type="button"
                  aria-label={t('settings.model.editProvider')}
                  title={t('settings.model.editProvider')}
                  onClick={() => setEditing(provider)}
                  className="ember-press rounded-control text-ink-mute hover:bg-raised hover:text-ink inline-flex size-11 shrink-0 items-center justify-center transition-colors duration-[var(--dur-hover)] ease-[var(--ease)]"
                >
                  <Pencil className="size-3.5" />
                </button>
              </div>
              {expanded === provider.id ? (
                <ProviderModels
                  provider={provider}
                  activeModelValue={activeValue}
                  onActivate={value => void selectGlobal(value)}
                  onChanged={() => {
                    toast.success(t('settings.saved'))
                    reload()
                    // 删掉的正好是全局模型时后端会把指针清掉，这里跟着刷新选择器
                    global.reload()
                  }}
                />
              ) : null}
            </Card>
          ))}
        </div>
      ) : (
        <EmptyState icon={<Server className="size-6" />} title={t('settings.model.empty')} />
      )}

      <Dialog
        open={creating}
        onClose={() => setCreating(false)}
        title={t('settings.model.addProvider')}
        size="md"
      >
        <ProviderDialog
          onDone={() => {
            setCreating(false)
            reload()
          }}
        />
      </Dialog>

      <Dialog
        open={Boolean(editing)}
        onClose={() => setEditing(null)}
        title={t('settings.model.editProvider')}
        size="md"
      >
        {editing ? (
          <ProviderDialog
            provider={editing}
            onDone={() => {
              setEditing(null)
              reload()
            }}
          />
        ) : null}
      </Dialog>
    </SettingsSection>
  )
}
