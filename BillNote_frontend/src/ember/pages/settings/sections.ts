import {
  Activity,
  AudioLines,
  Cpu,
  Download as DownloadIcon,
  Globe,
  HardDrive,
  Info,
  MessageSquareText,
  ScanText,
  SlidersHorizontal,
  type LucideIcon,
} from 'lucide-react'
import type { MessageKey } from '@/ember/i18n/strings'

/**
 * 设置页分区的唯一清单（W3）。
 *
 * 侧栏、窄屏下拉与路由都从这里取，避免"导航里有、路由里没有"这类漂移；
 * 图标存组件而不是 JSX，.ts 里也能定义，渲染处统一 size-4。
 */
export type SectionId =
  | 'general'
  | 'model'
  | 'transcriber'
  | 'ocr'
  | 'prompt'
  | 'media'
  | 'download'
  | 'proxy'
  | 'monitor'
  | 'about'

export type SectionDef = {
  id: SectionId
  labelKey: MessageKey
  icon: LucideIcon
}

export const SECTIONS: SectionDef[] = [
  { id: 'general', labelKey: 'settings.general', icon: SlidersHorizontal },
  { id: 'model', labelKey: 'settings.model', icon: Cpu },
  { id: 'transcriber', labelKey: 'settings.transcriber', icon: AudioLines },
  { id: 'ocr', labelKey: 'settings.ocr', icon: ScanText },
  { id: 'prompt', labelKey: 'settings.prompt', icon: MessageSquareText },
  { id: 'media', labelKey: 'settings.media', icon: HardDrive },
  { id: 'download', labelKey: 'settings.download', icon: DownloadIcon },
  { id: 'proxy', labelKey: 'settings.proxy', icon: Globe },
  { id: 'monitor', labelKey: 'settings.monitor', icon: Activity },
  { id: 'about', labelKey: 'settings.about', icon: Info },
]

const IDS = new Set<string>(SECTIONS.map(section => section.id))

/** 从 /settings/<id> 取出分区；未知路径（含 /settings）回落到 general，和路由的兜底一致。 */
export function sectionIdFromPath(pathname: string): SectionId {
  const rest = pathname.replace(/^\/+/, '').split('/')[1] ?? ''
  return IDS.has(rest) ? (rest as SectionId) : 'general'
}

/** 窄屏下拉的选项：有未保存草稿的分区在文案后缀一个点，和宽屏导航的圆点角标同义。 */
export function sectionOptions(
  label: (key: MessageKey) => string,
  dirty: ReadonlySet<string>,
): { value: SectionId; label: string }[] {
  return SECTIONS.map(section => ({
    value: section.id,
    label: dirty.has(section.id) ? `${label(section.labelKey)} •` : label(section.labelKey),
  }))
}
