/**
 * In-document anchors for the reader.
 *
 * 笔记里的目录与左侧大纲都是「跳到本文某个标题」，但两边的 id 来源不同：标题 id 由
 * rehype-slug（github-slugger）生成，大纲 id 由 outline.ts 的 slugify 生成，模型自己写的
 * 目录链接又是第三种写法。三套算法只要有一处不同，`#id` 就指不到任何元素，浏览器于是
 * 按普通链接处理 —— 路由一旦接管，当前笔记会被整页换掉。
 *
 * 所以这里不赌 id 相等：先按 id 找，找不到就按标题文本归一化后匹配。
 */

const normalize = (value: string): string => {
  let text = value
  try {
    text = decodeURIComponent(value)
  } catch {
    text = value
  }
  return text.toLowerCase().replace(/[^\p{L}\p{N}]+/gu, '')
}

/**
 * 把页面滚到某个锚点对应的标题。返回是否找到目标。
 *
 * 找不到时返回 false，调用方应让浏览器按默认行为处理（例如真的外链跳转）。
 */
export function scrollToAnchor(raw: string, root?: HTMLElement | null): boolean {
  const container = root ?? document.body
  const target = raw.replace(/^#/, '').trim()
  if (!target) return false

  let element: HTMLElement | null = null
  try {
    element =
      document.getElementById(target) ?? document.getElementById(decodeURIComponent(target))
  } catch {
    element = document.getElementById(target)
  }

  if (!element) {
    const wanted = normalize(target)
    if (!wanted) return false
    const headings = Array.from(
      container.querySelectorAll<HTMLElement>('h1, h2, h3, h4, h5, h6'),
    )
    element =
      headings.find(heading => normalize(heading.textContent ?? '') === wanted) ??
      headings.find(heading => normalize(heading.textContent ?? '').startsWith(wanted)) ??
      null
  }

  if (!element) return false

  const reduced = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false
  element.scrollIntoView({ behavior: reduced ? 'auto' : 'smooth', block: 'start' })
  element.setAttribute('tabindex', '-1')
  element.focus({ preventScroll: true })
  return true
}
