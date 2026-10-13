# 工单 03 · 前端服务层与「重试失败」按钮

- **状态**：已完成
- **依赖**：工单 02

## 交付物

### `BillNote_frontend/src/services/note.ts`

```ts
export interface RetryFailedResult {
  scope: 'all' | 'group'
  group_id: string | null
  candidates: number
  requeued: string[]
  skipped: { task_id: string; reason: string }[]
  missing: string[]
}

export const retryFailedTasks = async (
  scope: 'all' | 'group',
  groupId?: string | null
): Promise<RetryFailedResult> =>
  await request.post('/retry_failed_tasks', {
    scope,
    group_id: scope === 'group' ? (groupId ?? null) : null,
  })
```

### `BillNote_frontend/src/pages/HomePage/components/History.tsx`

工具条（`<div className="ml-auto flex items-center gap-2">`，「下载选中」与「删除选中」之间）新增「重试失败」按钮。

## 验收清单

- [x] 按钮文案「重试失败」+ `RotateCcw` 图标，`variant="outline"`
- [x] **范围由后端算**：前端只把「当前可见范围」翻译成一次请求（`activeGroupId === null` → `scope: "all"`；否则 `scope: "group"` + `toApiGroupId(activeGroupId)`）
- [x] 前端**不自己筛「哪些失败了」** —— 两处各判一次必然会漂移，而漂移的表现是「点了重试但什么都没发生」
- [x] `RETRY_CONFIRM_THRESHOLD = 200`：可见范围任务数超过 200 先弹确认 Dialog（复用既有 `Dialog` 组件，不引新依赖）
- [x] 三类结果各自一条 toast：`requeued` 数量 / `skipped` 前几条原因 / `missing` 数量
- [x] 门禁类错误（`code=300102`/`300104`）**不重复提示** —— 请求拦截器已经 `toast.error(res.msg)`，前端只 `console.warn` 兜底
- [x] 重试中按钮 `disabled`，避免连点产生并发请求
- [x] 重试**不改 store**：任务从「失败」变回「排队中」由既有轮询接管，组件直接调 service

## 已知限制

- 前端**无法**知道「这个范围内有几条是失败任务」，所以 200 条阈值是按**范围内任务总数**判的。范围越大越容易触发确认 —— 宁可多问一次，也不要在几十条长任务上点错。

## 验证

- `cd BillNote_frontend; pnpm exec tsc -p tsconfig.app.json --noEmit` → 改动文件零命中（全仓 110 errors，HEAD 基线 192）
- `cd BillNote_frontend; pnpm build` → **✓ built in 49.03s**，`BUILD_EXIT=0`
- `lens_diagnostics mode=full paths=[...History.tsx, ...note.ts]` → `History.tsx` **0 blocking**（3 条 warning：`History` 圈复杂度 101、调用 77 个不同函数 —— 拆组件属独立重构，不在本规格范围）
