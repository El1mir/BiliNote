import { describe, expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import { I18nContext, type I18nValue } from '../../src/ember/i18n/context'
import { dictionaries, format } from '../../src/ember/i18n/strings'
import type { MessageKey } from '../../src/ember/i18n/strings'
import { TaskCard } from '../../src/ember/features/workspace/TaskCard'
import type { Task } from '../../src/store/taskStore'

/**
 * spec 005 工单 10 的验收：「任务卡片直接看到阶段与进度」。
 *
 * 历史卡片只有标题 + 状态徽标 + 相对时间 —— "生成中"三个字对用户没有信息量，
 * 看不出卡在哪一步、走到几十%。卡片被拆成 `TaskCard`（单条渲染）与 `TaskList`
 * （筛选、搜索、拖拽），正是为了让这条验收能脱离 store 与浏览器环境断言。
 */

const i18n: I18nValue = {
  locale: 'zh-CN',
  setLocale: () => {},
  t: (key: MessageKey, values?: Record<string, string | number>) =>
    format(dictionaries['zh-CN'][key] ?? key, values),
}

const makeTask = (patch: Partial<Task>): Task =>
  ({
    id: 'task-x',
    markdown: '',
    transcript: { full_text: '', language: 'zh', raw: {}, segments: [] },
    status: 'TRANSCRIBING',
    plateform: undefined,
    platform: 'bilibili',
    groupId: null,
    groupName: '',
    audioMeta: {
      cover_url: '',
      duration: 0,
      file_path: '',
      platform: 'bilibili',
      raw_info: null,
      title: '测试视频',
      video_id: 'BV1',
    },
    createdAt: new Date().toISOString(),
    formData: { video_url: 'https://www.bilibili.com/video/BV1' },
    ...patch,
  }) as Task

const renderCard = (patch: Partial<Task>) =>
  renderToStaticMarkup(
    <I18nContext.Provider value={i18n}>
      <TaskCard
        task={makeTask(patch)}
        active={false}
        selecting={false}
        checked={false}
        draggable={false}
        onClick={() => {}}
        onDragStart={() => {}}
        onDragEnd={() => {}}
      />
    </I18nContext.Provider>,
  )

describe('TaskCard', () => {
  it('shows the current stage and the progress bar for a running task', () => {
    const html = renderCard({
      stage: 'building_grids',
      stageLabel: '拼接网格图',
      progress: 44,
    })

    expect(html).toContain('测试视频')
    expect(html).toContain('拼接网格图')
    expect(html).toContain('role="progressbar"')
    expect(html).toContain('aria-valuenow="44"')
  })

  it('shows the counters kept in detail next to the stage', () => {
    const html = renderCard({
      stage: 'extracting_frames',
      stageLabel: '抽取画面',
      progress: 30,
      detail: { current: 12, total: 24, unit: 'frames' },
    })

    expect(html).toContain('12 / 24 帧')
  })

  it('falls back to the frontend stage mapping when the label is missing', () => {
    const html = renderCard({ stage: 'transcribing', stageLabel: null, progress: 30 })

    expect(html).toContain('转写音频')
  })

  it('keeps the failed stage visible instead of only a badge', () => {
    const html = renderCard({
      status: 'FAILED',
      stage: 'transcribing',
      stageLabel: '音频转写',
      progress: 40,
    })

    expect(html).toContain('音频转写')
    expect(html).toContain('失败')
  })

  it('omits the progress bar when the backend has no percentage', () => {
    const html = renderCard({
      status: 'PENDING',
      stage: 'queued',
      stageLabel: '排队中',
      progress: null,
    })

    expect(html).toContain('排队中')
    expect(html).not.toContain('role="progressbar"')
  })
})
