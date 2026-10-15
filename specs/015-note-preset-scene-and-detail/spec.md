# Spec 015: 笔记预设改为「场景 × 详略」两个维度

- 状态：`implemented`（2026-10-15）
- 日期：2026-10-15
- 来源：用户请求（m02202）+ 代码调查结论 + 用户拍板（m02256 / m02257 / m02258 / m02259）
- 边界（⚠️ 2026-10-15 二次修订）：做「预设集合、请求字段契约、提示词文本、两处 UI」，**并含 BASE_PROMPT 与追加片段的重写**（见决策 10–12）。**不改** `extras` 自由文本、不改 format 四项开关的语义（只去掉它们的行首编号）。

> **二次修订说明**：本节最初写的「**不改** BASE_PROMPT 主体」已被撤销。用户在验收时追问「你把提示词都优化过了吗」，核对后发现只换了预设那几段，而 BASE_PROMPT 里「宁可长一些，也不要漏掉内容」与新增的「篇幅：精简」**直接对立**；用户随即拍板「顺手把 BASE_PROMPT 也过一遍，六条原则一起优化」。详见 [ticket 04](./tickets/04-base-prompt-rewrite.md) 与决策 10–12。

## 背景

「笔记风格」是生成表单上的一个下拉，代码里有 9 个预设。调查后确认它同时存在四个问题：

**1. 同一份清单有三份拷贝，外加一份死代码。**

| 位置 | 内容 | 状态 |
| --- | --- | --- |
| `backend/app/gpt/prompt_builder.py:92-119` `style_map` | 9 段真正进提示词的文本 | 唯一影响输出的地方 |
| `backend/app/gpt/prompt_builder.py:10-20` `note_styles` | 9 个 `{label, value}` | **死代码**：`backend` 里只 import 了 `generate_base_prompt`（`app/gpt/universal_gpt.py:2`），该列表零引用 |
| `BillNote_frontend/src/constant/note.ts:17-27` `noteStyles` | web 端下拉 | 独立一份，顺序还与后端不同（教程 / 学术互换） |
| `BillNote_extension/src/logic/types.ts:95-105` `NOTE_STYLES` | 扩展端下拉 + `NoteStyle` 联合类型 | 第三份 |

**2. 9 个提示词质量极端不均，且有两个完全相同。**

| label | value | 提示词 | 字数 |
| --- | --- | --- | --- |
| 精简 | `minimal` | `1. **精简信息**: 仅记录最重要的内容，简洁明了。` | 51 |
| 详细 | `detailed` | `2. **详细记录**: 包含完整的内容和每个部分的详细讨论。需要尽可能多的记录视频内容，最好详细的笔记` | 76 |
| 教程 | `tutorial` | `9.**教程笔记**:尽可能详细的记录教程,特别是关键点和一些重要的结论步骤` | 67 |
| 学术 | `academic` | `3. **学术风格**: 适合学术报告，正式且结构化。` | 51 |
| 小红书 | `xiaohongshu` | 17 行爆款关键词表 + 二极管标题法 + emoji 规则 | **648** |
| 生活向 | `life_journal` | `5. **生活向**: 记录个人生活感悟，情感化表达。` | 55 |
| 任务导向 | `task_oriented` | `6. **任务导向**: 强调任务、目标，适合工作和待办事项。` | 60 |
| 商业风格 | `business` | `7. **商业风格**: 适合商业报告、会议纪要，正式且精准。` | 55 |
| 会议纪要 | `meeting_minutes` | `8. **会议纪要**: 适合商业报告、会议纪要，正式且精准。` | 55 |

`business` 与 `meeting_minutes` 除编号和粗体名外**逐字相同**；`xiaohongshu` 一段 648 字，其余 8 段平均 59 字（12 倍差距）；51–60 字那几段只说了「是什么风格」，没有一条可执行的写作动作。

**3. 提示词前面的编号 1.–9. 是残留，而且会撞号。**
一次只追加**一个**风格片段（`prompt_builder.py:66-67`），模型看到的是孤零零的「7. **商业风格**…」，前面没有 1.–6.；而格式块用的是 9.–12.（`get_toc_format` → `9. **目录**`），于是 `tutorial`（`9.**教程笔记**`）与 `toc`（`9. **目录**`）**同时出现时都叫 9**。

**4. 未知取值静默失效，且历史值会被回放。**
请求模型 `style: str = None`（`backend/app/routers/note.py:84`）没有白名单；`style_map.get(style, '')`（`prompt_builder.py:120`）对未知值返回空串 —— 模型一条风格指令都收不到，不报错、不记日志。`style` 同时在 `PAYLOAD_KEYS`（`app/services/task_retry.py:71-85`）与 `_PAYLOAD_KEYS`（`app/services/task_recovery.py:58-76`）里，所以重试 / 重启恢复会回放**当时**的取值。

