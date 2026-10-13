/**
 * 分组名 → 下载文件名。分组名是用户随手起的（可能带 `\ / : * ? " < > |` 与控制字符），
 * 直接塞进 `link.download` 在 Windows 上会被浏览器丢掉或截断，所以这里统一洗一遍。
 */
// eslint-disable-next-line no-control-regex -- 控制字符正是要剥掉的目标，不是误写
const ILLEGAL_FILENAME_CHARS = /[\\/:*?"<>|\u0000-\u001f\u007f]/g

/** 清洗成安全的文件名片段：剥掉非法字符、收拢空白、去掉首尾的点与空格。 */
export const sanitizeFileName = (raw: string, fallback = '笔记归档'): string => {
  const cleaned = raw
    .replace(ILLEGAL_FILENAME_CHARS, '_')
    .replace(/\s+/g, ' ')
    .replace(/^[.\s]+|[.\s]+$/g, '')
    .slice(0, 80)
  return cleaned || fallback
}
