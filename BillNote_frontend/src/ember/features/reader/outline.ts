/**
 * Outline helpers for the reader. They live in their own module because
 * MarkdownNote.tsx must export nothing but a component for React Fast Refresh
 * to hot-swap it.
 */

export interface OutlineItem {
  id: string
  text: string
  depth: number
}

/** Heading anchors, so the outline can jump without a router. */
export const slugify = (text: string): string =>
  text
    .trim()
    .toLowerCase()
    .replace(/[^\p{L}\p{N}\s-]/gu, '')
    .replace(/\s+/g, '-')

/** Extract h2/h3 headings for the reader outline. */
export const extractOutline = (markdown: string): OutlineItem[] => {
  const items: OutlineItem[] = []
  const seen = new Map<string, number>()
  for (const line of markdown.split('\n')) {
    const match = /^(#{2,3})\s+(.+?)\s*$/.exec(line)
    if (!match) continue
    const text = match[2].replace(/[#*`]/g, '').trim()
    const base = slugify(text) || 'section'
    const count = seen.get(base) ?? 0
    seen.set(base, count + 1)
    items.push({ id: count === 0 ? base : `${base}-${count}`, text, depth: match[1].length })
  }
  return items
}
