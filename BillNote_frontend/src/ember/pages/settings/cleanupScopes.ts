/**
 * 媒体清理的作用域（T-062 / 上游 UI 计划 §5）。
 *
 * 缺陷原样：预览按钮写死 `expired_only=true`，而"强制清理全部"走 `clean(false)`，
 * 于是"预览 12 项"和随后真正删掉的 300 项对不上 —— 预览本来是这个页面的确认步骤，
 * 口径不一致就失去了确认的意义。
 *
 * 现在作用域只有两个取值，预览与执行都从 `scopeExpiredOnly()` 取同一个布尔，
 * 不存在"预览一个口径、执行另一个口径"的写法。抽成纯模块是为了能脱 DOM 断言。
 */

export type CleanupScope = 'expired' | 'all'

/** 该作用域是否只删已到期资源；预览与执行必须都走这里。 */
export function scopeExpiredOnly(scope: CleanupScope): boolean {
  return scope === 'expired'
}
