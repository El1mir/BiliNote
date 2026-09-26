/**
 * 后端 progress 协议已经是 0-100 的百分比（例如 40 表示 40%）。
 * 前端只做数值校验和区间夹取，不再二次乘 100，避免出现 4000%。
 */
export function toPercent(value: unknown): number | null {
  if (typeof value !== 'number' || !Number.isFinite(value)) return null
  return Math.max(0, Math.min(100, Math.round(value)))
}
