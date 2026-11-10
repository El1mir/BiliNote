import { describe, expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import { loadPhase, shouldBlockSave } from '../../src/ember/pages/settings/loadState'
import { SettingsLoadError } from '../../src/ember/pages/settings/Section'
import { I18nContext, type I18nValue } from '../../src/ember/i18n/context'
import { dictionaries, format } from '../../src/ember/i18n/strings'
import type { MessageKey } from '../../src/ember/i18n/strings'

/**
 * T-062 / 上游 UI 计划 §5「读取失败被当成空配置」。
 *
 * 这些断言锁的是数据安全，不是样式：
 * 1. 拉失败必须被判成 error（而不是 ready），否则分区会拿兜底值渲染表单；
 * 2. 读失败必须拦住保存 —— 这是"空值覆盖真实配置"的最后一道闸；
 * 3. 失败态渲染出来的是错误 + 重试，不含任何可编辑控件。
 */

const i18n: I18nValue = {
  locale: 'zh-CN',
  setLocale: () => {},
  t: (key: MessageKey, values?: Record<string, string | number>) =>
    format(dictionaries['zh-CN'][key] ?? key, values),
}

describe('loadPhase', () => {
  it('treats a rejected load as an error, never as ready', () => {
    // 关键回归：以前 error 被忽略，这里会返回 'ready'，分区随即用 0/空串渲染。
    expect(loadPhase({ data: undefined, loading: false, error: new Error('offline') })).toBe('error')
    expect(shouldBlockSave({ data: undefined, loading: false, error: new Error('offline') })).toBe(true)
  })

  it('stays loading until the first response arrives', () => {
    expect(loadPhase({ data: undefined, loading: true, error: undefined })).toBe('loading')
  })

  it('is ready once data is present', () => {
    expect(loadPhase({ data: { max_parallel_notes: 3 }, loading: false, error: undefined })).toBe('ready')
    expect(shouldBlockSave({ data: { max_parallel_notes: 3 }, loading: false, error: undefined })).toBe(false)
  })

  it('keeps showing data on a failed reload instead of blanking the form', () => {
    const state = { data: { max_parallel_notes: 3 }, loading: false, error: new Error('offline') }
    expect(loadPhase(state)).toBe('error')
    expect(shouldBlockSave(state)).toBe(true)
  })
})

describe('SettingsLoadError', () => {
  const html = renderToStaticMarkup(
    <I18nContext.Provider value={i18n}>
      <SettingsLoadError onRetry={() => {}} />
    </I18nContext.Provider>,
  )

  it('announces the failure and offers a retry', () => {
    expect(html).toContain('role="alert"')
    expect(html).toContain('读取设置失败')
    expect(html).toContain('重试')
  })

  it('renders no editable control at all', () => {
    // 失败态里出现 input/textarea/select 就意味着"空配置表单"又回来了。
    expect(html).not.toMatch(/<(input|textarea|select)\b/)
  })
})
