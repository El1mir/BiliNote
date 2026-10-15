/* -------------------- 常量 -------------------- */
import {
  BiliBiliLogo,
  DouyinLogo,
  KuaishouLogo,
  LocalLogo,
  YoutubeLogo,
} from '@/components/Icons/platform.tsx'

export const noteFormats = [
  { label: '目录', value: 'toc' },
  { label: '原片跳转', value: 'link' },
  { label: '原片截图', value: 'screenshot' },
  { label: 'AI总结', value: 'summary' },
] as const

/* spec 015：笔记预设是「场景 × 详略」两个正交维度，不再是九个互斥的风格。 */
export const noteScenes = [
  { label: '生活', value: 'life' },
  { label: '学术', value: 'academic' },
  { label: '专业', value: 'professional' },
] as const

export const noteDetails = [
  { label: '精简', value: 'brief' },
  { label: '详细', value: 'detailed' },
] as const

export const videoPlatforms = [
  { label: '哔哩哔哩', value: 'bilibili', logo: BiliBiliLogo },
  { label: 'YouTube', value: 'youtube', logo: YoutubeLogo },
  { label: '抖音', value: 'douyin', logo: DouyinLogo },
  { label: '快手', value: 'kuaishou', logo: KuaishouLogo },
  { label: '本地视频', value: 'local', logo: LocalLogo },
] as const
