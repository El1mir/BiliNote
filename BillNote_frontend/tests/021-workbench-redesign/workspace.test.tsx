import { describe, expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import { I18nContext, type I18nValue } from '../../src/ember/i18n/context'
import { dictionaries, format } from '../../src/ember/i18n/strings'
import type { Locale, MessageKey } from '../../src/ember/i18n/strings'
import { TaskCard } from '../../src/ember/features/workspace/TaskCard'
import { TaskProgressCard } from '../../src/ember/features/workspace/TaskProgressCard'
import { listDisplay } from '../../src/ember/features/workspace/listStates'
import { retryScopeForTask, retryScopeForGroup } from '../../src/ember/features/workspace/retryFailed'
import type { Task } from '../../src/store/taskStore'

/**
 * spec 021 工作区（W1）的回归钉：
 *
 * 视觉重绘最容易悄悄弄丢的是**状态的双编码**与**列表四态的分支顺序**——两者都
 * 只在某个具体状态下才显现，正常截图完全看不出来。这里用静态渲染与纯函数把
 * 它们固定住，不引入 DOM 环境（本仓库 devDependencies 里没有 jsdom）。
 */

const i18n = (locale: Locale): I18nValue => ({
  locale,
  setLocale: () => {},
  t: (key: MessageKey, values?: Record<string, string | number>) =>
    format(dictionaries[locale][key] ?? key, values),
})

const makeTask = (patch: Partial<Task>): Task =>
  ({
    id: 'task-w1',
    markdown: '',
    transcript: { full_text: '', language: 'zh', raw: {}, segments: [] },
    status: 'TRANSCRIBING',
    platform: 'bilibili',
    groupId: null,
    groupName: '',
    audioMeta: {
      cover_url: '',
      duration: 0,
      file_path: '',
      platform: 'bilibili',
      raw_info: null,
      title: '工作区测试视频',
      video_id: 'BV1',
    },
    createdAt: new Date().toISOString(),
    formData: { video_url: 'https://www.bilibili.com/video/BV1' },
    ...patch,
  }) as Task

const renderCard = (patch: Partial<Task>, active = false) =>
  renderToStaticMarkup(
    <I18nContext.Provider value={i18n('zh-CN')}>
      <TaskCard
        task={makeTask(patch)}
        active={active}
        selecting={false}
        checked={false}
        draggable={false}
        onClick={() => {}}
        onDragStart={() => {}}
        onDragEnd={() => {}}
      />
    </I18nContext.Provider>,
  )

const renderProgress = (task: Partial<Task>, onRetry?: () => void) =>
  renderToStaticMarkup(
    <I18nContext.Provider value={i18n('zh-CN')}>
      <TaskProgressCard task={makeTask(task)} onRetry={onRetry} />
    </I18nContext.Provider>,
  )

describe('workspace 状态双编码', () => {
  it('writes the status as text and as an icon, not colour alone', () => {
    const running = renderCard({ status: 'TRANSCRIBING' })
    expect(running).toContain('生成中')
    expect(running).toContain('<svg')

    const failed = renderCard({ status: 'FAILED' })
    expect(failed).toContain('失败')
    expect(failed).toContain('<svg')

    const done = renderCard({ status: 'SUCCESS' })
    expect(done).toContain('已完成')
    expect(done).toContain('<svg')
  })

  it('marks the selected card in the address-bar sense, not by colour only', () => {
    expect(renderCard({}, true)).toContain('aria-current="true"')
    expect(renderCard({}, false)).not.toContain('aria-current')
  })
})

describe('workspace 失败重试', () => {
  it('offers exactly one retry action for a failed task', () => {
    const html = renderProgress({ status: 'FAILED', stage: 'transcribing' }, () => {})
    expect(html).toContain('重试失败任务')
    expect(html.match(/重试失败任务/g)?.length).toBe(1)
    // idle 的按钮不该宣称自己 busy —— 只在真的在排队时才置 aria-busy。
    expect(html).not.toContain('aria-busy')
  })

  it('never offers retry for a task that already succeeded', () => {
    const html = renderProgress({ status: 'SUCCESS', stage: 'saving' }, () => {})
    expect(html).not.toContain('重试失败任务')
  })

  it('retries only the failed task\'s own group scope, never the whole library', () => {
    expect(retryScopeForTask({ groupId: 'g-1' })).toEqual({ scope: 'group', groupId: 'g-1' })
    expect(retryScopeForTask({ groupId: null })).toEqual({ scope: 'group', groupId: null })
    // 「全部笔记」视图下的批量重试仍然是 all —— 两个入口的范围语义不同是故意的。
    expect(retryScopeForGroup(null)).toEqual({ scope: 'all', groupId: null })
  })
})

describe('workspace 列表四态', () => {
  it('prefers skeletons over everything while the first request is in flight', () => {
    expect(listDisplay({ loading: true, error: 'boom', count: 0, narrowed: false })).toBe('loading')
  })

  it('shows the error state instead of pretending the list is empty', () => {
    expect(listDisplay({ loading: false, error: 'boom', count: 0, narrowed: false })).toBe('error')
    expect(listDisplay({ loading: false, error: 'boom', count: 3, narrowed: false })).toBe('error')
  })

  it('separates "no match" from "nothing here yet"', () => {
    expect(listDisplay({ loading: false, error: null, count: 0, narrowed: true })).toBe('emptySearch')
    expect(listDisplay({ loading: false, error: null, count: 0, narrowed: false })).toBe('empty')
    expect(listDisplay({ loading: false, error: null, count: 2, narrowed: true })).toBe('list')
  })

  it('ships copy for both states in both locales', () => {
    for (const locale of ['zh-CN', 'en-US'] as const) {
      const dict = dictionaries[locale] as Record<string, string>
      for (const key of [
        'history.emptySearch',
        'history.loadFailed',
        'history.deleteTitle',
        'history.deleteBody',
      ]) {
        expect(dict[key], locale + ' ' + key).toBeTruthy()
      }
    }
  })
})
