# 020/02 · 提示词：公式格式与图片原样保留

- 状态：resolved
- 依赖：无
- 关联 spec 章节：§4 决策 4、§6、§7

## 目标

新生成的笔记从源头就写对公式分隔符；图片里的题目 / 板书 / 表格原样保留，不被模型改写或讲解。

## 改动点

1. `backend/app/gpt/prompt.py` 的 `BASE_PROMPT`：
   - 写作原则第 5 条拆成三条子项（行内只写 `$…$`；独立公式 `$$` 必须单独占一行；下标上标括号写准），并明确禁止 `\(…\)` / `\[…\]`；
   - 画面内容节新增两条：题目 / 选项 / 板书 / 表格原样保留、不改写不翻译不讲解；引用了截图就保留截图，不要只用一句话概括。
2. `backend/tests/020-note-rendering-and-batch-options/test_prompt_format_rules.py` 新建 4 例。

## 验收

- [x] 4 例全过；
- [x] `tests/015-note-preset-scene-and-detail` 54 passed（预设词表与占位符契约未被破坏）。
