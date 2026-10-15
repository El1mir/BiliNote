/**
 * 把后端 / 历史持久化数据安全地转成可渲染文本。
 * 旧任务的 title / model_name / scene 等字段可能被存成对象或 null，
 * 直接放进 JSX 会触发 React 的 "Objects are not valid as a React child"。
 */
export function asText(value: unknown, fallback = ''): string {
  if (value === null || value === undefined) return fallback
  if (typeof value === 'string') return value
  if (typeof value === 'number' || typeof value === 'boolean') return String(value)
  if (value instanceof Date) return value.toLocaleString('zh-CN')
  if (Array.isArray(value))
    return value
      .map(item => asText(item))
      .filter(Boolean)
      .join('、')
  if (typeof value === 'object') {
    const record = value as Record<string, unknown>
    for (const key of ['title', 'name', 'label', 'value', 'model_name', 'scene', 'detail', 'text']) {
      if (key in record) {
        const text = asText(record[key])
        if (text) return text
      }
    }
    return fallback
  }
  return fallback
}
