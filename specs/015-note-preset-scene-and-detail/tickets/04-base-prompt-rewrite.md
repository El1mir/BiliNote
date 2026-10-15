# 04 · 主提示词重写：BASE_PROMPT 六条原则 + 追加片段去编号

- **依赖**：ticket 01（场景 / 详略片段与字段契约）— ✅ resolved 2026-10-15
- **关联**：spec 015 决策 10 / 11 / 12；二次修订说明
- **状态**：resolved 2026-10-15

## 目标

把 `backend/app/gpt/prompt.py` 的 `BASE_PROMPT` 按六条写作原则逐条重写，并消除它与新增「篇幅」档位之间的**直接对立**；同时把「追加片段不写行首编号」这条规则推到全部追加片段。

## 背景

用户在验收时追问「你把提示词都优化过了吗」。核对后的事实是：**只换了预设那 5 段，主提示词一行没动**——因为 spec 015 初版边界里写着「不改 BASE_PROMPT 主体」。

而没动的那份主体里藏着三个真问题：

1. **与「篇幅」直接对立**。`BASE_PROMPT` 原文写死了两句：
   - 「用户宁可笔记长一些，也不要漏掉内容。」
   - 「**不要**以「精简」为由删掉知识点、例题或推导过程。」

   而新增的详略片段是「**篇幅：精简** 只写结论层：每个小节一到三句话」。同一份提示词里两句话互相拉扯，选精简时模型听谁的没有定论。
2. **编号体系断了**。`BASE_PROMPT` 的原则编号 1.–6.，而追加的 format 片段从 **9.** 开始（`get_toc_format` 是 `9. **目录**`）——中间 7./8. 从来没有过。历史遗留的 `SCREENSHOT` 又是 `8.`、`LINK` 是 `9.`，与 format 的 9. 重号。
3. **标题层级没交代**。`get_toc_format` 假定目录基于 `##` 级标题、`get_link_format` 说「每个 `##` 追加时间戳」，但**四个格式开关全关掉时**，没有任何一处告诉模型笔记该用什么标题层级。

另外那段「输出说明」写得很绕：连着 6 行讲编号转义，还夹着两句重复的「(如果额外重要的任务有格式需求可以不遵守)」——而「额外重要的任务」直到文件最末尾才出现。

## 改动点

### 1. `backend/app/gpt/prompt.py`

| 位置 | 改动 |
| --- | --- |
| `BASE_PROMPT` | 整体重写（49 行 → 41 行）。修掉与「篇幅」的对立；补标题层级约定；把 6 行编号转义说明压成 1 行；两句逃逸口改成一条明确的优先级规则；「请始终遵循此规则。」（指代不明）删除 |
| `LINK` | 去掉行首 `9.` |
| `SCREENSHOT` | 去掉行首 `8.` |

### 2. `backend/app/gpt/prompt_builder.py`

- `get_toc_format` / `get_link_format` / `get_screenshot_format` / `get_summary_format` / `get_ocr_assist_screenshot_format`（两个分支）去掉行首 `9.` `10.` `11.` `12.`。
- 文件头那段讲编号的注释改写，说明为什么所有追加片段都不带编号。

### 3. 测试

- 新建 `backend/tests/015-note-preset-scene-and-detail/test_base_prompt_contract.py`（11 个用例）。
- `test_scene_detail_prompts.py`：删掉已被取代的 `FORMAT_NUMBERING` 与 `test_fragments_do_not_collide_with_format_numbering`（新文件的规则更强、覆盖面更广）。
- `test_generate_base_prompt_scene_detail.py:21`：断言里的 `"9. **目录**"` 改为 `"**目录**"`。

## 验收

- `BASE_PROMPT` 里的「篇幅」关系不再对立：出现「以篇幅指示为准」，且「精简」被定义为「不再逐段展开」「不是删内容」。
- 标题层级有明确约定（`##` / `###`）。
- 全部追加片段（format 四项 × 含 OCR 分支、`LINK`、`SCREENSHOT`、`AI_SUM`、5 段场景/详略）行首无编号。
- `BASE_PROMPT.format(video_title=..., tags=..., segment_text=...)` 正常，且 `Formatter` 解析出的字段**恰好**是这三个。

## 测试

`cd backend && .\.venv\Scripts\python.exe -m pytest tests/015-note-preset-scene-and-detail -q`

---

## Comments

### 实施记录（2026-10-15）

| 文件 | 改动 |
| --- | --- |
| `backend/app/gpt/prompt.py` | `BASE_PROMPT` 整体重写；`LINK` / `SCREENSHOT` 去编号 |
| `backend/app/gpt/prompt_builder.py` | 5 个 format 函数去编号（`11. **原片截图**` 有 3 处）；文件头注释改写 |
| `backend/tests/015-note-preset-scene-and-detail/test_base_prompt_contract.py` | 新建，11 用例 |
| `backend/tests/015-note-preset-scene-and-detail/test_scene_detail_prompts.py` | 删 2 处（被取代） |
| `backend/tests/015-note-preset-scene-and-detail/test_generate_base_prompt_scene_detail.py` | 1 行断言 |

### `BASE_PROMPT` 重写后的全文

