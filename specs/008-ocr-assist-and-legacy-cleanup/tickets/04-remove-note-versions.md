# 04 · 删除「笔记版本管理」，markdown 收敛为 string

- **状态**：已实现
- **依赖**：无
- **上游 spec**：`specs/008-ocr-assist-and-legacy-cleanup/spec.md` §8

## 目标

移除前端的笔记版本机制，把 `markdown` 从 `string | Markdown[]` 收敛为 `string`，同时保证**旧的数组形态数据仍能渲染出最新一版笔记**而不是空白。

## 为什么是「收敛」不是「删除」

`string | Markdown[]` 这个联合类型不仅服务于版本功能，也是**当前正常单版本笔记的存储形态**。所以不能把相关代码整段删掉，必须把它压缩成纯粹的单字符串路径。具体来说：

- `Markdown` 接口、`Task.markdown` 的联合类型 → 收敛为 `string`
- `updateTaskContent` 的版本包装逻辑 → 保留幂等保护，去掉包装，直接赋值
- `MarkdownViewer` 的版本 effect → 压回「直接取 `currentTask.markdown`」

## 现状锚点

- `BillNote_frontend/src/store/taskStore/index.ts:70-76` `interface Markdown { ver_id, content, style, model_name, created_at }`
- `taskStore/index.ts:80` `markdown: string|Markdown [] //为了兼容之前的笔记`
- `taskStore/index.ts:157-210` `updateTaskContent`：`:173-181` 构造 `ver_id: \`${task.id}-${uuidv4()}\``，`:183-199` `[newVersion, ...prev]` **新版本前插**，并把旧的字符串形态包装成第二个合成版本
- `taskStore/index.ts:4` `uuid` 依赖（`uuidv4` 是版本功能的唯一使用者）
- `BillNote_frontend/src/pages/HomePage/components/MarkdownHeader.tsx:11-16,20,22-24,94-116` 版本下拉，标签 `版本（${shortId}）`；`:71-73` `reversedMarkdown` 是**死变量**
- `BillNote_frontend/src/pages/HomePage/components/MarkdownViewer.tsx:291,302,311-341,425,445` `currentVerId` / `isMultiVersion` / 两个版本 effect
- `BillNote_frontend/src/hooks/useTaskPolling.ts:23-24` `hasMarkdownContent` 的数组分支；`:71-79` 每次轮询 SUCCESS 都会调 `updateTaskContent`，**这正是版本不断累积的来源**
- `backend/app/services/chat_tools.py:176-180`：`if isinstance(md, list): md = md[-1].get("content","")` —— 注释写「多版本，取最新」，但因为前端是前插，`md[-1]` 实际取到的是**最旧**版本，是既有 bug

## ⚠️ 最大的坑：旧 IndexedDB 数据

`taskStore` 用 zustand `persist` + `idb-keyval` 持久化，storage name 为 `'task-storage'`（`taskStore/index.ts:284-298`）。用户浏览器里**可能已经有** `markdown` 为数组的历史数据。

如果读取时直接把它当字符串用，这些历史笔记会**渲染成空白**。

处理方式（spec 决策 8 已定）：**容错读取**

```ts
const latest = Array.isArray(md) ? md[0]?.content ?? '' : md ?? ''
```

**注意顺序**：数组是**新版本在前**（`[newVersion, ...prev]`），所以取 `md[0]` 才是最新。**不要**写成 `md[md.length - 1]` —— 那正是 `chat_tools.py` 踩的坑。

容错读取要加在**读取路径**上（渲染处），而不是假设数据已经迁移过。

## 任务

### 必须改

1. `taskStore/index.ts`：删除 `Markdown` 接口；`Task.markdown: string`；`updateTaskContent` 去掉版本包装（**保留 `:164-170` 的幂等保护**）；删除 `retryTask`（属于 ticket 03）。
2. `MarkdownHeader.tsx`：删除版本下拉、`VersionNote` 接口、`isMultiVersion` / `currentVerId` / `setCurrentVerId` props，以及死变量 `reversedMarkdown`。
3. `MarkdownViewer.tsx`：删除 `currentVerId` / `isMultiVersion` 状态与两个版本 effect，改为直接使用 `currentTask.markdown`（带上面的容错读取）；`:425` 的 `if (status === 'failed' && !isMultiVersion)` 改为 `if (status === 'failed')`（注意：**重试按钮本身按 ticket 03 删除**，此处只保留失败态展示）。
4. `useTaskPolling.ts`：`hasMarkdownContent` 去掉数组分支，改为 `Boolean(task?.markdown)`。
5. `chat_tools.py:176-180`：简化数组分支（后端结构上 `NoteResult.markdown: str`，该分支本就是防御性的死代码）。

### 顺手清理（删除后变成死代码）

- `MarkdownViewer.tsx:41-44` 的 `content` prop —— 声明了但从未被消费（`Home.tsx:40` 只传 `status`）
- `Home.tsx:16` 未使用的 `content` 常量

### 依赖检查

`uuid` 包若仅被版本代码使用，可从 `package.json` 移除；**移除前必须确认全仓库无其他使用者**。

### 文档同步

- `README.md:82` `- 支持多版本记录保留` —— 删除或改写
- `specs/005-modern-dark-ui-and-task-progress/tickets/11-note-and-settings-redesign.md:14` `保留 LaTeX、代码块、截图、视频链接和 Markdown 版本能力。` —— 去掉「Markdown 版本能力」

## 验收

- 全仓库 `grep -rn "ver_id\|isMultiVersion\|VersionNote"` 无结果。
- `Task.markdown` 类型为 `string`。
- **手工验证旧数据**：在浏览器 IndexedDB 里塞一条 `markdown` 为数组形态的任务，刷新后该笔记正常渲染出**最新一版**内容，不是空白。
- 轮询不再产生任何版本累积（`updateTaskContent` 调用后 `markdown` 仍是字符串）。
- `README.md` 与 spec 005 ticket 11 已同步。
- 前端测试、生产构建通过。
