import { createContext, useContext } from 'react'

/**
 * 控件无障碍上下文：Field 生成 message/hint 节点 id 后下发给子控件，
 * 由 Input/Select/Textarea 自己挂 aria-describedby / aria-invalid。
 *
 * 用 context 而不是 cloneElement，是因为子控件可能被包装（Select 外面套了定位 div），
 * 克隆会漏掉包装层；context 只要求子控件在 Field 内部。
 *
 * 单独成文件而不是放在 Field.tsx 里：组件文件只导出组件，
 * 才能让 react-refresh 的 Fast Refresh 正常工作（eslint react-refresh 规则）。
 */
export type FieldControlA11y = {
  /** 控件 id；Field 未收到 htmlFor 时由 useId 兜底，保证 label 与控件能关联。 */
  controlId: string
  /** 错误/提示节点的 id，供控件写入 aria-describedby。 */
  describedBy?: string
  /** 错误存在时为 true；控件据此写 aria-invalid。 */
  invalid: boolean
}

export const FieldContext = createContext<FieldControlA11y | null>(null)

/** 读取 Field 下发的无障碍属性；不在 Field 内时返回 null。 */
export function useFieldControlA11y(): FieldControlA11y | null {
  return useContext(FieldContext)
}
