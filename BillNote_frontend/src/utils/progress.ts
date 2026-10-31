/**
 * 后端进度（0–100 的整数）转成前端用的百分比。
 *
 * 非数字（null / undefined / NaN / 字符串）一律返回 null，让调用方自己决定
 * 是「隐藏进度条」还是「显示 0%」—— 把未知值猜成 0 会让用户以为任务卡住了。
 */
export const toPercent = (value: unknown): number | null => {
  if (typeof value !== 'number' || !Number.isFinite(value)) return null
  return Math.min(100, Math.max(0, value))
}
