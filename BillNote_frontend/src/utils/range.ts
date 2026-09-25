/**
 * 解析批量勾选输入框里的范围表达式，返回 1-based 的行号数组（升序去重）。
 *
 * 支持：
 *   - 单个数字：`5`
 *   - 范围：`3-7`（倒序 `7-3` 会被自动纠正）
 *   - 逗号分隔：`1,3-5,9`
 *
 * 非法片段静默忽略；结果会被裁剪到 [1, max]。
 */
export function parseRangeSelection(input: string, max: number): number[] {
  if (!input || max <= 0) return []

  const picked = new Set<number>()

  for (const raw of input.split(',')) {
    const token = raw.trim()
    if (!token) continue

    const range = token.match(/^(\d+)\s*-\s*(\d+)$/)
    if (range) {
      let start = parseInt(range[1], 10)
      let end = parseInt(range[2], 10)
      if (start > end) [start, end] = [end, start]
      for (let i = Math.max(1, start); i <= Math.min(max, end); i++) {
        picked.add(i)
      }
      continue
    }

    const single = token.match(/^\d+$/)
    if (single) {
      const n = parseInt(token, 10)
      if (n >= 1 && n <= max) picked.add(n)
    }
  }

  return [...picked].sort((a, b) => a - b)
}
