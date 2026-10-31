import { useI18n } from '@/ember/i18n/context'
import { Badge } from '@/ember/ui/Badge'
import { Card } from '@/ember/ui/Card'
import { Select } from '@/ember/ui/Select'
import type { GlobalModelOption } from '@/utils/globalModel'

type GlobalModelPickerProps = {
  options: GlobalModelOption[]
  /** 当前全局模型压成一维 value；空串表示还没激活。 */
  activeValue: string
  saving?: boolean
  onSelect: (value: string) => void
}

/**
 * 全局模型选择器，住在「模型提供商」页（spec 019）。
 *
 * 它只是一个原生 select：候选是「启用服务商 × 其下模型」的拍平结果，所以停用的
 * 服务商、被删掉的模型根本不在列表里 —— 选不到，也就不会再存下一个失效指针。
 * 选中即保存（没有"保存"按钮）：这一项只有一个值，多一次确认反而容易漏点。
 */
export function GlobalModelPicker({
  options,
  activeValue,
  saving,
  onSelect,
}: GlobalModelPickerProps) {
  const { t } = useI18n()
  const activeLabel = options.find(option => option.value === activeValue)?.label

  return (
    <Card className="bg-canvas">
      <div className="flex flex-col gap-3 px-4 py-4 sm:px-5">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <span className="ember-overline">{t('settings.model.globalTitle')}</span>
          {activeLabel ? (
            <Badge tone="ember" className="max-w-full truncate">
              {activeLabel}
            </Badge>
          ) : (
            <span className="text-caption text-ink-mute">{t('settings.model.globalNone')}</span>
          )}
        </div>

        {options.length ? (
          <>
            <Select
              aria-label={t('settings.model.globalTitle')}
              data-testid="global-model-select"
              options={[
                { value: '', label: t('settings.model.globalNone'), disabled: false },
                ...options,
              ]}
              value={activeValue}
              disabled={saving}
              onChange={event => {
                if (event.target.value) onSelect(event.target.value)
              }}
            />
            <span className="text-caption text-ink-mute">{t('settings.model.globalHint')}</span>
          </>
        ) : (
          <span className="text-caption text-ink-mute">{t('settings.model.globalEmpty')}</span>
        )}
      </div>
    </Card>
  )
}
