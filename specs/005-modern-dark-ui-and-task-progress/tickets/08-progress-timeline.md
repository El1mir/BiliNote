# 08 · 前端阶段时间线与进度组件（遗留缺陷）

- **依赖**：07
- **关联**：spec §7
- **状态**：待实现（遗留缺陷）

> ⚠️ 2026-10-05 重新定义。本工单原来的表述是「用与后端阶段协议一致的时间线替代当前单薄的固定
> StepBar」，其中「暗色体验统一」的部分随 m02324（浅色 DesignMD 是最终意图）失效。
> 下面保留的是**独立于主题、至今仍然成立**的缺陷 —— 每一条都有代码落点，都可在浅色界面下复现。

## 目标

让阶段时间线真正反映后端写入的状态。目前它接上了协议，却有三处把信息吃掉。

## 缺陷清单

### 1. `detail` 永远不显示（最严重）

后端写入的 `detail` **全是 dict**（`backend/app/services/note.py:1446` 的 `detail or {}`；
调用点见 `backend/app/routers/note.py` 的 562/582/834/917/1012/1182/1224/1487/1509/1881/2029/2061 行）。
而 `BillNote_frontend/src/utils/text.ts:12-20` 的 `asText` 对普通对象返回 `''` —— 于是所有阶段详情都被吞掉。
前端 `Task.detail` 还被声明成 `string | null`（`taskStore/index.ts:124-130`，具体在 `:129`），
类型与实现不符。

**修法要点**：`detail` 的类型要改成 `Record<string, unknown> | null`，并给时间线一个真正的渲染分支
（切片数 / 帧数 / 网格数就藏在里面）。

### 2. 成功时 12 个阶段全部显示为待处理

`backend/app/services/note.py:592` 的 `self._update_status(task_id, TaskStatus.SUCCESS)` 写入 `stage='success'`。
而 `BillNote_frontend/src/pages/HomePage/components/ProgressTimeline.tsx:49-62` 的 stages 列表里**没有** `success`
→ `index === -1` → 全部渲染成 pending。头部却同时显示「笔记已完成」+ 100%，自相矛盾。

### 3. 失败时不保留失败阶段

`backend/app/services/note.py:600` 的 `_update_status(task_id, TaskStatus.FAILED, message=str(exc))` **没有传 `stage`**
→ 写入 `stage='failed'`，把在途阶段覆盖掉。前端同样 `index === -1`，于是没有任何阶段标红，
只在 `ProgressTimeline.tsx:116` 追加一行通用失败行 —— 用户看不出是卡在哪一步失败的。

### 4. 缺少阶段上下文

切片数 / 帧数 / 网格数从未渲染（与缺陷 1 同源）。

### 5. 长阶段详情没有截断/展开

### 6. 窄屏不滚动

`BillNote_frontend/src/index.css:168` 是 `flex-wrap: wrap`（换行），不是 `overflow-x`。
阶段一多就折成多行，时间线的横向语义丢失。

## 验收

- 后端写了 `detail` 的阶段，界面上能看到里面的数字。
- 任务成功后，已走过的阶段显示为已完成。
- 任务失败后，失败发生在哪一步是可见的，且错误消息保留。
- 窄屏下时间线横向滚动而不是换行堆叠。
