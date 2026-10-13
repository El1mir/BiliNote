# 11 · 设置页：Prompt 页面缺失（遗留缺陷）

- **依赖**：无
- **关联**：spec §7
- **状态**：待实现（遗留缺陷）

> ⚠️ 2026-10-05 重新定义。原表述是「统一笔记阅读、转写、对话、Markmap 和设置页的暗色体验」——
> 「暗色体验」随 m02324（浅色 DesignMD 是最终意图）失效。核查后，本工单**只剩一个真实缺陷**。

## 缺陷清单

### Prompt 页面是一个未挂路由的占位 stub

- `BillNote_frontend/src/pages/SettingPage/Prompt.tsx:1-4` 的全部内容就是
  `<div className={'flex h-full w-full bg-white'}>prompt</div>`。
- `BillNote_frontend/src/App.tsx:92-107` 的路由表里**没有** `prompt` 这一项。
- `BillNote_frontend/src/pages/SettingPage/Menu.tsx:15-22` 的设置页侧边菜单里也**没有**这一项。

即：Prompt 编辑能力在导航上完全不可达，页面文件却还在。

### 随主题决定失效、不再算缺陷的部分

`MarkdownViewer.tsx:19` 引 `github-markdown-css/github-markdown-light.css`、
`MarkdownViewer.tsx:420/431` 的 `bg-white`、`ChatPanel.tsx:171` 的 `bg-blue-500`、
`ChatPanel.tsx:181` 的 `bg-neutral-500`、`transcriptViewer.tsx:52` 的 `bg-white` 与 `:72-92` 的 slate 系、
`MarkdownHeader.tsx:72` 的 `bg-white/95`、`SettingLayout.tsx:25` 的 `border-neutral-200 bg-white` 与
`:32` 的 `text-gray-800` —— 这些都是**浅色**，正是 m02324 选定的方向。

## 验收

- Prompt 页面在设置页导航里可达，且能读取、编辑、保存 Prompt。
- 设置数据可读取、编辑、保存和删除（沿用原验收）。
