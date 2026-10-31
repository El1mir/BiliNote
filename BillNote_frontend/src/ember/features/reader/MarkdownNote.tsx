import { useMemo } from 'react'
import ReactMarkdown from 'react-markdown'
import type { Components } from 'react-markdown'
import remarkGfm from 'remark-gfm'
import remarkMath from 'remark-math'
import rehypeKatex from 'rehype-katex'
import rehypeSlug from 'rehype-slug'
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter'
import { oneLight } from 'react-syntax-highlighter/dist/esm/styles/prism'
import 'katex/dist/katex.min.css'
import Zoom from 'react-medium-image-zoom'
import 'react-medium-image-zoom/dist/styles.css'
import { scrollToAnchor } from '@/ember/features/reader/anchors'
import { resolveAssetUrl } from '@/ember/lib/assets'
import { normalizeMathDelimiters } from '@/utils/markdown'
import { cn } from '@/ember/lib/cn'

type MarkdownNoteProps = {
  markdown: string
  className?: string
}

/**
 * Element overrides for the reader.
 *
 * Every renderer destructures `node` out instead of forwarding it. react-markdown
 * hands custom components a hast node for the element; spreading it onto a DOM
 * tag would render an invalid `node="[object Object]"` attribute. The rest of the
 * props ARE real HTML attributes, so those are forwarded.
 */
const components: Components = {
  h1: ({ node: _node, children, ...props }) => (
    <h1
      className="font-display text-section sm:text-headline mt-8 mb-4 scroll-mt-24 leading-tight first:mt-0"
      {...props}
    >
      {children}
    </h1>
  ),
  h2: ({ node: _node, children, ...props }) => (
    <h2
      className="font-display text-subhead sm:text-section mt-8 mb-3 scroll-mt-24 leading-snug first:mt-0"
      {...props}
    >
      {children}
    </h2>
  ),
  h3: ({ node: _node, children, ...props }) => (
    <h3
      className="font-display text-body sm:text-subhead mt-6 mb-2 scroll-mt-24 leading-snug"
      {...props}
    >
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
    // HashRouter 下还会被当成路由跳转，直接把读者带离笔记。
    if (href && href.startsWith('#')) {
      return (
        <a
          href={href}
          className="text-ember decoration-ember/30 hover:decoration-ember underline underline-offset-2"
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
        className="text-ember decoration-ember/30 hover:decoration-ember underline underline-offset-2"
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
      className="rounded-r-control border-ember bg-ember-soft/60 text-ink-soft my-4 border-l-2 py-1 pr-3 pl-4"
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
  img: ({ node: _node, src, alt, ...props }) => (
    <span className="my-4 block">
      <Zoom wrapElement="span">
        <img
          src={resolveAssetUrl(src)}
          alt={alt ?? ''}
          className="rounded-surface border-line max-w-full cursor-zoom-in border"
          loading="lazy"
          decoding="async"
          {...props}
        />
      </Zoom>
    </span>
  ),
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
        style={oneLight}
        customStyle={{
          margin: '1rem 0',
          borderRadius: '12px',
          border: '1px solid var(--color-line)',
          background: 'var(--color-surface)',
          fontSize: '13px',
          padding: '14px 16px',
        }}
        codeTagProps={{ style: { fontFamily: 'Fira Code, ui-monospace, monospace' } }}
      >
        {String(children).replace(/\n$/, '')}
      </SyntaxHighlighter>
    )
  },
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
 * Markdown reader tuned to Ember: warm neutrals, Playfair headings,
 * Fira Code blocks. Long-form content is the one place generous rhythm pays off.
 */
export function MarkdownNote({ markdown, className }: MarkdownNoteProps) {
  // spec 004：先把 LaTeX 的 \(...\) / \[...\] 换成 remark-math 认的 $...$，
  // 再做时间标记的人话化。顺序不能反 —— 公式里出现 \[2mm] 之类的间距写法时，
  // 先做时间标记替换会把括号内容当成标记。
  const content = useMemo(
    () => humanizeTimeMarks(normalizeMathDelimiters(markdown ?? '')),
    [markdown]
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
    </div>
  )
}
