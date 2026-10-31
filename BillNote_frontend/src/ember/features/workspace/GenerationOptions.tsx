import { noteDetails, noteFormats, noteScenes } from '@/constant/note'
import { useI18n } from '@/ember/i18n/context'
import type { MessageKey } from '@/ember/i18n/strings'
import { Chip } from '@/ember/ui/Chip'
import { Field } from '@/ember/ui/Field'
import { Input, Textarea } from '@/ember/ui/Input'
import { Select } from '@/ember/ui/Select'
import { Switch } from '@/ember/ui/Switch'
import { Tabs } from '@/ember/ui/Tabs'
import type { GenerationSettings } from './generationSettings'

/**
 * One line per sampling mode, rendered under the switcher. The three differ in how
 * frames get chosen and how much model work that costs — that trade-off is the only
 * reason to prefer one, so it belongs next to the control that picks it.
 */
const SAMPLING_HINT: Record<'interval' | 'smart' | 'hybrid', MessageKey> = {
  interval: 'workspace.samplingMode.intervalHint',
  smart: 'workspace.samplingMode.smartHint',
  hybrid: 'workspace.samplingMode.hybridHint',
}

type Props = {
  value: GenerationSettings
  onChange: (patch: Partial<GenerationSettings>) => void
  /** 同一页出现两份面板时，用前缀把 input id 岔开（label 的 htmlFor 靠它）。 */
  idPrefix?: string
}

