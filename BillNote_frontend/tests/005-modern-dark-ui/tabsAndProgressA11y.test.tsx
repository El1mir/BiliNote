import { describe, expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import { Tabs } from '../../src/ember/ui/Tabs'
import { tabPanelProps, tabId, panelId, resolveTabKey } from '../../src/ember/ui/tabsA11y'
import { Progress } from '../../src/ember/ui/Progress'
import { I18nContext, type I18nValue } from '../../src/ember/i18n/context'
import { dictionaries, format } from '../../src/ember/i18n/strings'
import type { MessageKey } from '../../src/ember/i18n/strings'

/**
 * spec 005 / UI 计划 W1（A2、A5）。
 *
 * 改之前：tablist 里每个 tab 都能被 Tab 键逐个停留，且没有 aria-controls；
 * 面板根本没有 role="tabpanel" —— 键盘用户要按 N 次 Tab 才能经过一组 tab，
 * 读屏用户也无法从 tab 跳到它控制的面板。
 */

const items = [
  { id: 'note', label: '笔记' },
  { id: 'transcript', label: '转写' },
  { id: 'outline', label: '大纲' },
]

const renderTabs = (value: string) =>
  renderToStaticMarkup(
    <div>
      <Tabs idBase="reader" items={items} value={value} onChange={() => {}} />
      <div {...tabPanelProps('reader', value)}>面板内容</div>
    </div>,
  )

describe('Tabs', () => {
  it('uses roving tabindex: only the active tab is reachable with Tab', () => {
    const html = renderTabs('transcript')
    // 三个 tab 里恰好一个 tabindex="0"，其余是 -1。
    // （面板自己也有 tabindex="0"，所以只统计 role="tab" 的按钮。）
    expect(html.match(/role="tab"[^>]*tabindex="0"/g)?.length).toBe(1)
    expect(html.match(/role="tab"[^>]*tabindex="-1"/g)?.length).toBe(2)
  })

  it('points every tab at its panel and the panel back at its tab', () => {
    const html = renderTabs('note')
    for (const item of items) {
      expect(html).toContain(`id="${tabId('reader', item.id)}"`)
      expect(html).toContain(`aria-controls="${panelId('reader', item.id)}"`)
    }
    expect(html).toContain('role="tabpanel"')
    expect(html).toContain(`id="${panelId('reader', 'note')}"`)
    expect(html).toContain(`aria-labelledby="${tabId('reader', 'note')}"`)
  })

  it('marks the selected tab with aria-selected', () => {
    const html = renderTabs('note')
    expect(html.match(/aria-selected="true"/g)?.length).toBe(1)
  })
})

describe('resolveTabKey（左右方向键与 Home/End）', () => {
  it('moves right and wraps from the last tab to the first', () => {
    expect(resolveTabKey('ArrowRight', 0, 3)).toBe(1)
    expect(resolveTabKey('ArrowRight', 2, 3)).toBe(0)
  })

  it('moves left and wraps from the first tab to the last', () => {
    expect(resolveTabKey('ArrowLeft', 0, 3)).toBe(2)
    expect(resolveTabKey('ArrowLeft', 2, 3)).toBe(1)
  })

  it('jumps to the ends with Home and End', () => {
    expect(resolveTabKey('Home', 2, 3)).toBe(0)
    expect(resolveTabKey('End', 0, 3)).toBe(2)
  })

  it('ignores keys that are not navigation', () => {
    expect(resolveTabKey('Enter', 1, 3)).toBeNull()
    expect(resolveTabKey('Tab', 1, 3)).toBeNull()
  })
})

const i18n: I18nValue = {
  locale: 'zh-CN',
  setLocale: () => {},
  t: (key: MessageKey, values?: Record<string, string | number>) =>
    format(dictionaries['zh-CN'][key] ?? key, values),
}

describe('Progress', () => {
  it('still has an accessible name when no label is passed', () => {
    // 改之前 aria-label 直接等于 label，未传时是 undefined ——
    // 读屏只念出一个没有名字的 progressbar。
    const html = renderToStaticMarkup(<Progress value={0.44} />)
    expect(html).toContain('role="progressbar"')
    expect(html).not.toContain('aria-label="undefined"')
    const label = /aria-label="([^"]*)"/.exec(html)?.[1]
    expect(label).toBeTruthy()
    expect(label?.trim().length).toBeGreaterThan(0)
  })

  it('uses the label as the accessible name when one is given', () => {
    const html = renderToStaticMarkup(
      <I18nContext.Provider value={i18n}>
        <Progress value={0.44} label="进度" />
      </I18nContext.Provider>,
    )
    expect(html).toContain('aria-label="进度"')
    expect(html).toContain('aria-valuenow="44"')
  })

  it('falls back to the i18n string when no label is passed inside a provider', () => {
    const html = renderToStaticMarkup(
      <I18nContext.Provider value={i18n}>
        <Progress value={1} />
      </I18nContext.Provider>,
    )
    expect(html).toContain('aria-label="进度"')
  })
})