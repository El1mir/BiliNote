import { beforeEach, describe, expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import { I18nContext, type I18nValue } from '../../src/ember/i18n/context'
import { dictionaries, format } from '../../src/ember/i18n/strings'
import type { Locale, MessageKey } from '../../src/ember/i18n/strings'
import { SaveStatus, SettingsLoadError } from '../../src/ember/pages/settings/Section'
import { SettingsNav } from '../../src/ember/pages/settings/SettingsPage'
import { loadPhase, shouldBlockSave } from '../../src/ember/pages/settings/loadState'
import { scopeExpiredOnly } from '../../src/ember/pages/settings/cleanupScopes'
import { canSaveProxy, proxyUrlError } from '../../src/ember/pages/settings/proxyUrl'
import { sectionIdFromPath, sectionOptions, SECTIONS } from '../../src/ember/pages/settings/sections'
import {
  clearDraft,
  draftKeys,
  draftsVersion,
  hasDraft,
  readDraft,
  resetDrafts,
  subscribeDrafts,
  writeDraft,
} from '../../src/ember/pages/settings/drafts'

/**
 * spec 021 设置页（W3）的回归钉。
 *
 * 视觉重绘最容易丢的是三类只有特定状态才出现的语义：
 *  - 读失败时"不给改"（否则保存把空值/0 写回后端）；
 *  - 预览与执行同一清理口径；
 *  - 草稿跨分区卸载仍然存在。
 * 这些都能脱 DOM 断言；本仓库没有 jsdom，所以静态渲染 + 纯函数两条路。
 */

const i18n = (locale: Locale): I18nValue => ({
  locale,
  setLocale: () => {},
  t: (key: MessageKey, values?: Record<string, string | number>) =>
    format(dictionaries[locale][key] ?? key, values),
})

beforeEach(() => resetDrafts())

describe('设置分区读取状态', () => {
  it('treats a read error as error even while reloading', () => {
    expect(loadPhase({ data: undefined, loading: true, error: 'boom' })).toBe('error')
  })

  it('shows the loading branch only before any data arrives', () => {
    expect(loadPhase({ data: undefined, loading: true, error: null })).toBe('loading')
    // 重新拉取时旧数据还在，页面不该退回骨架屏（否则表单会被卸载、草稿看起来丢了）。
    expect(loadPhase({ data: { a: 1 }, loading: true, error: null })).toBe('ready')
    expect(loadPhase({ data: { a: 1 }, loading: false, error: null })).toBe('ready')
  })

  it('blocks saving exactly when the read failed', () => {
    expect(shouldBlockSave({ data: undefined, loading: false, error: 'boom' })).toBe(true)
    expect(shouldBlockSave({ data: undefined, loading: true, error: null })).toBe(false)
    expect(shouldBlockSave({ data: {}, loading: false, error: null })).toBe(false)
  })
})

describe('清理口径', () => {
  it('maps each scope to one expired_only value shared by preview and run', () => {
    expect(scopeExpiredOnly('expired')).toBe(true)
    expect(scopeExpiredOnly('all')).toBe(false)
  })
})

describe('代理地址校验', () => {
  it('rejects empty, scheme-less and malformed urls', () => {
    expect(proxyUrlError('')).toBe('empty')
    expect(proxyUrlError('   ')).toBe('empty')
    expect(proxyUrlError('127.0.0.1:7890')).toBe('scheme')
    expect(proxyUrlError('ftp://127.0.0.1:21')).toBe('scheme')
    expect(proxyUrlError('http://')).toBe('malformed')
    expect(proxyUrlError('http://127.0.0.1:7890')).toBe(null)
  })

  it('allows saving a disabled proxy with no address, but not an enabled invalid one', () => {
    expect(canSaveProxy({ enabled: false, url: '' })).toBe(true)
    expect(canSaveProxy({ enabled: true, url: '' })).toBe(false)
    expect(canSaveProxy({ enabled: true, url: 'http://127.0.0.1:7890' })).toBe(true)
  })
})

describe('草稿仓库', () => {
  it('keeps a draft after the section component is gone', () => {
    writeDraft('general', { max_parallel_notes: 5 })
    expect(hasDraft('general')).toBe(true)
    expect(readDraft<{ max_parallel_notes: number }>('general')).toEqual({ max_parallel_notes: 5 })
    expect(draftKeys()).toEqual(['general'])
    // 模拟"离开分区"：没有组件，只剩仓库，值仍在。
    expect(readDraft('general')).toBeDefined()

    clearDraft('general')
    expect(hasDraft('general')).toBe(false)
    expect(readDraft('general')).toBeUndefined()
  })

  it('notifies subscribers and only bumps the version when something changed', () => {
    let calls = 0
    const unsubscribe = subscribeDrafts(() => {
      calls += 1
    })
    const before = draftsVersion()

    writeDraft('ocr', { enabled: true })
    expect(calls).toBe(1)
    expect(draftsVersion()).toBeGreaterThan(before)

    // 清除一个不存在的 key 不该惊动订阅者。
    const versionAfterWrite = draftsVersion()
    clearDraft('not-there')
    expect(calls).toBe(1)
    expect(draftsVersion()).toBe(versionAfterWrite)

    unsubscribe()
    writeDraft('ocr', undefined)
    expect(calls).toBe(1)
  })
})

describe('SettingsLoadError', () => {
  it('explains the failure and offers retry without rendering editable controls', () => {
    const html = renderToStaticMarkup(
      <I18nContext.Provider value={i18n('zh-CN')}>
        <SettingsLoadError onRetry={() => {}} />
      </I18nContext.Provider>,
    )

    expect(html).toContain('role="alert"')
    expect(html).toContain(dictionaries['zh-CN']['settings.loadFailed'])
    expect(html).toContain(dictionaries['zh-CN']['common.retry'])
    // 读不回来就不给改：不能出现任何输入控件，否则用户会以为那是"当前配置"。
    expect(html).not.toContain('<input')
    expect(html).not.toContain('<textarea')
    expect(html).not.toContain('<select')
    expect(html).not.toContain('<form')
  })
})

describe('SaveStatus', () => {
  const render = (state: 'idle' | 'saving' | 'saved' | 'error') =>
    renderToStaticMarkup(
      <I18nContext.Provider value={i18n('zh-CN')}>
        <SaveStatus state={state} />
      </I18nContext.Provider>,
    )

  it('says saved and failed inline, politely', () => {
    const saved = render('saved')
    expect(saved).toContain(dictionaries['zh-CN']['settings.saved'])
    expect(saved).toContain('role="status"')
    expect(saved).toContain('aria-live="polite"')

    const failed = render('error')
    expect(failed).toContain(dictionaries['zh-CN']['settings.saveFailed'])
    expect(failed).toContain('text-danger')
  })

  it('stays out of the way while idle or saving (the button already shows the spinner)', () => {
    expect(render('idle')).toBe('')
    expect(render('saving')).toBe('')
  })
})

describe('分区导航', () => {
  it('resolves the current section from the path with a general fallback', () => {
    expect(sectionIdFromPath('/settings/model')).toBe('model')
    expect(sectionIdFromPath('/settings/transcriber/')).toBe('transcriber')
    expect(sectionIdFromPath('/settings')).toBe('general')
    expect(sectionIdFromPath('/settings/nope')).toBe('general')
  })

  it('marks sections that hold a draft in the narrow-screen options', () => {
    writeDraft('prompt', 'hello')
    const options = sectionOptions(key => key, new Set(draftKeys()))
    expect(options).toHaveLength(SECTIONS.length)
    expect(options.find(o => o.value === 'prompt')?.label).toBe('settings.prompt •')
    expect(options.find(o => o.value === 'about')?.label).toBe('settings.about')
  })

  it('renders a native select on narrow screens and the vertical list on wide ones', () => {
    // 静态渲染走的是 useSyncExternalStore 的 server snapshot（版本恒为 0），
    // 所以这里不断言草稿标记 —— 它由上面 sectionOptions 的用例钉住。
    const html = renderToStaticMarkup(
      <I18nContext.Provider value={i18n('zh-CN')}>
        <MemoryRouter initialEntries={['/settings/model']}>
          <SettingsNav current="model" />
        </MemoryRouter>
      </I18nContext.Provider>,
    )

    // 窄屏：一颗 select 装下全部分区，且当前值跟随路由。
    expect(html).toContain('<select')
    expect(html).toContain('id="settings-section"')
    expect(html).toContain('value="model"')
    expect(html.match(/<option/g)?.length).toBe(SECTIONS.length)
    // 宽屏：同一份清单渲染成带 aria-current 的链接列表。
    expect(html).toContain('aria-label="设置"')
    expect(html).toContain('/settings/general')
    expect(html).toContain('aria-current="page"')
    // 窄屏下拉必须藏在 lg 以下、宽屏导航必须从 lg 起出现，断点只切呈现不切路由。
    expect(html).toContain('lg:hidden')
    expect(html).toContain('lg:flex')
  })
})
