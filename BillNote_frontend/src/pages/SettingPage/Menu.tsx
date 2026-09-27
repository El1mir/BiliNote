import {
  Activity,
  BotMessageSquare,
  Captions,
  Database,
  HardDriveDownload,
  Info,
} from 'lucide-react'
import MenuBar, { IMenuProps } from '@/pages/SettingPage/components/menuBar.tsx'

const Menu = () => {
  const menuList: IMenuProps[] = [
    { id: 'model', name: 'AI 模型设置', icon: <BotMessageSquare />, path: '/settings/model' },
    { id: 'transcriber', name: '音频转写配置', icon: <Captions />, path: '/settings/transcriber' },
    { id: 'media', name: '媒体资源管理', icon: <Database />, path: '/settings/media' },
    { id: 'download', name: '下载配置', icon: <HardDriveDownload />, path: '/settings/download' },
    { id: 'monitor', name: '部署监控', icon: <Activity />, path: '/settings/monitor' },
    { id: 'about', name: '关于', icon: <Info />, path: '/settings/about' },
  ]

  return (
    <div className="flex h-full flex-col">
      <div className="flex w-full flex-col gap-2">
        <div className="text-2xl font-medium">设置</div>
        <div className="text-sm font-light text-gray-800">全局配置与模型设置</div>
      </div>
      <div className="mt-6 flex-1">
        {menuList.map(item => <MenuBar key={item.id} menuItem={item} />)}
      </div>
    </div>
  )
}

export default Menu