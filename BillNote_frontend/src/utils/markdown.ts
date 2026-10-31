/**
 * 把 LaTeX 的 \(...\) / \[...\] 分隔符换成 remark-math 认的 $...$ / $$...$$，
 * 并把 $$ 围栏强制拆到独立行。
 *
 * 为什么需要（spec 004、spec 020）：
 * - 模型输出的公式常用 LaTeX 原生分隔符，而 remark-math 只认 `$`；
 * - remark-math 的**块公式**要求 `$$` 单独占一行：模型写成
 *   `$$\begin{cases}…\end{cases}$$`（开符号和内容同一行）时，解析器认不出这是
 *   块公式，整段退化成普通文本，后面的 `$$` 还会两两错位，最后表现为
 *   「一大堆没渲染的公式 + 满屏红色报错」。所以这里把围栏拆到独立行，
 *   让 remark-math 无论模型怎么写都能拿到标准形态。
 *
 * 代码围栏内的内容是**代码**，不是公式，必须原样保留。
 */
const FENCE_RE = /^\s*(\x60{3,}|~{3,})/
const INLINE_MATH_RE = /\\\(([\s\S]+?)\\\)/g
const BLOCK_MATH_RE = /\\\[([\s\S]+?)\\\]/g

/**
 * 把 `$$` 围栏拆成独立行：`$$x$$` → `$$` / `x` / `$$`，
 * 跨行的 `$$\begin{cases}…` … `…\end{cases}$$` 同样拆成三行。
 *
 * 只处理围栏位置，不动公式内容本身 —— 换行在数学里是空白，拆行不改变语义。
 */
const isolateDollarFences = (text: string): string => {
  const out: string[] = []
  let inBlock = false

  for (const line of text.split('\n')) {
    if (inBlock) {
      const closeAt = line.indexOf('$$')
      if (closeAt === -1) {
        out.push(line)
        continue
      }
      const body = line.slice(0, closeAt)
      if (body.trim()) out.push(body.trim())
      out.push('$$')
      const rest = line.slice(closeAt + 2)
      if (rest.trim()) out.push(rest.trim())
      inBlock = false
      continue
    }

    const trimmedStart = line.trimStart()
    if (trimmedStart.startsWith('$$')) {
      const after = trimmedStart.slice(2)
      const closeAt = after.indexOf('$$')
      out.push('$$')
      if (closeAt === -1) {
        if (after.trim()) out.push(after.trim())
        inBlock = true
      } else {
        const body = after.slice(0, closeAt)
        if (body.trim()) out.push(body.trim())
        out.push('$$')
      }
      continue
    }

    // 句子中间的 `$$x$$`（模型偶尔这么写展示公式）：同样拆成独立的块。
    if (line.includes('$$')) {
      const parts = line.split('$$')
      parts.forEach((chunk, index) => {
        if (index % 2 === 0) {
          if (chunk.trim()) out.push(chunk.trim())
          return
        }
        out.push('$$')
        if (chunk.trim()) out.push(chunk.trim())
        out.push('$$')
      })
      continue
    }

    out.push(line)
  }

  return out.join('\n')
}

/** 逐段（非代码围栏部分）转换：先换分隔符，再整理 $$ 围栏。 */
const convertProse = (text: string): string =>
  isolateDollarFences(
    text
      .replace(BLOCK_MATH_RE, (_match, body: string) => `\n\n$$\n${body.trim()}\n$$\n\n`)
      // 行内公式不能跨行（remark-math 的行内 math 不认换行），折成空格。
      .replace(INLINE_MATH_RE, (_match, body: string) => `$${body.replace(/\s*\n\s*/g, ' ').trim()}$`)
  )

export const normalizeMathDelimiters = (markdown: string | null | undefined): string => {
  if (!markdown) return ''
  const out: string[] = []
  let prose: string[] = []
  let inFence = false

  // 整段处理而不是逐行：\[ ... \] 常常开括号一行、闭括号另一行（spec 020）。
  const flush = () => {
    if (!prose.length) return
    out.push(...convertProse(prose.join('\n')).split('\n'))
    prose = []
  }

  for (const line of String(markdown).split('\n')) {
    if (FENCE_RE.test(line)) {
      flush()
      inFence = !inFence
      out.push(line)
      continue
    }
    if (inFence) out.push(line)
    else prose.push(line)
  }
  flush()
  return out.join('\n')
}
