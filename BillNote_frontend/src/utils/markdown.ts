/**
 * LaTeX 分隔符归一化（spec 004）。
 *
 * 模型（尤其中文数学讲解）经常输出 `\( ... \)` / `\[ ... \]` 这种 LaTeX 原生分隔符，
 * 但前端渲染链是 react-markdown + remark-math + rehype-katex，remark-math 只认
 * `$...$` / `$$...$$`。于是 `\(` 被 Markdown 当成转义，公式直接以纯文本露出。
 *
 * 这里在交给 ReactMarkdown 之前，把两种分隔符换成 remark-math 认识的形式。
 */

/** 只处理非代码块部分，避免破坏代码示例里的 `\(`。 */
function mapOutsideCodeFences(input: string, fn: (chunk: string) => string): string {
  // 按成对的 ``` 围栏切分：奇数下标是围栏内容，原样保留
  const parts = input.split(/(```[\s\S]*?```)/g)
  return parts.map((part, index) => (index % 2 === 1 ? part : fn(part))).join('')
}

function convertChunk(chunk: string): string {
  return (
    chunk
      // \[ ... \] → $$ ... $$（块级公式单独成段，避免被当成行内）
      .replace(/\\\[([\s\S]*?)\\\]/g, (_m, body: string) => `\n$$\n${body.trim()}\n$$\n`)
      // \( ... \) → $ ... $
      .replace(/\\\(([\s\S]*?)\\\)/g, (_m, body: string) => `$${body.trim()}$`)
  )
}

/**
 * 把 `\(...\)` / `\[...\]` 归一化成 `$...$` / `$$...$$`。
 *
 * 已经是 `$` 形式的公式不受影响；内容里没有这两种分隔符时原样返回。
 */
export function normalizeMathDelimiters(input: string | null | undefined): string {
  if (!input) return ''
  if (!input.includes('\\(') && !input.includes('\\[')) return input
  return mapOutsideCodeFences(input, convertChunk)
}
