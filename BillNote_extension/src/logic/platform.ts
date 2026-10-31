import type { Platform } from './types'

// 与 backend/app/validators/video_url_validator.py 保持一致：生成链路只认 B 站。
// 其它站点返回 null，由 popup 显示「不支持该平台」——识别失败要明确说出来，
// 而不是让用户点完按钮才在后端收到一个 400。
export function detectPlatform(url: string | undefined | null): Platform | null {
  if (!url)
    return null
  if (/bilibili\.com\/video\//.test(url) || /b23\.tv\//.test(url))
    return 'bilibili'
  return null
}

export const PLATFORM_LABELS: Record<Platform, string> = {
  bilibili: '哔哩哔哩',
}