```text
你是一个专业的笔记助手，擅长把视频转录内容整理成清晰、有条理、信息完整的笔记。

语言：
- 笔记正文用 **中文** 撰写。
- 专有名词、技术术语、品牌名、人名保留 **英文** 原词。
- 场景说明对术语另有要求时，以场景说明为准。

视频标题：
{video_title}

视频标签：
{tags}

视频分段（格式：开始时间 - 内容）：
---
{segment_text}
---

你的任务：
根据上面的分段转录内容，生成结构化的笔记。

输出要求：
- 只返回最终的 **Markdown 正文**，不要包在代码块里，也不要写「以下是笔记」这类开场白。
- 章节用 `## ` 标题，小节用 `### ` 标题。
- 不要在行首写 `1. **xxx**` 这种裸编号——Markdown 会把它渲染成有序列表。确实需要编号时，写成 `## 1. xxx`。

写作原则：

1. **完整信息**：默认记录尽可能多的相关细节，宁可长一些也不要漏掉内容。任务里若指定了「篇幅」，以篇幅指示为准；但题目、结论和关键数字在任何篇幅下都不能省。
2. **去除无关内容**：只省略广告、口头禅、寒暄和与主题无关的闲聊。不要以「精简」为由删掉知识点、例题或推导过程——「精简」指的是不再逐段展开，不是删内容。
3. **题目与例题完整保留**：题干、已知条件、选项、答案、解题步骤一个都不能少；其中的数字、字母、单位、编号原样保留。
4. **可读布局**：一段讲一件事，段落之间空一行；并列内容用项目符号，不要堆成大段文字。
5. **数学公式**：视频里出现的公式必须保留，用 LaTeX 语法写成 Markdown 可渲染的形式；行内写 `$...$`、独立成行写 `$$...$$`。符号、下标、上标、括号都要写准，不要简化或省略。
6. **修正转写错误**：转录来自自动语音识别，可能有错别字、同音字、术语识别错误或断句错误。结合上下文改写成通顺的书面表述（把认错的术语还原成正确写法），不要因为某句话读不通就跳过它——那通常是识别问题，不是内容问题。

优先级：下面的「额外重要的任务」优先于上面的通用原则；两者冲突时，以任务里的指示为准。

额外重要的任务如下（每一个都必须严格完成）：
```

### ⚠️ 一个真被咬到的坑：`String.replace` 的 `$$`

第一次写入时，第 5 条里写的「行内写 `$...$`、独立成行写 `$$...$$`」被写成了：

```text
行内用 `$...，独立成行用 `$...$`。
```

即 `$...$` 少了个 `$`、`$$...$$` 变成了 `$...$`。原因是那行文本是作为 **`String.replace()` 的替换串**传进去的，而替换串里的 `$$` 是转义序列（`$$` → `$`）。

修法：改用**函数式替换** `t.replace(old, () => newText)`，函数返回值不做 `$` 解释。这类批量改写脚本以后一律用函数式替换。

（顺带：这也说明改完必须读回原文核对，不能只看 `writeFile` 成功。）

### 为什么用 `Formatter` 而不是 `format()` 断言占位符

`BASE_PROMPT` 会走 `str.format(video_title=..., tags=..., segment_text=...)`，四家消费者（`prompt_builder`、`openai_gpt`、`qwen_gpt`、`deepseek_gpt`）共用。文案里多一个花括号就会让四家**一起**抛 `KeyError`。第 5 条写 LaTeX 时最容易踩到——`\frac{a}{b}` 里的 `{a}` 会被当成占位符。

所以断言用 `string.Formatter().parse(BASE_PROMPT)` 取出真正的字段名集合，断言它**恰好等于** `{{video_title, tags, segment_text}}`——比「format 不报错」强，因为后者只覆盖当次调用里恰好传了的键。

### 证据

- `backend/tests/015-note-preset-scene-and-detail`：**40 passed**（原 29；新增 11，删 2 处旧断言）。
- 全量后端回归：**817 passed, 5 warnings, 13 subtests passed in 86.40s**（历史基线 777）。
- pyright 对 `app/gpt/prompt.py` / `app/gpt/prompt_builder.py` / 两个测试文件 **0 errors**；ruff **All checks passed**。
- 运行时核对：`Formatter().parse()` → `['video_title', 'tags', 'segment_text']`；`LINK` 与 `SCREENSHOT` 里 `9. **Add time` / `8. **Screenshot` 均不再命中。

### 影响面（谁会被这次重写波及）

`BASE_PROMPT` 有四个消费者：`backend/app/gpt/prompt_builder.py:1`（现行主路径，经 `universal_gpt.py:2`）、以及三个历史 provider `backend/app/gpt/openai_gpt.py:4` / `qwen_gpt.py:4` / `deepseek_gpt.py:4`（它们另外拼 `SCREENSHOT` / `LINK` / `AI_SUM`）。四家都用同一组三个占位符，所以这次重写对四家同时生效。

⚠️ **没有对生成结果做端到端人工复核**：这次改的是提示词文本，验证只能到「文案自洽 + 契约测试 + 四家都能 `.format` 通过」。实际生成质量的改善需要真实跑几次视频才能判断，不在本次自动化范围内。

## Answer

**已完成**。`BASE_PROMPT` 六条原则逐条重写，三人对立的「宁可长 vs 精简」改成「默认完整、任务指定时以任务为准」并把「精简」定义成压缩表达而非删内容；补上标题层级约定；把 6 行编号转义说明压成 1 行并给出明确优先级。全部追加片段（format / OCR / LINK / SCREENSHOT）去掉行首编号，编号只留给恒定原则。新增 11 个契约用例锁住这些性质。
