import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { renderToStaticMarkup } from 'react-dom/server'
import { I18nContext, type I18nValue } from '../../src/ember/i18n/context'
import { dictionaries, format } from '../../src/ember/i18n/strings'
import type { Locale, MessageKey } from '../../src/ember/i18n/strings'
import { MarkdownNote } from '../../src/ember/features/reader/MarkdownNote'
import { NotePanel } from '../../src/ember/features/reader/NotePanel'
import { TranscriptView } from '../../src/ember/features/reader/TranscriptView'
import { prismStyleFor } from '../../src/ember/features/reader/codeTheme'
import { extractOutline } from '../../src/ember/features/reader/outline'
import { filterTranscript } from '../../src/ember/features/reader/transcriptSearch'
import type { Task } from '../../src/store/taskStore'

/**
 * spec 021 阅读区（W2）的回归钉：
 *
 * 阅读区的问题几乎都不是「渲染不出来」，而是**某一条长文约束悄悄丢了**：
 * 列宽被拉宽、表格把整页撑出横向滚动、代码块在深色主题里变成一团、
 * 图片点开后键盘用户回不到原处。这些在浅色桌面截图里全都看不出来，
 * 所以这里把布局契约（class 与 reader.css 规则）和纯逻辑（大纲 id、
 * 转写计数、代码配色映射）钉住；灯箱的真实键盘行为用浏览器证据补。
 */

const i18n = (locale: Locale): I18nValue => ({
  locale,
  setLocale: () => {},
  t: (key: MessageKey, values?: Record<string, string | number>) =>
    format(dictionaries[locale][key] ?? key, values),
})

const render = (node: React.ReactNode) =>
  renderToStaticMarkup(<I18nContext.Provider value={i18n('zh-CN')}>{node}</I18nContext.Provider>)

const makeTask = (patch: Partial<Task> = {}): Task =>
  ({
    id: 'task-w2',
    markdown: '',
    transcript: { full_text: '', language: 'zh', raw: {}, segments: [] },
    status: 'SUCCESS',
    platform: 'bilibili',
    groupId: null,
    groupName: '',
    audioMeta: {
      cover_url: '',
      duration: 0,
      file_path: '',
      platform: 'bilibili',
      raw_info: null,
      title: '阅读区测试视频',
      video_id: 'BV1',
    },
    createdAt: new Date().toISOString(),
    formData: { video_url: 'https://www.bilibili.com/video/BV1' },
    ...patch,
  }) as Task

const NOTE = `# 标题

## 第一节

正文段落，带一个[站内锚点](#第二节)和一个[外链](https://example.com)。

| 列一 | 列二 |
| --- | --- |
| a | b |

> 引用一段原文

\`\`\`ts
const answer: number = 42
\`\`\`

![截图说明](https://example.com/shot.png)

## 第二节

第二段正文。

## 第三节

第三段正文。
`

describe('reader 正文约束', () => {
  it('caps the reading column at 68ch and keeps the outline sticky', () => {
    const html = render(<NotePanel task={makeTask({ markdown: NOTE })} />)
    expect(html).toContain('max-w-[68ch]')
    expect(html).toContain('sticky')
    // 大纲出现的前提是有足够多标题（>2 条 h2/h3）
    expect(html).toContain('大纲')
  })

  it('wraps tables in a horizontal scroller instead of widening the column', () => {
    const html = render(<MarkdownNote markdown={NOTE} />)
    expect(html).toContain('overflow-x-auto')
    expect(html).toMatch(/<div class="[^"]*overflow-x-auto[^"]*"><table/)
  })

  it('leaves images on the trigger button and never lets them exceed the column', () => {
    const html = render(<MarkdownNote markdown={NOTE} />)
    expect(html).toContain('ember-zoom-trigger')
    expect(html).toMatch(/<button[^>]*aria-label="查看大图[^"]*"/)
    expect(html).toMatch(/<img[^>]*max-w-full/)
  })

  it('keeps every reader.css long-form rule in place', () => {
    const css = readFileSync(join(__dirname, '../../src/ember/reader.css'), 'utf8')
    // 正文衬线 + 16/28 行高
    expect(css).toMatch(/\.ember-markdown\s*{[^}]*font-family:\s*var\(--font-serif\)/)
    expect(css).toMatch(/\.ember-markdown :is\(p, li, blockquote\)\s*{[^}]*font-size:\s*1rem[^}]*line-height:\s*1\.75/)
    // 代码/图片不撑破列
    expect(css).toMatch(/\.ember-markdown pre\s*{[^}]*overflow-x:\s*auto/)
    expect(css).toMatch(/\.ember-markdown img\s*{[^}]*max-width:\s*100%/)
    // 锚点要躲开吸顶顶栏
    expect(css).toMatch(/scroll-margin-top:\s*6rem/)
  })

  it('renders the empty state when the task has no markdown yet', () => {
    const html = render(<NotePanel task={makeTask()} />)
    expect(html).toContain('任务完成后这里会显示生成的笔记')
  })

  it('keeps copy, download and archive entry points', () => {
    const html = render(<NotePanel task={makeTask({ markdown: NOTE })} />)
    expect(html).toContain('复制 Markdown')
    expect(html).toContain('下载 Markdown')
    expect(html).toContain('导出归档')
  })
})

describe('reader 主题与搜索', () => {
  it('switches the Prism palette with the theme', () => {
    const light = prismStyleFor('light')
    const dark = prismStyleFor('dark')
    expect(light).toBeTruthy()
    expect(dark).toBeTruthy()
    expect(light).not.toBe(dark)
    // 两块都要有真正的关键字色，否则等于没上色
    expect(light.keyword).toBeTruthy()
    expect(dark.keyword).toBeTruthy()
  })

  it('filters transcript lines case-insensitively and counts the hits', () => {
    const segments = [
      { start: 0, text: '开场白' },
      { start: 12, text: 'React 组件的状态' },
      { start: 30, text: '这里又提到 react' },
    ]
    expect(filterTranscript(segments, '')).toHaveLength(3)
    expect(filterTranscript(segments, '  ')).toHaveLength(3)
    expect(filterTranscript(segments, 'React')).toHaveLength(2)
    expect(filterTranscript(segments, '不存在的词')).toHaveLength(0)
  })

  it('renders the transcript search box and hit counter wiring', () => {
    const task = makeTask({
      transcript: {
        full_text: 'a',
        language: 'zh',
        raw: {},
        segments: [{ start: 65, text: '第一段转写' }],
      } as Task['transcript'],
    })
    const html = render(<TranscriptView task={task} />)
    expect(html).toContain('aria-label="搜索"')
    expect(html).toContain('01:05')
    // 未输入时不该出现计数（空查询等于全量）
    expect(html).not.toContain('匹配 0')
  })

  it('gives the outline stable ids and depth from the headings', () => {
    expect(extractOutline(NOTE)).toEqual([
      { id: '第一节', text: '第一节', depth: 2 },
      { id: '第二节', text: '第二节', depth: 2 },
      { id: '第三节', text: '第三节', depth: 2 },
    ])
  })
})
