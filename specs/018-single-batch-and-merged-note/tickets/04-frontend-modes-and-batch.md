# 04 前端模式切换与批量面板

- 依赖：02（接口字段）
- 关联 spec：§4 决策 1/2/7、§6
- 目标：输入区分单集/批量两个 Tab；单集探测多P 自动切批量；批量支持范围选择与合并开关。

## 改动点

- 新增 `BillNote_frontend/src/ember/features/workspace/IntakePanel.tsx`：持有 `mode` 状态，
  `Tabs`（单集生成 / 批量生成），单集触发 `onMultiPart(url)` 时切到批量并传 `initialUrl`。
- `IntakeForm.tsx`：URL 去抖 600ms 调 `expandUrl`；`videos[0].parts.length > 1` → 回调切换；单P 不打扰。
- `BatchImportPanel.tsx`：`initialUrl` 预填并自动解析；列表序号范围输入（`parseRangeSelection`）；
  「合并任务」`Switch`；合并时隐藏组名、显示合并标题；提交带 `merge` / `merge_title` / `merge_polish`。
- `WorkspacePage.tsx`：移除页头「批量导入」按钮，改渲染 `IntakePanel`。
- `src/utils/range.ts`：恢复 `parseRangeSelection`（`tests/001-bilibili-batch-import/range.test.ts` 依赖它）。
- i18n：`strings.ts` zh/en 新增 `intake.*` 与 `batch.merge*` / `batch.range*` 文案。

## 验收

- 粘贴多P 链接 600ms 后自动切到批量并展开分P。
- 合并开关打开时组名输入框消失、合并标题出现；关闭时相反。
- `3-6,9` 只勾中对应序号的行。
