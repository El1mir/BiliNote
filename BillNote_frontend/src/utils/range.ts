/**
 * 解析「页码范围」输入（spec 018 决策 7）。
 *
 * 支持 `3`、`3-6`、`1,3-5,9` 以及中文逗号/空格分隔；倒序范围自动纠正，
 * 越界序号裁剪到 `[1, max]`，非法片段直接忽略（用户输入到一半不该报错）。
 * 返回**去重且升序**的序号数组。
 */
export const parseRangeSelection = (input: string, max: number): number[] => {
  if (!input || max <= 0) return []
  const picked = new Set<number>()
  for (const raw of input.split(/[,，\s]+/)) {
    const token = raw.trim()
    if (!token) continue
    const match = /^(\d+)(?:-(\d+))?$/.exec(token)
    if (!match) continue
    const start = Number(match[1])
    const end = match[2] === undefined ? start : Number(match[2])
    const low = Math.min(start, end)
    const high = Math.max(start, end)
    for (let value = low; value <= high; value += 1) {
      if (value >= 1 && value <= max) picked.add(value)
    }
  }
  return [...picked].sort((a, b) => a - b)
}
