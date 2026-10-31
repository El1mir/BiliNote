# 020/03 · 生成设置抽成共享组件（批量页可用）

- 状态：resolved
- 依赖：无
- 关联 spec 章节：§4 决策 5–6、§5、§6.2

## 目标

批量生成面板能调全部生成参数，且与单集共用同一份实现。

## 改动点

1. 新建 `generationSettings.ts`：`GenerationSettings` 类型、`DEFAULT_GENERATION_SETTINGS`、`toPayloadSettings`（三态 OCR → `true/false/null`）。
2. 新建 `GenerationOptions.tsx`：受控面板（`value` / `onChange(patch)` / `idPrefix`），只导出组件。
3. `IntakeForm.tsx`：`useWatch` 组 `settings`，`applySettings` 用 `form.setValue` 写回；内联面板换成 `<GenerationOptions idPrefix="single" />`。
4. `BatchImportPanel.tsx`：`BATCH_DEFAULT_SETTINGS`（多勾 toc/link/summary）、`settings` state、「生成设置」折叠按钮、提交走 `toPayloadSettings`。

## 验收

- [x] `tsc -b` / `lint` 干净（组件文件不再触发 react-refresh 警告）；
- [x] `generationSettings.test.ts` 4 例全过；
- [x] 浏览器：批量 picking 阶段出现「生成设置」，id 前缀为 `batch-`，改动后状态保持。
