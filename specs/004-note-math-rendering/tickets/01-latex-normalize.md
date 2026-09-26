# 01 · 前端：LaTeX 分隔符归一化

- **依赖**：无
- **关联**：spec §3
- **状态**：✅ 已完成

## 改动点

1. 新增 `BillNote_frontend/src/utils/markdown.ts`：
   - `normalizeMathDelimiters(input)`：把 `\(...\)` → `$...$`、`\[...\]` → `$$...$$`；
   - 按 ``` 围栏切分，只在非代码块内容上替换；
   - 没有这两种分隔符时原样返回（零开销）。
2. `MarkdownViewer.tsx`：渲染笔记正文前套一层 `normalizeMathDelimiters`；
3. `ChatPanel.tsx`：AI 问答的回答同样套一层；
4. 新增 `BillNote_frontend/tests/004-note-math-rendering/math.test.ts`。

## 验收

- 行内 / 块级公式都能渲染；
- `$...$` 原样、代码块内原样、空值返回空串；
- `pnpm test` 全绿。
