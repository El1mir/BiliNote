import { setDownloaderCookie } from './api'
import type { Platform } from './types'

// 后端期望的 cookie 字符串格式：name=value; name=value; ...
// 见 backend/app/downloaders/bilibili_downloader.py 的 split("; ")
const COOKIE_DOMAINS: Record<Platform, string> = {
  bilibili: '.bilibili.com',
}

export const SUPPORTED_COOKIE_PLATFORMS: Platform[] = ['bilibili']

export async function readBrowserCookies(platform: Platform): Promise<string> {
  const domain = COOKIE_DOMAINS[platform]
  const list = await browser.cookies.getAll({ domain })
  return list.map(c => `${c.name}=${c.value}`).join('; ')
}

export async function syncCookieToBackend(platform: Platform): Promise<{ ok: boolean, count: number, error?: string }> {
  try {
    const cookieStr = await readBrowserCookies(platform)
    if (!cookieStr)
      return { ok: false, count: 0, error: '当前浏览器没有该域名的 cookie，先在浏览器内登录目标站点' }
    const count = cookieStr.split('; ').length
    await setDownloaderCookie(platform, cookieStr)
    return { ok: true, count }
  }
  catch (e) {
    return { ok: false, count: 0, error: (e as Error).message }
  }
}
