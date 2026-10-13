# 10 · 首页任务队列信息密度（遗留缺陷）

- **依赖**：08
- **关联**：spec §7
- **状态**：待实现（遗留缺陷）

> ⚠️ 2026-10-05 重新定义。原表述是「重构首页为暗色工作台」—— 其中「暗色工作台」随 m02324
> （浅色 DesignMD 是最终意图）失效。剩下的是：**任务卡片几乎不显示任何进度信息**。

## 目标

让任务列表本身承载进度信息，而不是必须点进详情才知道任务在干什么。

## 缺陷清单

### 1. 任务卡片只有 legacy 徽标

`BillNote_frontend/src/pages/HomePage/components/NoteHistory.tsx:206-216` 的卡片只有三个旧徽标：
`bg-primary`（`:207` 已完成）/ `bg-green-500`（`:210` 等待中）/ `bg-red-500`（`:215` 失败）。
**无阶段、无进度、无耗时、无错误消息。**

佐证：在 `BillNote_frontend/src/pages` 全库 grep `stage` / `progress` / `message` / `detail` / `updatedAt`，
**唯一消费者是 `ProgressTimeline.tsx`** —— 也就是说 spec 005 后端辛苦写的阶段协议，
在任务列表这个用户最常看的地方完全没有露出来。

### 2. 没有任务重试

失败任务只能重新走一遍生成表单。

### 3. 批量导入不按任务展示阶段

`BillNote_frontend/src/pages/HomePage/components/BatchImportDialog.tsx:246-247` 只有 queued/skipped 两个计数，
看不到每个视频各自进行到哪一步。

### 4. 首页顶部仍在读 legacy 字段

`BillNote_frontend/src/pages/HomePage/Home.tsx:35-46` 仍只读 `currentTask.status`，不读阶段。

## 验收

- 任务卡片上能直接看到当前阶段与进度。
- 失败任务能一键重试。
- 批量任务能看到每个视频各自的阶段，而不是一个混合百分比。
- 桌面和窄屏下任务区可独立滚动、不重叠。