export function GenerationOptions({ value, onChange, idPrefix = '' }: Props) {
  const { t } = useI18n()
  const label = (key: MessageKey) => t(key)
  const id = (name: string) => (idPrefix ? idPrefix + '-' + name : name)

  const samplingMode = value.sampling_mode
  const frameLimitMode = value.frame_limit_mode

  const toggleFormat = (next: string) => {
    const list = value.format.includes(next)
      ? value.format.filter(item => item !== next)
      : [...value.format, next]
    onChange({ format: list })
  }

  /** grid_size 是固定的 [列, 行] 元组 —— 两个格子一起写成新数组。 */
  const setGridSize = (columns: number, rows: number) => onChange({ grid_size: [columns, rows] })

  return (
    <div className="flex flex-col gap-5">
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label={label('workspace.quality')} htmlFor={id('quality')}>
          <Select
            id={id('quality')}
            options={[
              { value: 'fast', label: label('workspace.quality.fast') },
              { value: 'medium', label: label('workspace.quality.medium') },
              { value: 'slow', label: label('workspace.quality.slow') },
            ]}
            value={value.quality}
            onChange={event => onChange({ quality: event.target.value as GenerationSettings['quality'] })}
          />
        </Field>
        <Field label={label('workspace.scene')} htmlFor={id('scene')}>
          <Select
            id={id('scene')}
            options={noteScenes.map(item => ({
              value: item.value,
              label: label(('workspace.scene.' + item.value) as MessageKey),
            }))}
            value={value.scene}
            onChange={event => onChange({ scene: event.target.value })}
          />
        </Field>
        <Field label={label('workspace.detail')} htmlFor={id('detail')}>
          <Select
            id={id('detail')}
            options={noteDetails.map(item => ({
              value: item.value,
              label: label(('workspace.detail.' + item.value) as MessageKey),
            }))}
            value={value.detail}
            onChange={event => onChange({ detail: event.target.value })}
          />
        </Field>
      </div>

      <div className="flex flex-col gap-2">
        <span className="text-small text-ink font-semibold">{label('workspace.format')}</span>
        <div className="flex flex-wrap gap-2">
          {noteFormats.map(item => (
            <Chip
              key={item.value}
              active={value.format.includes(item.value)}
              onClick={() => toggleFormat(item.value)}
            >
              {label(('workspace.format.' + item.value) as MessageKey)}
            </Chip>
          ))}
        </div>
      </div>

      <Field label={label('workspace.extras')} htmlFor={id('extras')}>
        <Textarea
          id={id('extras')}
          rows={3}
          placeholder={label('workspace.extrasPlaceholder')}
          value={value.extras}
          onChange={event => onChange({ extras: event.target.value })}
        />
      </Field>

      <div className="rounded-surface border-line bg-surface flex flex-col gap-3 border p-4">
        <div className="flex items-start justify-between gap-4">
          <div className="flex flex-col gap-0.5">
            <span className="text-small text-ink font-semibold">
              {label('workspace.videoUnderstanding')}
            </span>
            <span className="text-caption text-ink-soft">
              {label('workspace.videoUnderstandingHint')}
            </span>
          </div>
          <Switch
            checked={value.video_understanding}
            label={label('workspace.videoUnderstanding')}
            onChange={checked => onChange({ video_understanding: checked })}
          />
        </div>

        {value.video_understanding ? (
          <div className="ember-enter border-line flex flex-col gap-4 border-t pt-4">
            <div className="flex flex-col gap-2">
              <span className="text-small text-ink font-semibold">
                {label('workspace.samplingMode')}
              </span>
              <Tabs
                value={samplingMode}
                onChange={next =>
                  onChange({ sampling_mode: next as GenerationSettings['sampling_mode'] })
                }
                items={[
                  { id: 'interval', label: label('workspace.samplingMode.interval') },
                  { id: 'smart', label: label('workspace.samplingMode.smart') },
                  { id: 'hybrid', label: label('workspace.samplingMode.hybrid') },
                ]}
              />
              <p className="text-caption text-ink-soft leading-relaxed">
                {label(SAMPLING_HINT[samplingMode])}
              </p>
            </div>
            <div className="grid gap-4 sm:grid-cols-2">
              {/* interval 只留一个旋钮：帧预算和秒数间隔会为同一批帧打架。 */}
              {samplingMode === 'interval' ? (
                <Field
                  label={label('workspace.interval')}
                  htmlFor={id('interval')}
                  hint={label('workspace.intervalHint')}
                >
                  <Input
                    id={id('interval')}
                    type="number"
                    min={1}
                    max={30}
                    value={value.video_interval}
                    onChange={event =>
                      onChange({ video_interval: Math.max(1, Number(event.target.value) || 1) })
                    }
                  />
                </Field>
              ) : null}

              {samplingMode === 'smart' ? (
                <>
                  <Field
                    label={label('workspace.frameLimitMode')}
                    htmlFor={id('frame-limit')}
                    hint={label('workspace.frameLimitModeHint')}
                  >
                    <Select
                      id={id('frame-limit')}
                      value={frameLimitMode}
                      options={[
                        { value: 'total', label: label('workspace.frameLimitMode.total') },
                        { value: 'per_second', label: label('workspace.frameLimitMode.per_second') },
                      ]}
                      onChange={event =>
                        onChange({
                          frame_limit_mode: event.target.value as GenerationSettings['frame_limit_mode'],
                        })
                      }
                    />
                  </Field>
                  {frameLimitMode === 'total' ? (
                    <Field
                      label={label('workspace.maxFrames')}
                      htmlFor={id('max-frames')}
                      hint={label('workspace.maxFramesHint')}
                    >
                      <Input
                        id={id('max-frames')}
                        type="number"
                        min={5}
                        value={value.max_frames}
                        onChange={event =>
                          onChange({ max_frames: Math.max(5, Number(event.target.value) || 5) })
                        }
                      />
                    </Field>
                  ) : (
                    <Field
                      label={label('workspace.framesPerSecond')}
                      htmlFor={id('fps')}
                      hint={label('workspace.framesPerSecondHint')}
                    >
                      <Input
                        id={id('fps')}
                        type="number"
                        min={1}
                        max={10}
                        value={value.frames_per_second}
                        onChange={event =>
                          onChange({ frames_per_second: Math.max(1, Number(event.target.value) || 1) })
                        }
                      />
                    </Field>
                  )}
                </>
              ) : null}

              {samplingMode === 'hybrid' ? (
                <Field
                  label={label('workspace.maxFrames')}
                  htmlFor={id('max-frames')}
                  hint={label('workspace.hybridMaxFramesHint')}
                >
                  <Input
                    id={id('max-frames')}
                    type="number"
                    min={5}
                    value={value.max_frames}
                    onChange={event =>
                      onChange({ max_frames: Math.max(5, Number(event.target.value) || 5) })
                    }
                  />
                </Field>
              ) : null}

              <Field
                label={label('workspace.gridSize')}
                htmlFor={id('grid-cols')}
                hint={label('workspace.gridSizeHint')}
              >
                <div className="flex items-center gap-2">
                  <Input
                    id={id('grid-cols')}
                    type="number"
                    min={1}
                    max={10}
                    className="w-20"
                    aria-label={label('workspace.gridSizeColumns')}
                    value={value.grid_size[0]}
                    onChange={event =>
                      setGridSize(Math.max(1, Number(event.target.value) || 1), value.grid_size[1])
                    }
                  />
                  <span aria-hidden="true" className="text-ink-mute">
                    ×
                  </span>
                  <Input
                    id={id('grid-rows')}
                    type="number"
                    min={1}
                    max={10}
                    className="w-20"
                    aria-label={label('workspace.gridSizeRows')}
                    value={value.grid_size[1]}
                    onChange={event =>
                      setGridSize(value.grid_size[0], Math.max(1, Number(event.target.value) || 1))
                    }
                  />
                </div>
              </Field>

              <Field
                label={label('workspace.ocrAssist')}
                htmlFor={id('ocr')}
                hint={label('workspace.ocrAssistHint')}
              >
                <Select
                  id={id('ocr')}
                  value={value.ocr_assist}
                  options={[
                    { value: 'global', label: label('workspace.ocrAssist.inherit') },
                    { value: 'on', label: label('workspace.ocrAssist.on') },
                    { value: 'off', label: label('workspace.ocrAssist.off') },
                  ]}
                  onChange={event =>
                    onChange({ ocr_assist: event.target.value as GenerationSettings['ocr_assist'] })
                  }
                />
              </Field>
            </div>
            <p className="rounded-control border-line bg-canvas text-caption text-ink-soft border px-3 py-2">
              {label('workspace.multimodalHint')}
            </p>
          </div>
        ) : null}
      </div>
    </div>
  )
}
