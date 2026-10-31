import { describe, expect, it } from 'vitest'

import { normalizeMathDelimiters } from '@/utils/markdown'

/**
 * spec 020：模型常把块公式写成「$$ 和内容同一行」，remark-math 认不出这种形态，
 * 整段退化成普通文本、后面的 $$ 还会两两错位 —— 读者看到的就是「一堆没渲染的
 * 公式 + 满屏红色报错」。这里钉住规范化后的三种标准形态。
 */
describe('normalizeMathDelimiters —— 块公式围栏（spec 020）', () => {
  it('跨行的 \\[...\\] 也能转成 $$ 块', () => {
    const md = ['设方程', '\\[', 'x^2 + y^2 = 1', '\\]', '结束'].join('\n')
    const out = normalizeMathDelimiters(md)
    expect(out).not.toContain('\\[')
    expect(out).toContain('$$\nx^2 + y^2 = 1\n$$')
  })

  it('$$ 与内容同一行时拆成独立行', () => {
    const md = ['$$\\begin{cases} a=1\\\\ b=2 \\end{cases}$$', '正文'].join('\n')
    expect(normalizeMathDelimiters(md)).toBe(
      ['$$', '\\begin{cases} a=1\\\\ b=2 \\end{cases}', '$$', '正文'].join('\n')
    )
  })

  it('开符号与内容同行、闭符号在末行的 $$ 块也能拆好', () => {
    const md = ['前文', '', '$$\\begin{cases}', 'a=1\\\\', 'b=2', '\\end{cases}$$', '', '后文'].join(
      '\n'
    )
    const out = normalizeMathDelimiters(md)
    expect(out).not.toContain('$$\\begin{cases}')
    expect(out).not.toContain('\\end{cases}$$')
    expect(out).toContain('$$\n\\begin{cases}\na=1\\\\\nb=2\n\\end{cases}\n$$')
  })

  it('行内 $...$ 原样保留，不被拆行', () => {
    const md = '当 $x_0=5$ 且 $y_0=-1$ 时'
    expect(normalizeMathDelimiters(md)).toBe(md)
  })

  it('跨行的 \\(...\\) 折成单行', () => {
    expect(normalizeMathDelimiters('\\( a +\nb \\)')).toBe('$a + b$')
  })

  it('代码围栏里的 $$ 不动', () => {
    const md = ['\x60\x60\x60md', '$$x$$', '\x60\x60\x60'].join('\n')
    expect(normalizeMathDelimiters(md)).toBe(md)
  })
})
