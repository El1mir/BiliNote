# 002 任务读取模型与更新传输

- 类型：架构决策
- 状态：designed
- 依赖：001-capability-inventory-and-information-architecture（能力分区已确定）
- 阻塞：前端工作区数据层、后端 route migration、性能预算落地、扩展端任务状态适配
- 关联规格：specs/017-web-rebuild-and-architecture/spec.md 第 5、6、7 节
- 设计范围：只定义任务读取模型与状态更新传输；任务写入、生成流水线重构和数据库迁移留给后续 ticket。

## 1. 目标与删除测试

当前任务状态由后端 router、serial executor、note service、前端 service、轮询 hook 和 Zustand store 共同拼装。页面知道请求形状、轮询周期、状态归一化和分组关系，导致同一任务在首页、历史、扩展端出现不同的进行中、失败、完成解释。

本 ticket 的目标是建立一个深 module：调用方只关心读取任务视图和订阅更新，不关心数据库字段、Axios、轮询周期或 executor 内部状态。

删除测试：如果删掉当前前端的状态拼装、状态归一化和散落的轮询请求，复杂度必须集中到一个可测试的 Task Read Model，而不是转移到新的页面组件；如果无法做到，先不迁移页面。

## 2. 领域边界

### 2.1 读取模型负责

- 任务组摘要：groupId、groupName、组级状态、任务数、完成数、失败数、最近更新时间。
- 任务摘要：taskId、groupId、来源标题/URL、platform、阶段、状态、进度、可读错误、创建/开始/结束时间。
- 阶段进度：稳定的 phase 枚举和 progress 数值/未知值，不把后端日志文本当作协议。
- 可用动作：canRetry、canCancel、canOpenNote、canOpenTranscript、canChat、canExport，由后端能力判断生成。
- 查询窗口：当前任务、最近任务、按组历史和单任务详情；读取模型不负责笔记 Markdown、思维导图数据或聊天消息正文。
- 版本与一致性：快照版本、单任务 revision、组级 revision、服务器时间和传输来源。

### 2.2 读取模型不负责

- 任务创建、取消、重试等 command 的业务副作用。
- 下载、转录、OCR、LLM、导出和聊天内部流水线。
- 数据库 ORM 结构、临时文件路径和供应商错误原文。
- 页面布局、中文/英文文案和移动端交互。
- 事件永久存储；只提供当前可重建的读取视图和短期增量游标。

## 3. 规范化状态模型

状态集合固定为：

- queued：已接收，尚未开始执行。
- running：正在执行，必须带 phase；progress 可以是 null。
- succeeded：任务完成且笔记资源可读取。
- failed：任务终止且存在稳定 error.code；可通过 actions.retry 判断是否允许重试。
- cancelled：用户或系统取消，不与失败混淆。

终态为 succeeded、failed、cancelled。状态转换必须单调：queued → running → terminal；允许 queued → cancelled，不允许终态回到非终态。重复消息必须幂等，旧 revision 必须丢弃。

phase 使用协议枚举：accepted、resolving、downloading、transcribing、sampling、ocr、generating、indexing、exporting、finalizing。新增阶段只能追加枚举并保留旧值兼容，页面不得依赖任意自然语言阶段。

## 4. 版本化快照 contract

读取接口统一返回 envelope，字段名先固定为下列形状；实现时可在同一 ticket 中补充 OpenAPI、Pydantic、TypeScript 类型，但不得让页面直接消费旧响应。

TaskViewEnvelope：

- schemaVersion：协议主版本，首版为 1；破坏性变更升主版本。
- snapshotRevision：本次快照的全局单调版本；只用于重连与比较。
- serverTime：ISO 8601 UTC 时间。
- source：snapshot、sse、polling，仅用于诊断，不参与业务判断。
- groups：TaskGroupView 数组，服务端已按最近更新时间排序。
- tasks：TaskView 数组，用于无分组任务和快速索引；组内任务仍以 groupId 关联。

TaskGroupView：

- groupId：string 或 null；groupName：string 或 null。
- status：queued、running、succeeded、failed、cancelled。
- taskCount、completedCount、failedCount、updatedAt。
- revision：该组最近一次变化的版本。

TaskView：

- taskId、groupId、platform、sourceUrl、title。
- status、phase、progress，其中 progress 为 number 或 null。
- createdAt、startedAt、finishedAt、updatedAt。
- error：code、messageKey、retryable，或 null。
- actions：retry、cancel、openNote、openTranscript、chat、export，均为 boolean。
- revision：单任务单调版本；服务端更新任务时递增。

前端以 taskId 为主键、以 revision 做 last-write-wins；不得用数组位置合并。服务端字段不得直接暴露供应商异常、文件路径或内部堆栈。

## 5. 更新传输决策

### 5.1 首选：SSE 增量更新

新增只读接口：GET /api/v1/task-groups/stream。客户端通过 groupId、taskId、since 和 schemaVersion 过滤；服务端发送 text/event-stream，每条事件带 id=snapshotRevision。

事件类型固定为：

- task.snapshot：连接建立或无法从游标恢复时发送完整 TaskViewEnvelope。
- task.upsert：一个或多个任务或组的最新视图。
- task.remove：任务被永久清理时的 taskId、groupId。
- task.heartbeat：只证明连接存活，不改变读取模型。
- task.error：传输错误，不等同于业务任务 failed。