**另外：没有 spec，也没有一条测试。** 9 个预设的出处是 `CHANGELOG.md:173`；`get_style_format` 零用例，唯二碰 `prompt_builder` 的测试把整个模块 stub 掉了（`backend/tests/test_universal_gpt_checkpoint.py:37`、`backend/tests/test_universal_gpt_content_format.py:38`）。

**根因（本次要修的）**：9 个预设在语义上是**两个正交维度**被压平成了一个下拉 —— 「详略」（精简 / 详细）与「场景 / 体裁」（学术 / 教程 / 商业 / 会议纪要 / 小红书 / 生活向 / 任务导向）根本不是同一类东西。压平之后不管怎么删都别扭：删「详细」就失去控制篇幅的能力，删「学术」就失去场景。

## 目标

1. 预设改成两个正交维度：**场景**（生活 / 学术 / 专业，3 项）× **详略**（精简 / 详细，2 项）。
2. 每个维度的提示词都给**可执行的写作动作**，不再只写「适合××风格」。
3. 请求契约从单个 `style` 拆成 `scene` + `detail`，一路透传到 `GPTSource` 与 `payload_json`。
4. 删掉后端的死代码 `note_styles`，以及提示词里的残留编号。
5. web 端与扩展端各两个并排下拉；笔记详情页显示「场景 · 详略」。

## 非目标

- **不做老任务兼容**（见决策 4）。
- 不改 BASE_PROMPT 主体（`backend/app/gpt/prompt.py`）。
- 不改 `extras` 自由文本字段的行为。
- 不改 format 四项开关。
- 不把清单收敛到后端（见决策 6）。
- 不动 `xiaohongshu` 那段 648 字提示词的**内容**：它随「小红书」预设一起删除，不做迁移。

## 已定决策

| # | 决策 | 依据 / 代价 |
| --- | --- | --- |
| 1 | 预设改为**两个正交维度**：场景 × 详略 | 用户 m02256 拍板。代价：表单多一个控件，两个字段都要透传并写进 payload |
| 2 | 场景 = `life` 生活 / `academic` 学术 / `professional` 专业 | 用户 m02257 拍板。**不保留**小红书；**不设**「标准」详略档 |
| 3 | 详略 = `brief` 精简 / `detailed` 详细 | 用户 m02257 拍板 |
| 4 | **不做老任务兼容**：不写旧值→新组合的映射表；旧 payload 里的 `style` 被 `PAYLOAD_KEYS` 白名单丢弃 | 用户 m02258 选择。代价：老任务重试 / 重启恢复时拿不到场景与详略指令（静默，与现状「未知值静默失效」同一类行为）。理由：九个旧值无法无损映射到两个维度，且映射表会永久留在代码里 |
| 5 | 提示词去掉 1.–9. 编号前缀 | 编号是「九个风格曾被拼进同一份提示词」的残留；一次只追加一条，模型会看到孤立编号，且与格式块的 9.–12. 撞号 |
| 6 | **前端常量继续做预设清单的唯一来源**；后端删掉 `note_styles`，只保留提示词映射 | 用户 m02259 拍板。代价：新增场景 / 详略仍要同时改 web 与扩展两处 |
| 7 | 表单用两个并排下拉 | 用户 m02259 拍板 |
| 8 | 提示词用**正面表述**写（给动作，不给禁令） | 走 `writing-for-agents`：禁令会把被禁行为拉进上下文。凡「不要 ××」改写为「写 ××」 |
| 9 | 默认值：详略 = `detailed`、场景 = `life` | **实施假设**（非用户拍板），可随时改、无迁移成本。现状默认是 `minimal`（`NoteForm.tsx:158`）；改成「不丢内容」的档 |
| 10 | **BASE_PROMPT 一并重写**，六条写作原则逐条过 | 用户 m02550 追问后拍板（撤销原「不改主体」边界）。代价：改动面从「预设」扩到「生成质量核心」，非确定性输出的人工复核成本更高 |
| 11 | 「追加片段不写行首编号」升级为**全局规则**：format 四项、OCR 截图分支、`LINK` / `SCREENSHOT` 全部去掉编号 | 决策 5 的推广。理由：这些片段按勾选一次只追加一条，编号**无法保证连续**（没勾目录时 8. 9. 10. 直接跳号），且孤立数字只消耗注意力。编号只留给 BASE_PROMPT 那六条恒定原则 |
| 12 | BASE_PROMPT 与「篇幅」的关系定为：**默认完整；任务里指定了篇幅就以任务为准**；并把「精简」定义为「不再逐段展开」而不是「删内容」 | 原来两句话直接对立，等于让模型每次自己猜。定义成「压缩表达」后，两条规则才可能共存 |

