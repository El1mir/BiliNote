# T-069 W1 工作区重绘 · 视觉与布局证据

隔离环境（不碰 master 数据库）：后端 `BACKEND_PORT=8496` +
`DATABASE_URL=sqlite:///<worktree>/backend/.t069-tmp/t069.db` +
`NOTE_OUTPUT_DIR=<同目录>/note_results`；前端 `pnpm dev` 3024，
worktree 根 `.env.local` 写 `VITE_API_BASE_URL=http://127.0.0.1:8496`。

种子：两个分组（学习笔记 / 素材归档）+ 五条任务（两条 SUCCESS 带
`note_results/<id>.json`，一条 TRANSCRIBING 42%，一条 PLANNING_FRAMES 12/24，
一条 FAILED 带错误文案）。截图前未选中任务，除 reader/failed 两张外。

| 截图 | 视口 | overflowX | dark |
| --- | --- | --- | --- |
| workspace-1440-light | 1440x900 | 0 | false |
| workspace-1024-light | 1024x900 | 0 | false |
| workspace-768-light | 768x900 | 0 | false |
| workspace-375-light | 375x812 | 0 | false |
| workspace-375-light-touch | 375x812（hasTouch） | 0 | false |
| workspace-1024-dark | 1024x900 | 0 | true |
| workspace-375-dark | 375x812 | 0 | true |
| workspace-reader-1024-light | 点开 SUCCESS 任务 | 0 | false |
| workspace-failed-1024-light | 失败筛选 + 选中失败任务 | 0 | false |
| workspace-drag-1024-light | dragstart→dragover 后 | 0 | false |
| workspace-delete-confirm-1024-light | 批量删除确认框 | 0 | false |
| workspace-empty-search-1024-light | 搜索无结果 | 0 | false |
| workspace-loading-1024-light | 列表请求延迟 6s | 0 | false |
| workspace-backend-down-1024-light | 后端未启动 | 0 | false |

四态证据：加载（.ember-pulse 骨架 3 个）、空（无搜索无任务）、无搜索结果
（clearFilters 按钮）三张是实测截图。列表请求失败态（AlertTriangle + 重试）
由 `TaskList` 的 `error` 分支承担，断言在
`tests/021-workbench-redesign/workspace.test.tsx`；浏览器里真正让列表接口
失败时会先被 AppShell 的启动页拦住（"正在启动后端服务"），所以补了一张
`workspace-backend-down-1024-light` 记录后端整体不可达时的实际界面。

删除确认：选择模式 → 勾选一条 → 点“已选 1 条” → 标题“删除选中的笔记 /
将删除 1 条任务记录与已生成的笔记，无法撤销”。截图时取消，未真的删。

## 已知限制（如实记录）

1. 种子任务的状态文件由列表接口回填，`stage` 只在 SSE/单任务状态里给，
   所以截图里在途任务的阶段行显示“等待处理”（回落文案），不是产品缺陷。
2. 选择工具栏此前在 340px 侧栏里不换行，1024 视口下把“已选 N 条”挤出屏幕
   （overflowX=181）。已在 `TaskList.tsx` 给标题行与工具栏加 `flex-wrap`
   + `justify-end`，复测 overflowX=0，确认框可正常打开。
3. 仍有 22–32 个 <44px 的可点目标，样本全部来自既有 shell / ui 原语
   （侧栏导航 47x36、主题与语言按钮 42x32、单集/批量 tab 80x38、
   “下载所选分组”32x28、“新建”32x32、“重试失败任务”124x32）。
   这些尺寸属于 ui 原语与外壳，不在本卡改动范围内。
