import { describe, expect, it } from 'vitest'

import { normalizeMathDelimiters } from '@/utils/markdown'

describe('normalizeMathDelimiters', () => {
  it('把行内 \\(...\\) 转成 $...$', () => {
    expect(normalizeMathDelimiters("求导：\\( f'(x) = \\frac{1 - \\ln x}{x^2} \\)。")).toBe(
      "求导：$f'(x) = \\frac{1 - \\ln x}{x^2}$。"
    )
  })

  it('把块级 \\[...\\] 转成 $$...$$', () => {
    const out = normalizeMathDelimiters('函数：\\[ f(x) = \\frac{\\ln x}{x} \\]')
    expect(out).toContain('$$')
    expect(out).toContain('f(x) = \\frac{\\ln x}{x}')
    expect(out).not.toContain('\\[')
  })

  it('已经是 $...$ 的内容原样返回', () => {
    // $$ 围栏的规范化在 spec 020 单独覆盖：这里只钉行内公式不被改动。
    const md = '公式：$x^2$ 与 $\\alpha$'
    expect(normalizeMathDelimiters(md)).toBe(md)
  })

  it('没有 LaTeX 分隔符时原样返回', () => {
    expect(normalizeMathDelimiters('普通文本')).toBe('普通文本')
  })

  it('空值返回空串', () => {
    expect(normalizeMathDelimiters('')).toBe('')
    expect(normalizeMathDelimiters(null)).toBe('')
    expect(normalizeMathDelimiters(undefined)).toBe('')
  })

  it('不破坏代码块里的反斜杠括号', () => {
    const md = ['```txt', '\\( x^2 \\)', '```', '', '正文 \\( y \\)'].join('\n')
    const out = normalizeMathDelimiters(md)
    expect(out).toContain('\\( x^2 \\)') // 代码块内保持原样
    expect(out).toContain('正文 $y$')
  })

  it('一条内容里多个公式都能转换', () => {
    const out = normalizeMathDelimiters('\\(a\\) 与 \\(b\\)')
    expect(out).toBe('$a$ 与 $b$')
  })
})
