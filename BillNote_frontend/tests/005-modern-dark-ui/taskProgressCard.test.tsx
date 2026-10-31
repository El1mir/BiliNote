import { describe, expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import { I18nContext, type I18nValue } from '../../src/ember/i18n/context'
import { dictionaries, format } from '../../src/ember/i18n/strings'
import type { Locale, MessageKey } from '../../src/ember/i18n/strings'
import { TaskProgressCard } from '../../src/ember/features/workspace/TaskProgressCard'
import type { Task } from '../../src/store/taskStore'

/**
 * spec 005 ticket 12 第 4 条：进度卡必须有一个渲染测试。
 *
 * 用 `renderToStaticMarkup` 而不是 jsdom：这个仓库的 devDependencies 只有
 * vitest，没有 DOM 环境；`react-dom/server` 是 react-dom 自带的，不新增依赖
 * 就能断言真实输出。组件全部逻辑都在渲染结果里（文案、百分比、详情行），
 * 静态标记足够钉住工单 08 的三处缺陷。
 */

const i18n = (locale: Locale): I18nValue => ({
  locale,
  setLocale: () => {},
  t: (key: MessageKey, values?: Record<string, string | number>) =>
    format(dictionaries[locale][key] ?? key, values),
})

const render = (task: Partial<Task>, locale: Locale = 'zh-CN') =>
  renderToStaticMarkup(
    <I18nContext.Provider value={i18n(locale)}>
      <TaskProgressCard task={task as Task} />
    </I18nContext.Provider>,
  )

/** 进度条只有 `label` 存在时才渲染百分比数字。 */
const percentText = (html: string): string[] => [...html.matchAll(/(\d+)%/g)].map(match => match[1])

describe('TaskProgressCard', () => {
  it('renders the backend stage label and its detail counters', () => {
    const html = render({
      id: 'task-1',
      status: 'TRANSCRIBING',
      stage: 'transcribing',
      stageLabel: '音频转写',
      progress: 62,
      stageProgress: 40,
      detail: { current: 3, total: 10, unit: 'segments' },
    })

    expect(html).toContain('音频转写')
    expect(html).toContain('3 / 10 段')
    expect(percentText(html)).toContain('62')
  })

  it('falls back to the stage mapping when the backend sends no label', () => {
    const html = render({
      id: 'task-2',
      status: 'DOWNLOADING',
      stage: 'building_grids',
      stageLabel: null,
      progress: 44,
    })

    // 阶段文案走 stageKey('building_grids') → task.stage.frames
    expect(html).toContain('抽取画面')
    expect(html).not.toContain('task.stage.frames')
  })

  it('does not fabricate a percentage when progress is null', () => {
    const html = render({
      id: 'task-3',
      status: 'PENDING',
      stage: 'queued',
      stageLabel: '排队中',
      progress: null,
      stageProgress: null,
    })

    // 工单 08 缺陷 3 的反面：没有真实进度时宁可只显示阶段名，也不画「0%」
    expect(html).toContain('排队中')
    expect(html).not.toContain('role="progressbar"')
    expect(percentText(html)).toEqual([])
  })

  it('marks a failed task with the stage that broke and keeps the message', () => {
    const html = render({
      id: 'task-4',
      status: 'FAILED',
      stage: 'transcribing',
      stageLabel: '音频转写',
      progress: 40,
      message: '转写服务超时',
    })

    expect(html).toContain('音频转写')
    expect(html).toContain('转写服务超时')
    expect(html).toContain('失败')
    expect(percentText(html)).toContain('40')
  })

  it('shows the finished stage of a successful task instead of an empty line', () => {
    const html = render({
      id: 'task-5',
      status: 'SUCCESS',
      stage: 'saving',
      stageLabel: '保存结果',
      progress: 100,
    })

    expect(html).toContain('保存结果')
    expect(html).toContain('已完成')
    expect(percentText(html)).toContain('100')
  })

  it('renders the English copy when the locale is en-US', () => {
    const html = render(
      {
        id: 'task-6',
        status: 'TRANSCRIBING',
        stage: 'transcribing',
        stageLabel: null,
        progress: 30,
      },
      'en-US',
    )

    expect(html).toContain('Transcribing')
    expect(html).toContain('Running')
  })
})
