# 008 前端 Workspace Data Module、i18n 与 Ember Studio 壳层

- 类型：架构决策
- 状态：designed
- 依赖：002-task-read-model-and-update-transport、007-source-intake-module、003-performance-baseline-and-budgets
- 阻塞：网页页面迁移、响应式壳层实现、中文/英文完整 i18n、前端性能门禁
- 设计范围：定义前端数据 facade、view model、能力加载和壳层边界；不实现页面视觉细节或后端接口。

## 1. 目标与删除测试

当前 taskStore、useTaskPolling、note services 和页面组件共同知道后端字段、轮询行为、状态转换和 Markdown/转录/聊天数据的加载时机。HomeLayout、RootLayout、SettingLayout 与 App.tsx 还同时承担路由、启动检查和 UI 组织，导致首屏加载范围不清晰。

目标是建立 Frontend Workspace Data Module：对页面提供稳定的 query、command 和 view model；它内部适配 Task Read Model、Source Intake、资源详情和 i18n，不把 Axios、SSE/轮询、旧字段、后端错误文本泄漏给组件。

删除测试：删除页面内直接调用 note service、直接读取 taskStore 原始字段、直接启动轮询和直接判断后端状态后，核心生成、进度、历史、阅读、导出、聊天和设置流程仍可由 facade 驱动；如果页面必须重新拼装 transport 或状态，说明 module 不够深。

## 2. Module 边界

### 2.1 Workspace Data Module 负责

- 暴露工作区查询：intake preview、active task groups、task detail、history page、note resource、transcript、mind map、chat session、settings summary。
- 暴露命令：resolveIntake、submitTasks、retryTask、cancelTask、deleteTask、open/export resource、sendChatMessage；command 返回稳定结果并不让组件接触 HTTP。
- 把 TaskViewEnvelope 合并为按 taskId/groupId 索引的不可变 view model，遵守 revision、跳号和终态规则。
- 管理单一任务更新 transport：网页/Tauri 默认 SSE，失败回退带 since 的轮询；扩展端继续使用兼容 adapter。
- 控制请求去重、取消、缓存和资源加载优先级；进度更新不得触发 Markdown、Markmap 或聊天重新请求。
- 将后端 error code/messageKey 映射为可供 i18n 渲染的领域错误，不把供应商原文当作 UI 文案。

### 2.2 Module 不负责

- React 组件树、CSS、Ember Studio 色彩/字体实现和具体响应式布局。
- 业务流水线、任务副作用、下载、转录、OCR、LLM 或数据库。
- Markdown 内容翻译；生成内容保持原文。
- 浏览器扩展 UI 和 Tauri 打包；只提供共享 contract 适配。

## 3. 前端 interface

### 3.1 Facade 分区

- useWorkspaceQuery：返回 activeGroups、selectedTask、history、loading、stale、lastUpdated 和 transport health。
- useIntake：管理 raw inputs、resolve preview、ready items、validation errors 和 submit eligibility；规则来自 Source Intake response。
- useTaskActions：retry/cancel/delete/export 等 command，动作可用性来自 TaskView.actions，不由按钮猜测。
- useResourceQuery：按需加载 Markdown、transcript、mind map、screenshots 和 chat；资源 query key 包含 taskId、resource kind 与 revision。
- useSettingsWorkspace：按设置域懒加载 provider、model、transcriber、downloader、proxy、monitoring、prompt 数据。

组件拿到的 view model 必须是 UI 语义模型，例如 statusLabelKey、phaseLabelKey、progress、actions 和 resourceState；组件不得读取 response.data、Axios error、后端字段别名或轮询计时器。

### 3.2 Store 结构

- taskReadModelStore：只保存任务组/任务索引、revision、游标、transport 状态和窗口选择。
- workspaceUiStore：只保存 route、selectedTaskId、drawer/panel 状态、语言和用户偏好。
- intakeStore：只保存当前输入草稿和 resolve 结果，提交成功后清理草稿但保留最近结果摘要。
- resource cache：由 query layer 按 taskId/resource/revision 管理，不能把 Markdown、聊天消息塞进任务状态 store。

现有 taskStore 不直接整体搬迁：先由 adapter 将旧状态映射到新 read model，再按消费方迁移并删除旧字段。useTaskPolling 退化为 transport adapter 的内部实现，页面不再调用它。

## 4. 加载与路由边界

### 4.1 首屏工作区

首屏只加载 shell、工作台 query、Source Intake 输入、任务摘要、基础错误/空状态和必要 shadcn primitives。Markdown viewer、Markmap、转录、聊天、导出、设置和系统诊断均通过 route/interaction triggered lazy boundary 加载。

首屏 query 只请求活动任务窗口；历史、归档和资源详情按用户进入或点击加载。收到 task.upsert 时只更新受影响的任务和组，不能令整个 HomePage 重新挂载。

### 4.2 桌面/平板/手机

