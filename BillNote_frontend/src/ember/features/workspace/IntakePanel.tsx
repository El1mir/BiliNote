import { useCallback, useState } from 'react'
import { Tabs } from '@/ember/ui/Tabs'
import { tabPanelProps } from '@/ember/ui/tabsA11y'
import { useI18n } from '@/ember/i18n/context'
import { BatchImportPanel } from './BatchImportPanel'
import { IntakeForm } from './IntakeForm'

type Mode = 'single' | 'batch'

/** tab 与面板 id 的稳定前缀（见 Tabs 的 idBase 说明）。 */
const TABS_ID = 'intake-mode'

type Props = {
  /** 批量提交成功后让工作区刷新任务列表。 */
  onSubmitted: () => void
}

/**
 * 输入区：单集生成 / 批量生成两个模式（spec 018 决策 1）。
 *
 * 为什么两个面板都常驻、只切显示：用户在单集里调好的参数不该因为去看一眼
 * 批量列表就被清空。`handoffKey` 只在「单集探测到多P 自动切过来」时自增，
 * 让批量面板重新挂载一次 —— 换了链接就该从新的展开结果开始。
 */
export function IntakePanel({ onSubmitted }: Props) {
  const { t } = useI18n()
  const [mode, setMode] = useState<Mode>('single')
  const [handoffUrl, setHandoffUrl] = useState<string | undefined>(undefined)
  const [handoffKey, setHandoffKey] = useState(0)

  const handleMultiPart = useCallback((url: string) => {
    setHandoffUrl(url)
    setHandoffKey(current => current + 1)
    setMode('batch')
  }, [])

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <Tabs
          idBase={TABS_ID}
          value={mode}
          onChange={next => setMode(next as Mode)}
          items={[
            { id: 'single', label: t('intake.single') },
            { id: 'batch', label: t('intake.batch') },
          ]}
        />
        <p className="text-caption text-ink-soft">
          {mode === 'single' ? t('intake.singleHint') : t('intake.batchHint')}
        </p>
      </div>

      <div {...tabPanelProps(TABS_ID, 'single')} className={mode === 'single' ? undefined : 'hidden'}>
        <IntakeForm onMultiPart={handleMultiPart} />
      </div>

      <div {...tabPanelProps(TABS_ID, 'batch')} className={mode === 'batch' ? undefined : 'hidden'}>
        <BatchImportPanel
          key={handoffKey}
          initialUrl={handoffUrl}
          onClose={() => setMode('single')}
          onSubmitted={onSubmitted}
        />
      </div>
    </div>
  )
}