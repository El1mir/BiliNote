import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import { I18nContext, type I18nValue } from '../../src/ember/i18n/context'
import { dictionaries, format } from '../../src/ember/i18n/strings'
import type { Locale, MessageKey } from '../../src/ember/i18n/strings'
import { StartupScreen } from '../../src/ember/startup/StartupScreen'
import { NotFoundPage } from '../../src/ember/pages/NotFoundPage'
import { OnboardingPage } from '../../src/ember/pages/OnboardingPage'

/**
 * spec 021 W4（引导 / 启动屏 / 后端不可用 / 404）的回归钉。
 *
 * 这一组页面最难在正常截图里看见失效的，是**状态分支**与**被替换掉的旧色名**：
 * 启动失败卡少一个重试入口、404 少一条回工作区的链接、页面又写回 bg-primary 这类
 * 兼容别名，都只在特定状态或特定主题下才露馅。这里用静态渲染 + 纯文本扫描固定住，
 * 不引入 DOM 环境（本仓库 devDependencies 里没有 jsdom）。
 */

const i18n = (locale: Locale): I18nValue => ({
  locale,
  setLocale: () => {},
  t: (key: MessageKey, values?: Record<string, string | number>) =>
    format(dictionaries[locale][key] ?? key, values),
})

const zh = dictionaries['zh-CN']

const render = (node: React.ReactNode, locale: Locale = 'zh-CN') =>
  renderToStaticMarkup(
    <I18nContext.Provider value={i18n(locale)}>
      <MemoryRouter>{node}</MemoryRouter>
    </I18nContext.Provider>,
  )

describe('启动屏：等待与失败是两个不同状态', () => {
  it('等待态标 aria-busy 并说出在等什么', () => {
    const html = render(<StartupScreen loading failed={false} lastError={null} />)
    expect(html).toContain('data-boot-state="loading"')
    expect(html).toContain('aria-busy="true"')
    expect(html).toContain(zh['startup.loading.title'])
    expect(html).toContain('ember-spin')
  })

  it('失败态给出可读原因、常见原因清单和重试入口', () => {
    const html = render(
      <StartupScreen
        loading={false}
        failed
        lastError="connect ECONNREFUSED 127.0.0.1:8483"
        reason={{ code: 'connect', detail: 'ECONNREFUSED 127.0.0.1:8483' }}
      />,
    )
    expect(html).toContain('data-boot-state="failed"')
    expect(html).toContain('data-boot-error="connect ECONNREFUSED 127.0.0.1:8483"')
    expect(html).toContain(zh['startup.failed.title'])
    // 原因句按 code 走 i18n，而不是把后端原文直接丢给用户
    expect(html).toContain('ECONNREFUSED 127.0.0.1:8483')
    for (const cause of ['startup.failed.causePath', 'startup.failed.causePort', 'startup.failed.causeModel'] as MessageKey[]) {
      expect(html, cause).toContain(zh[cause])
    }
    expect(html).toContain(zh['startup.retry'])
    expect(html).toContain('<button')
  })

  it('超时态把预算秒数写进文案', () => {
    const html = render(<StartupScreen loading={false} failed lastError={null} reason={{ code: 'timeout' }} />)
    expect(html).toContain('60s')
  })
})

describe('404 有回工作区的主路径', () => {
  it('渲染指向工作区的链接（键盘可达的原生 a）', () => {
    const html = render(<NotFoundPage />)
    expect(html).toContain(zh['notFound.title'])
    expect(html).toContain(zh['notFound.back'])
    expect(html).toMatch(/<a[^>]+href="\/"/)
    expect(html).toContain('focus-visible:outline-accent')
  })
})

describe('首次引导：步骤一在后端未就绪前不放行', () => {
  it('首屏停在第一步，下一步禁用，重试可用', () => {
    const html = render(<OnboardingPage />)
    expect(html).toContain('aria-current="step"')
    expect(html).toContain('data-step-state="current"')
    expect(html).toContain(zh['onboarding.step1.title'])
    expect(html).toContain(zh['onboarding.step1.retry'])
    expect(html).toMatch(/<button[^>]*disabled[^>]*>下一步/)
  })
})

describe('被重绘的四个面不再写回旧 token 别名', () => {
  const ROOT = fileURLToPath(new URL('../..', import.meta.url))
  const FILES = [
    'src/ember/startup/StartupScreen.tsx',
    'src/ember/pages/OnboardingPage.tsx',
    'src/ember/pages/NotFoundPage.tsx',
    'src/ember/shell/ErrorBoundary.tsx',
  ]
  const LEGACY = /(?:bg|text|border|shadow|outline|accent)-(?:primary|on-primary|primary-hover|primary-soft|primary-ring|ok|warn)\b|ink-mute\b|var\(--primary\)/

  it('只用 021 的规范色名', () => {
    const hits = FILES.map(path => ({ path, text: readFileSync(ROOT + '/' + path, 'utf8') }))
      .filter(entry => LEGACY.test(entry.text))
      .map(entry => entry.path)
    expect(hits).toEqual([])
  })
})