### 旧 9 个预设的去向（说明性，不是兼容表）

| 旧 label / value | 去向 |
| --- | --- |
| 精简 `minimal` | → 详略 `brief` |
| 详细 `detailed` | → 详略 `detailed` |
| 学术 `academic` | → 场景 `academic` |
| 教程 `tutorial` | → 场景 `professional`（教程＝照着做的专业内容） |
| 任务导向 `task_oriented` | → 场景 `professional` |
| 生活向 `life_journal` | → 场景 `life` |
| 小红书 `xiaohongshu` | 删除 |
| 商业风格 `business` | 删除（与会议纪要逐字相同） |
| 会议纪要 `meeting_minutes` | 删除（与商业风格逐字相同） |

## 接口草案

### 请求契约

```json
{
  "scene": "academic",
  "detail": "detailed"
}
```

- 两个字段都是可选字符串，缺省即不追加对应的提示词片段。
- `style` 从请求模型、`GPTSource`、`_build_task_kwargs`、`PAYLOAD_KEYS`、`_PAYLOAD_KEYS` 中**移除**。
- 未知取值仍然静默返回空串 —— 与现状一致，本 spec 不改这个行为（清单由前端常量拥有，见决策 6）。

### 后端

```python
# backend/app/gpt/prompt_builder.py
SCENE_PROMPTS: dict[str, str]   # life / academic / professional
DETAIL_PROMPTS: dict[str, str]  # brief / detailed

def get_scene_prompt(scene: str | None) -> str
def get_detail_prompt(detail: str | None) -> str

def generate_base_prompt(..., scene=None, detail=None, ...)
```

拼接顺序（`generate_base_prompt` 内）：OCR 参考 → format 片段 → **场景** → **详略** → extras。

### 提示词草稿（后端唯一实现，前端只引用 value 与 label）

```python
SCENE_PROMPTS = {
    "life": (
        "**场景：生活**\n"
        "读者是看视频的本人，几个月后回来翻看这份笔记回忆当时。\n"
        "- 保留具体的人名、地点、时间、价格、数字：它们比结论更值得留。\n"
        "- 用第一人称记下当时的感受，以及这件事为什么值得记。\n"
        "- 一段话讲一件事，段与段之间空行分开。"
    ),
    "academic": (
        "**场景：学术**\n"
        "读者要引用或复述这份内容，可能在写论文、做汇报、备考。\n"
        "- 术语首次出现时同时给出原文（英文 / 拉丁文），此后统一用同一个译名。\n"
        "- 一个论点一小节：先写结论句，再写支撑它的证据或推导。\n"
        "- 视频里没有讲清、或与常识冲突的地方，标注「视频未说明」，照实留白。\n"
        "- 引用具体说法时附上时间点，便于回查。"
    ),
    "professional": (
        "**场景：专业**\n"
        "读者要照着这份笔记把内容用起来：做项目、跑流程、上手工具。\n"
        "- 把可执行的部分拆成有序步骤，每步写清「做什么」和「怎么判断这一步成了」。\n"
        "- 命令、参数、配置项原样抄进代码块，不改写、不省略。\n"
        "- 视频一带而过、实际操作会卡住的地方，单独写成「待确认」。\n"
        "- Docker、token、embedding 这类术语保留原词。"
    ),
}

DETAIL_PROMPTS = {
    "brief": (
        "**篇幅：精简**\n"
        "只写结论层：每个小节一到三句话，给出该节的结论与关键步骤。"
    ),
    "detailed": (
        "**篇幅：详细**\n"
        "逐段覆盖字幕内容：每个小节把该段的例子、数字、推导、原话都写进去。\n"
        "小节按视频的段落顺序排列。"
    ),
}
```

设计说明：

- 用 `**场景：××**` 粗体行而不是 `##` 标题，与既有 format 片段的写法一致，避免模型把新标题当成要复现的正文结构。
- 每条都是**动作**（保留什么、怎么拆、抄进哪里），不是形容（「正式且结构化」这类写法在旧版里占了 5/9）。
- 场景片段先交代「读者是谁、他拿这份笔记干什么」，再给动作 —— 这是让详略与场景两个维度**互不冲突**的关键：场景定内容与措辞，详略定覆盖范围。

## 影响面

