# 020/01 · 数学分隔符规范化（前端读路径）

- 状态：resolved
- 依赖：无
- 关联 spec 章节：§4 决策 1–3、§6.1、§7

## 目标

用户那篇笔记（169 个公式、`$$…` 与内容同行、`\begin{cases}` 跨多行）刷新后能正确渲染：行内公式不再原样显示、没有 KaTeX 红字、`$$` 不残留在正文。

## 改动点

1. `BillNote_frontend/src/utils/markdown.ts` 重写：
   - 按代码围栏（``` 与 `~~~`）分段，围栏内不动；
   - `isolateDollarFences` 把「`$$` 与内容同行、闭符号在末行」的块拆成 `$$` / 正文 / `$$` 三行，句子中间的 `$$…$$` 同样拆块；
   - `convertProse` 把跨行 `\[…\]` 换成前后带空行的 `$$` 块，把 `\(…\)` 换成 `$…$` 并把 body 内换行折成空格。
2. `MarkdownNote.tsx`：`rehype-katex` 传 `{ throwOnError: false, strict: false }`。

## 验收

- [x] `tests/020-note-rendering-and-batch-options/markdown.test.ts` 6 例全过；
- [x] `tests/004-note-math-rendering/math.test.ts` 调整后仍全过；
- [x] 真实组件渲染用户笔记：`katex-error` 0 个、残留 `$` 0 个、`katex-display` 52 个。