- 桌面：固定侧边导航 + 工作区主列 + 可选详情列；任务列表和阅读内容可并列。
- 平板：可折叠双栏；详情、聊天和设置使用可调整面板，保持输入与当前任务同屏。
- 手机：单列工作流；导航与次要详情进入抽屉/底部 sheet；输入、提交、进度和重试保持拇指可达。
- 所有尺寸共享同一 facade 和状态模型；响应式变化只改变布局，不重复请求或重置选中任务。

### 4.3 Ember Studio 壳层

Shell 只拥有设计 token、字体加载、导航、surface、focus ring、toast、drawer、loading skeleton 和全局错误边界。采用 ember-studio-DESIGN.md 已定的 terracotta #C2410C、amber #F59E0B、warm neutral、Playfair Display + Source Sans 3；组件通过语义 token 使用颜色，不把色值散落到业务页面。

装饰保持克制：纹理、阴影和圆角服务层级与反馈，不阻塞首屏，也不把关键状态只编码为颜色。减少动画默认值，支持 prefers-reduced-motion；任务进度变化使用稳定的数字/文本和可访问 aria 状态。

## 5. i18n contract

- locale：zh-CN、en-US，默认跟随浏览器但允许用户覆盖并持久化。
- namespaces：shell、intake、tasks、history、reader、chat、settings、errors、a11y、common。
- 页面和组件只使用 t(namespace.key, params)；新增用户可见字符串必须进入语言包。
- status、phase、action、error messageKey 和 accessibility label 全部有中英文键；后端 messageKey 不直接显示。
- 语言切换不清空任务/资源状态，不重新建立任务 transport；只刷新文案和格式化器。
- 日期、时长、数量、文件大小使用 locale-aware formatter；生成 Markdown、转录和聊天正文不翻译。
- 英文长文案、错误 detail、批量数量和设置项必须允许换行，不能依赖固定宽度或 hover 才可理解。

## 6. 性能与数据一致性规则

- 所有 facade query 标明 priority：critical（shell/intake/task summary）、deferred（history/resource）、on-demand（Markmap/chat/settings）。
- 资源加载支持 AbortSignal；切换任务时取消未完成的非关键请求，避免旧任务结果覆盖新选择。
- 活跃任务 view 的陈旧时间遵守 ticket 003 锁定的 freshness budget；终态资源可缓存但必须按 revision 校验。
- taskReadModelStore 以 taskId/groupId 为 key；revision 旧于当前值的更新丢弃；跳号交给 transport 触发快照恢复。
- selector 按受影响的 task/group/resource 订阅，进度更新不能导致整页、Markdown 或聊天组件重渲染。
- route chunks、字体和 Markmap/聊天依赖必须可测量；不得用 eager import 让首屏加载所有设置和重型渲染库。

## 7. 实现顺序

1. 以现有 taskStore、useTaskPolling、services、App.tsx 和 layouts 建立 facade fixture 与消费清单。
2. 定义共享 TypeScript schema、error/messageKey 类型、query keys 和 revision reducer；接入 ticket 002 的 read model adapter。
3. 建立 Source Intake facade，迁移首页和 BatchImportDialog，删除页面内 URL/P 号/平台逻辑。
4. 接入单一 SSE/轮询 transport，迁移任务列表、进度、历史和重试；验证 selector 局部更新。
5. 建立 shell token、路由边界和懒加载，迁移 Markdown、Markmap、转录、聊天、导出与设置。
6. 完成 zh-CN/en-US 语言包、可访问性键、三 viewport 和 ticket 003 性能基线；通过 ticket 006 后删除旧 store/service adapter。

## 8. 测试与验收

### Data Module

- reducer：快照、upsert、remove、旧 revision、跳号和终态保护。
- transport：SSE 建连/断线/回退/恢复、轮询 since、页面恢复可见和取消请求。
- facade：resolve/submit/action/resource query 的 schema 映射、去重和错误分类。
- selector：单任务更新不重渲染无关任务、Markdown、Markmap 或聊天。

### UI 与 i18n

- 工作区首屏不加载 Markmap、聊天、设置和非关键字体/资源。
- 语言切换保持当前任务、抽屉、滚动和未提交输入；所有 namespace 键完整。
- 桌面、平板、手机完成输入、提交、进度、阅读、重试和错误恢复；键盘和屏幕阅读器可完成核心流程。
- Ember token、字体、focus ring、reduced motion 和非颜色状态表达符合设计规格。

### 验收

- 页面不直接导入旧 task service/polling helper，不读取旧 response 字段。
- 任务进度更新只影响相关 task/group；资源内容不会因进度刷新重新获取。
- 首屏、路由切换、交互响应和任务 freshness 都有 ticket 003 的可重复证据。
- zh-CN/en-US 文案、错误、阶段、动作和 aria label 完整；长英文布局稳定。
- 三个架构模块均有本地 ticket、明确边界、删除测试、实现顺序和验收条件，之后才可进入业务代码实现。

## 9. 未决问题

- ticket 003 锁定首屏 chunk、字体、请求数、INP/LCP/CLS 与任务 freshness 数值。
- ticket 006 决定 React Router/query library 是否引入；本 ticket 只要求 facade 语义，不预设具体库。
- 若现有 i18n locale key 与 namespace 迁移成本过高，保留兼容 key 的期限由 ticket 006 设定。