| 文件 | 改动 |
| --- | --- |
| `backend/app/gpt/prompt_builder.py` | 删 `note_styles`（L10-20）；删 `get_style_format`；新增 `SCENE_PROMPTS` / `DETAIL_PROMPTS` / `get_scene_prompt` / `get_detail_prompt`；`generate_base_prompt` 的 `style` 参数换成 `scene` + `detail` |
| `backend/app/gpt/universal_gpt.py` | L118 / L424 / L620 / L632 / L654：`style` → `scene` + `detail` |
| `backend/app/models/gpt_model.py` | L14 `style` → `scene` + `detail` |
| `backend/app/routers/note.py` | L84 请求模型 / L969 / L1030 / L1076 / L1101 / L1280 |
| `backend/app/services/note.py` | L266 / L292 / L616 / L1971 / L1989 / L2016 |
| `backend/app/services/task_retry.py` | L78 `PAYLOAD_KEYS` |
| `backend/app/services/task_recovery.py` | L65 `_PAYLOAD_KEYS` |
| `BillNote_frontend/src/constant/note.ts` | `noteStyles` → `noteScenes` + `noteDetails`（各带 label） |
| `BillNote_frontend/src/pages/HomePage/components/NoteForm.tsx` | L55 zod / L158 默认值 / L193 / L326 提交 / L493-514 换成两个 Select |
| `BillNote_frontend/src/pages/HomePage/components/BatchImportDialog.tsx` | L27 / L224 |
| `BillNote_frontend/src/pages/HomePage/components/MarkdownViewer.tsx` | L304 / L326 / L429-430 |
| `BillNote_frontend/src/pages/HomePage/components/MarkdownHeader.tsx` | L12-13 / L27-28 / L54 / L79 |
| `BillNote_frontend/src/services/note.ts` | L77 / L241 |
| `BillNote_frontend/src/store/taskStore/index.ts` | L118 |
| `BillNote_extension/src/logic/types.ts` | L86-105 / L123 |
| `BillNote_extension/src/popup/Popup.vue` | L204 |
| `BillNote_extension/src/options/pages/General.vue` | L138-139 |

## 流程

1. 前端提交 `{scene, detail}` → `POST /api/generate_note`。
2. `_build_task_kwargs` 透传 → `run_note_task` → `NoteGenerator.generate_note`（`services/note.py:266`）→ `universal_gpt`（`universal_gpt.py:118`）→ `GPTSource`。
3. `generate_base_prompt` 依次追加 format / 场景 / 详略 / extras，拼出最终提示词。
4. 提交时的 `{scene, detail}` 进 `payload_json`，供重试与重启恢复重建参数。

## 测试要点

后端（`backend/tests/015-note-preset-scene-and-detail/`）：

- `get_scene_prompt` / `get_detail_prompt`：每个合法取值返回非空、互不相同、不含 `1.`–`9.` 形式的编号前缀；未知取值 / `None` 返回 `''`。
- `generate_base_prompt`：同时给 scene 与 detail 时两段都出现且场景在详略之前；只给其一时另一段不出现；都不给时提示词里不含任何场景 / 篇幅标记。
- 字段契约：`GenerateRequest` 不再接受 `style`、`scene`/`detail` 能一路出现在 `GPTSource`；`PAYLOAD_KEYS` 与 `_PAYLOAD_KEYS` 含 `scene`/`detail`、不含 `style`。
- 无编号断言：把 `SCENE_PROMPTS` + `DETAIL_PROMPTS` 的全部取值拼起来，断言不含与 format 片段撞号的编号前缀（回归 m02246 发现的问题）。

前端（`BillNote_frontend/tests/015-note-preset-scene-and-detail/`）：

- 两个常量表的 value 集合与后端 `SCENE_PROMPTS` / `DETAIL_PROMPTS` 的 key 集合一致（防止三处再次漂移；扩展端由同一份断言覆盖）。

> 说明：web 端与扩展端的下拉渲染不写组件测试（仓库没有组件测试基建），靠 `pnpm lint` + `pnpm build` / `pnpm typecheck` 兜住类型与语法。

## 实现清单

| # | 工单 | 状态 |
| --- | --- | --- |
| 01 | [后端：场景 / 详略提示词与字段契约](./tickets/01-backend-scene-detail.md) | **resolved** 2026-10-15 |
| 02 | [web 端：两个下拉 + 提交 + 展示](./tickets/02-web-scene-detail.md) | **resolved** 2026-10-15 |
| 03 | [浏览器扩展：两个下拉 + 设置项](./tickets/03-extension-scene-detail.md) | **resolved** 2026-10-15（⚠️ 验收项「`pnpm typecheck` 通过」在改动前即不成立：18 条既有的 `browser` 类型错误，详见 ticket Comments） |
| 04 | [主提示词重写：BASE_PROMPT 六条原则 + 追加片段去编号](./tickets/04-base-prompt-rewrite.md) | **resolved** 2026-10-15 |

## 待确认问题

无。