SSE 只传读取视图，不承载 command；创建、重试、取消仍走 command endpoint，待迁移 ticket 统一成版本化 command contract。

### 5.2 降级：带游标的短轮询

当浏览器、Tauri、扩展端或代理不支持 SSE 时使用 GET /api/v1/task-groups?since=revision。默认间隔 3 秒，页面进入前台后立即刷新；连续两次无变化可退避到 6 秒，发现变化后恢复 3 秒。轮询返回与 SSE 相同的 envelope/update 语义，避免两套业务合并逻辑。

### 5.3 重连与顺序

- 客户端保存最后确认的 snapshotRevision，连接断开后用 Last-Event-ID 和 since 重连。
- 服务器若无法覆盖游标，必须发送 task.snapshot，客户端先清空受影响窗口再应用快照。
- 事件只允许按 snapshotRevision 递增应用；旧事件丢弃，跳号触发重新快照，不尝试猜测中间状态。
- 客户端应用更新成功后才推进本地游标；解析失败保留旧视图并记录可诊断错误。
- SSE 重连使用指数退避 1、2、4、8、16 秒，上限 30 秒；页面恢复可见时立即尝试一次。

## 6. 错误、刷新与兼容

### 6.1 错误边界

读取失败分为 transport_unavailable、schema_unsupported、cursor_expired、unauthorized、server_unavailable 五类；这些错误只影响读取连接，不把任务标为 failed。业务失败必须来自 TaskView.error。

messageKey 由前端 i18n 映射为中文/英文；后端只提供稳定 key 和安全参数，不直接提供需要翻译的完整 UI 文案。

### 6.2 首屏与刷新

- 首页首读只请求当前任务窗口，历史列表按需加载。
- 收到 task.upsert 后只更新受影响 task/group，笔记 Markdown、思维导图和聊天不因进度变化重新请求。
- 浏览器刷新或新标签页从快照开始，不依赖内存中的历史事件。
- 终态任务允许短期缓存；正在运行的任务不得使用超过 3 秒的陈旧数据作为当前状态。

### 6.3 扩展兼容

扩展端继续消费快照/轮询 contract，不强制要求 SSE；新增字段只向后兼容追加。网页、Tauri 和扩展端共用 schema 类型与状态枚举，但各自选择 transport。旧 endpoint 先作为 adapter 适配到新读取模型，迁移完成前不让页面同时拼装新旧响应。

## 7. 性能与可观测性预算

具体数值在 ticket 003 基线后锁定；本 ticket 先锁比较维度：

- 首屏任务读取请求数、payload bytes、解析耗时。
- 活跃任务更新到界面的 freshness：SSE 事件、轮询响应到 UI 提交的时间。
- 同一任务窗口的重复请求数和无变化响应占比。
- 重连次数、游标过期次数、快照恢复次数、更新解析失败次数。
- 前端渲染受影响的 task/group 数量，不允许进度更新导致整页重渲染。

## 8. 实现顺序

1. 以现有 taskStore、useTaskPolling、noteGroup 和后端任务状态响应建立 fixture，冻结旧行为对照样本。
2. 添加后端 TaskViewEnvelope 读取模型与序列化器，先通过旧 endpoint adapter 输出新 contract。
3. 添加带 since 的轮询读取接口和契约测试；网页先切到新快照，扩展端保持 adapter。
4. 添加 SSE stream 与游标恢复测试；网页默认 SSE，失败自动切轮询。
5. 删除前端旧的字段拼装、状态归一化和重复轮询逻辑，保留一个 transport client。
6. 完成桌面/平板/手机、中文/英文、刷新/断线/终态和扩展回归后，才关闭旧 endpoint adapter。

## 9. 测试与验收

### 后端

- 状态转换矩阵：合法转换、终态保护、重复 revision、乱序事件。
- 快照 schema：必填字段、未知可选字段、隐藏内部错误/路径/堆栈。
- SSE：首个快照、upsert/remove/heartbeat、Last-Event-ID、游标过期重快照、断线重连。
- 轮询：since 无变化、变化、过期和降级响应与 SSE 语义一致。
- 性能：固定任务窗口下 payload、序列化耗时和查询次数可测。

### 前端

- reducer/store：按 taskId/groupId 合并，旧 revision 和跳号行为正确。
- transport：SSE 成功、解析失败、断线退避、轮询 fallback、页面恢复可见。
- UI：同一状态在首页、历史、移动抽屉显示一致；英文长文案不溢出；终态动作由 actions 控制。
- 回归：网页、Tauri、浏览器扩展都能读取同一 schema；生成内容、笔记正文、聊天消息不被任务刷新破坏。

### 验收

- 页面不再读取或拼装旧 task 字段；只依赖 TaskViewEnvelope。
- 同一任务在不同客户端的状态、阶段、进度和 error code 一致。
- 断线后能恢复到最新快照，不显示倒退状态。
- 无变化轮询不会触发笔记、思维导图或聊天重新加载。
- 旧 endpoint adapter 可删除前，所有 contract、响应式和性能门禁通过。

## 10. 未决问题

- ticket 003 基线完成后，确定首屏任务窗口大小、SSE 心跳间隔、payload 上限和 freshness 目标。
- ticket 006 决定 command endpoint 是否与读取模型同一版本前缀，及旧 endpoint 的下线日期。
- 若后端部署环境不允许长连接，SSE 仅作为网页/Tauri 优化路径，扩展端继续使用游标轮询。
