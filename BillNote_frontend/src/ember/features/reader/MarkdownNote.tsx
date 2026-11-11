import { useMemo, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import type { Components } from 'react-markdown'
import remarkGfm from 'remark-gfm'
import remarkMath from 'remark-math'
import rehypeKatex from 'rehype-katex'
import rehypeSlug from 'rehype-slug'
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter'
import { prismStyleFor } from '@/ember/features/reader/codeTheme'
import 'katex/dist/katex.min.css'
import { scrollToAnchor } from '@/ember/features/reader/anchors'
import { resolveAssetUrl } from '@/ember/lib/assets'
import { Dialog } from '@/ember/ui/Dialog'
import { useI18n } from '@/ember/i18n/context'
import { useTheme } from '@/ember/theme/theme'
import { normalizeMathDelimiters } from '@/utils/markdown'
import { cn } from '@/ember/lib/cn'

type MarkdownNoteProps = {
  markdown: string
  className?: string
}

type ComponentOptions = {
  /** Opens the lightbox for a resolved image URL. */
  onOpenImage: (src: string, alt: string) => void
  /** Prism palette must follow the surface it is painted on. */
  dark: boolean
  viewImageLabel: string
}

/**
 * Element overrides for the reader.
 *
 * Every renderer destructures `node` out instead of forwarding it. react-markdown
 * hands custom components a hast node for the element; spreading it onto a DOM
 * tag would render an invalid `node="[object Object]"` attribute. The rest of
 * the props ARE real HTML attributes, so those are forwarded.
 *
 * Built per render rather than module-level so the lightbox trigger has a
 * stable callback and the code palette follows the current theme.
 */
function buildComponents({ onOpenImage, dark, viewImageLabel }: ComponentOptions): Components {
  const heading = 'scroll-mt-24 leading-tight first:mt-0 font-display'
  return {
    h1: ({ node: _node, children, ...props }) => (
      <h1 className={`${heading} text-section sm:text-headline mt-8 mb-4`} {...props}>
        {children}
      </h1>
    ),
    h2: ({ node: _node, children, ...props }) => (
      <h2 className={`${heading} text-subhead sm:text-section mt-8 mb-3 leading-snug`} {...props}>
        {children}
      </h2>
    ),
    h3: ({ node: _node, children, ...props }) => (
      <h3 className={`${heading} text-body sm:text-subhead mt-6 mb-2 leading-snug`} {...props}>
        {children}
      </h3>
    ),
    h4: ({ node: _node, children, ...props }) => (
      <h4 className="text-body mt-5 mb-2 scroll-mt-24 font-semibold" {...props}>
        {children}
      </h4>
    ),
    p: ({ node: _node, children, ...props }) => (
      <p className="text-body text-ink my-3 leading-[1.75]" {...props}>
        {children}
      </p>
    ),
    a: ({ node: _node, href, children, ...props }) => {
      // 站内锚点（模型写的目录链接）必须留在本页滚动。给 _blank 会新开一个空白页，
      // 交给路由则会被当成跳转，直接把读者带离笔记。
      if (href && href.startsWith('#')) {
        return (
          <a
            href={href}
            className="text-accent decoration-accent/30 hover:decoration-accent underline underline-offset-2"
            onClick={event => {
              if (scrollToAnchor(href)) event.preventDefault()
            }}
          >
            {children}
          </a>
        )
      }
      return (
        <a
          className="text-accent decoration-accent/30 hover:decoration-accent underline underline-offset-2"
          target="_blank"
          rel="noreferrer"
          href={href}
          {...props}
        >
          {children}
        </a>
      )
    },
    ul: ({ node: _node, children, ...props }) => (
      <ul className="text-body my-3 flex list-disc flex-col gap-1.5 pl-5 leading-relaxed" {...props}>
        {children}
      </ul>
    ),
    ol: ({ node: _node, children, ...props }) => (
      <ol
        className="text-body my-3 flex list-decimal flex-col gap-1.5 pl-5 leading-relaxed"
        {...props}
      >
        {children}
      </ol>
    ),
    blockquote: ({ node: _node, children, ...props }) => (
      <blockquote
        className="rounded-r-control border-accent bg-accent-soft/60 text-ink-soft my-4 border-l-2 py-1 pr-3 pl-4"
        {...props}
      >
        {children}
      </blockquote>
    ),
    table: ({ node: _node, children, ...props }) => (
      <div className="rounded-surface border-line my-4 w-full overflow-x-auto border">
        <table className="text-small w-full border-collapse" {...props}>
          {children}
        </table>
      </div>
    ),
    thead: ({ node: _node, children, ...props }) => (
      <thead className="bg-surface" {...props}>
        {children}
      </thead>
    ),
    th: ({ node: _node, children, ...props }) => (
      <th className="border-line border-b px-3 py-2 text-left font-semibold" {...props}>
        {children}
      </th>
    ),
    td: ({ node: _node, children, ...props }) => (
      <td className="border-line/70 border-b px-3 py-2 align-top" {...props}>
        {children}
      </td>
    ),
    hr: ({ node: _node, ...props }) => <hr className="border-line my-6" {...props} />,
    // 图片点开是 Dialog（Escape / 遮罩关闭 / 关闭后焦点回触发元素都由
    // useOverlayFocus 负责）。原来的 react-medium-image-zoom 只做缩放，
    // 上面三条无障碍行为一条都没保证。
    img: ({ node: _node, src, alt, ...props }) => {
      const resolved = resolveAssetUrl(src)
      return (
        <button
          type="button"
          onClick={() => onOpenImage(resolved ?? '', alt ?? '')}
          aria-label={alt ? `${viewImageLabel}：${alt}` : viewImageLabel}
          className="ember-zoom-trigger my-4 block max-w-full cursor-zoom-in rounded-surface border-line focus-visible:ring-accent focus-visible:ring-2 focus-visible:outline-none"
        >
          <img
            src={resolved}
            alt={alt ?? ''}
            className="rounded-surface max-w-full"
            loading="lazy"
            decoding="async"
            {...props}
          />
        </button>
      )
    },
    code: ({ node: _node, className: codeClass, children, ...props }) => {
      const match = /language-(\w+)/.exec(codeClass ?? '')
      if (!match) {
        return (
          <code
            className="rounded-inline bg-raised text-ink px-1.5 py-0.5 font-mono text-[0.9em]"
            {...props}
          >
            {children}
          </code>
        )
      }
      return (
        <SyntaxHighlighter
          language={match[1]}
          // 浅色主题配 oneLight、深色配 oneDark：硬编码 oneLight 在深色画布上
          // 会把关键字染成近黑的浅色系颜色，等于整块代码看不清。
          style={prismStyleFor(dark ? 'dark' : 'light')}
          customStyle={{
            margin: '1rem 0',
            borderRadius: '12px',
            border: '1px solid var(--color-line)',
            background: 'var(--color-surface)',
            fontSize: '13px',
            padding: '14px 16px',
          }}
          codeTagProps={{ style: { fontFamily: 'IBM Plex Mono, ui-monospace, monospace' } }}
        >
          {String(children).replace(/\n$/, '')}
        </SyntaxHighlighter>
      )
    },
  }
}

/**
 * 把提示词里的时间标记还原成人能读的样子。
 *
 * 格式开关要求每个 `##` 标题后面跟 `*Content-[mm:ss]`，模型也会在截图位置写
 * `*Screenshot-[mm:ss]`。星号和方括号是给后处理用的记号，原样渲染时标题会变成
 * 「标题 *Content-[32:35]」——读者看到的是一段没清理干净的源码。
 * 换成行内代码：`32:35` 与 `截图 32:35`，既保留时间点又不抢标题的视觉重量。
 */
function humanizeTimeMarks(markdown: string): string {
  return markdown
    .replace(/\s*\*Content-\[(\d{1,2}:\d{2})\]/g, ' `$1`')
    .replace(/\s*\*Screenshot-\[(\d{1,2}:\d{2})\]/g, ' `截图 $1`')
}

/**
 * Markdown reader: serif body on a 68ch measure, graphite/teal chrome, and a
 * lightbox that keeps keyboard users oriented.
 */
export function MarkdownNote({ markdown, className }: MarkdownNoteProps) {
  const { t } = useI18n()
  const { resolved } = useTheme()
  const [preview, setPreview] = useState<{ src: string; alt: string } | null>(null)

  // spec 004：先把 LaTeX 的 \(...\) / \[...\] 换成 remark-math 认的 $...$，
  // 再做时间标记的人话化。顺序不能反 —— 公式里出现 \[2mm] 之类的间距写法时，
  // 先做时间标记替换会把括号内容当成标记。
  const content = useMemo(
    () => humanizeTimeMarks(normalizeMathDelimiters(markdown ?? '')),
    [markdown]
  )

  const components = useMemo(
    () =>
      buildComponents({
        onOpenImage: (src, alt) => setPreview({ src, alt }),
        dark: resolved === 'dark',
        viewImageLabel: t('note.viewImage'),
      }),
    [resolved, t]
  )

  return (
    <div className={cn('ember-markdown', className)}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm, remarkMath]}
        // spec 020：单个公式写坏不该把整篇笔记炸掉 —— 关掉 throwOnError，
        // 坏公式由 KaTeX 原地标出来，其余内容照常渲染。
        rehypePlugins={[[rehypeKatex, { throwOnError: false, strict: false }], rehypeSlug]}
        components={components}
      >
        {content}
      </ReactMarkdown>

      <Dialog
        open={preview !== null}
        onClose={() => setPreview(null)}
        title={preview?.alt || t('note.lightboxAlt')}
        size="xl"
      >
        {preview ? (
          <img
            src={preview.src}
            alt={preview.alt || t('note.lightboxAlt')}
            className="rounded-surface mx-auto max-h-[70vh] w-auto max-w-full"
          />
        ) : null}
      </Dialog>
    </div>
  )
}
