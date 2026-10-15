# 01 · 后端：场景 / 详略提示词与字段契约

- **依赖**：无
- **关联**：spec 015（§已定决策 1–5、8、9；§接口草案；§影响面；§测试要点）
- **状态**：resolved 2026-10-15

## 目标

把后端唯一影响输出的地方（`prompt_builder`）从「九个压平的风格」换成「场景 × 详略」，并把请求契约从单字段 `style` 换成 `scene` + `detail`。

## 背景

见 spec 015 §背景。要修的四件事：三份拷贝里的后端死代码、9 段质量不均的提示词、与格式块撞号的编号前缀、以及 `style` 这个承载了两种语义的单字段。

## 改动点

1. `backend/app/gpt/prompt_builder.py`
   - **删** `note_styles`（L10-20，零引用的死代码）与 `get_style_format`（L91-120）。
   - **新增** `SCENE_PROMPTS` / `DETAIL_PROMPTS` 与 `get_scene_prompt(scene)` / `get_detail_prompt(detail)`。文本逐字用 spec 015 §接口草案里的草稿；取值：`life` / `academic` / `professional`，`brief` / `detailed`。
   - `generate_base_prompt`：`style=None` → `scene=None, detail=None`；在 format 之后、extras 之前依次追加两段（场景在前）。**不加编号前缀。**
2. `backend/app/models/gpt_model.py:14`：`style: Optional[str] = None` → `scene: Optional[str] = None` + `detail: Optional[str] = None`。
3. `backend/app/gpt/universal_gpt.py`：L118 `style=kwargs.get('style')` → `scene` / `detail`；L424（`checkpoint` 的键）、L620 / L632 / L654（三处 `generate_base_prompt(..., style=source.style)`）同步。
   - ⚠️ L424 是 checkpointer 的去重 / 恢复键：两个字段都要进，否则「只改了详略」的重跑会命中旧检查点。
4. `backend/app/routers/note.py`：L84（`GenerateRequest`）→ `scene: Optional[str] = None` + `detail: Optional[str] = None`；L969（构造 `GPTSource` 或 kwargs 的那处）、L1030（`run_note_task` 形参）、L1076（转发）、L1101（`payload` 字典）、L1280（批量端点形参）同步。
5. `backend/app/services/note.py`：L266（`generate_note` 形参）、L292（docstring）、L616（转发）、L1971 + L1989 + L2016（第二个生成入口）同步。
6. `backend/app/services/task_retry.py:78` 与 `backend/app/services/task_recovery.py:65`：白名单里的 `"style"` 换成 `"scene"` + `"detail"`（决策 4：**不做**旧值映射，旧 payload 里的 `style` 直接丢弃）。
7. `CHANGELOG.md`：本次是用户可见的行为变更（预设从 9 个变两个维度），在 `## [Unreleased]` 的 **Changed** 里加一条。文件是 CRLF，按下节「写 CRLF 文件」的办法改。
8. `GLOSSARY.md`：新增两条概念（只写概念与边界，不写字段名）。

## 验收

- `python -c "from app.gpt.prompt_builder import get_scene_prompt, get_detail_prompt"` 可用；模块里不再有 `style_map` / `note_styles` / `get_style_format`。
- 同时给 `scene="academic"` 与 `detail="brief"` 时，生成的提示词里**场景段在详略段之前**，且两段都在 format 段之后。
- 提示词里不出现 `1.`–`9.` 形式的风格编号前缀。
- `grep -rn "style" backend/app/gpt backend/app/routers/note.py` 只剩 format / 无关命中（如 `api_style`、CSS `style=` 不属于本仓库后端）。
- 全量后端回归不低于 777 passed（spec 014 完成时的基线）。

## 测试

新建 `backend/tests/015-note-preset-scene-and-detail/`：

- `test_scene_detail_prompts.py`：
  - 每个合法取值返回非空串，且三个场景 / 两个详略彼此不同；
  - 未知取值与 `None` → `''`；
  - **无编号断言**：把五段拼起来，断言不含 `re.compile(r"^\s*\d+\.\s", re.M)` 形式的行首编号（回归 spec 015 §背景问题 3）。
- `test_generate_base_prompt_scene_detail.py`：
  - 两段都出现、顺序为 场景 → 详略；
  - 只给其一时另一段不出现；
  - 都不给时不含 `**场景：` / `**篇幅：` 标记；
  - format 段仍在两段之前。
- `test_preset_contract.py`：
  - `GenerateRequest` 的字段集合含 `scene` / `detail`、不含 `style`；
  - `task_retry.PAYLOAD_KEYS` 与 `task_recovery._PAYLOAD_KEYS` 含 `scene` / `detail`、不含 `style`；
  - `GPTSource` 有 `scene` / `detail` 字段。
- `test_preset_vocabulary_sync.py`（跨端一致性）：
  - 从 `BillNote_frontend/src/constant/note.ts` 与 `BillNote_extension/src/logic/types.ts` 的源码文本里正则提取 value 列表，断言与 `SCENE_PROMPTS` / `DETAIL_PROMPTS` 的 key 集合相等。这条防的是 spec 015 背景问题 1（三份拷贝再次漂移）。
  - 路径从 `Path(__file__).parents[3]` 起算；文件缺失时 `pytest.skip`（后端单独 checkout 时不应红）。

## 写 CRLF 文件（`CHANGELOG.md`）的办法

仓库里 `CHANGELOG.md` / `backend/app/routers/config.py` 是 CRLF，而编辑工具只认 LF（多行 `old_str` 匹配不到，且会把 LF 插进 CRLF 文件造成混行尾）。用一次性 Python 脚本：读成 `raw` → `text = raw.replace("\r\n", "\n")` → 断言锚点 `count == 1` → 替换 → `path.write_bytes(text.replace("\n", "\r\n").encode("utf-8"))`，跑完删除，并用 `crlf / loneLf` 计数验证。

---

## Comments

### 实施记录（2026-10-15）

| 文件 | 改动 |
| --- | --- |
| `backend/app/gpt/prompt_builder.py`（**CRLF**） | 删 `note_styles`（死代码）与 `get_style_format`；新增 `SCENE_PROMPTS` / `DETAIL_PROMPTS` / `get_scene_prompt` / `get_detail_prompt`；`generate_base_prompt` 的 `style=None` → `scene=None, detail=None`，追加顺序固定为「场景 → 详略」。**196 行**，改后 `note_styles` / `get_style_format` 与独立词 `style` 全部 0 命中 |
| `backend/app/models/gpt_model.py`（**CRLF**） | `GPTSource.style` → `scene` + `detail` |
| `backend/app/gpt/universal_gpt.py` | 4 处：kwargs 取值、**checkpointer 的键 `"style": source.style`**、两处 chunker 调用 + create_messages |
| `backend/app/routers/note.py` | 6 处：`VideoRequest`(L84-85)、`_build_task_kwargs`、`run_note_task` 形参、转发调用、`task_kwargs` 字典、`BatchGenerateRequest`(L1285-1286) |
| `backend/app/services/note.py` | 6 处：`generate_note` 形参 + docstring、`_summarize_text` 调用与形参 + docstring、构造 `GPTSource` 处 |
| `backend/app/services/task_retry.py` / `task_recovery.py` | 两份白名单 `"style"` → `"scene"` + `"detail"`（各 18 键） |
| `backend/app/db/models/video_tasks.py:20` | 注释里的字段清单同步 |
| 新建 `backend/tests/015-note-preset-scene-and-detail/` | 4 个测试文件，29 个用例 |

### ⚠️ **`universal_gpt.py:424` 的 checkpointer 键必须同步**

那一行是 `"style": source.style`，属于**检查点签名**（用来判断「这次请求跟上次是否一致，能不能复用缓存的分块结果」）。如果只改数据模型不改它，签名里永远带着一个恒为 `None` 的 `style`，**只改详略的重跑会命中旧检查点**、拿到上一次的笔记。已改成 `"scene"` + `"detail"` 两个键。

### 三条既有测试被字段重命名打破（位置传参）

`_summarize_text` 的参数列表里插进一个新参数，会让**按位置传参**的调用方整体错位：

- `backend/tests/005-modern-dark-ui-and-task-progress/test_real_task_id_threading.py`：两处位置传参 → 改为关键字传参（`audio_meta=` / `transcript=` / `gpt=` / `markdown_cache_file=` / `link=` / `screenshot=` / `formats=` / `scene=None` / `detail=None` / `extras=None` / `video_img_urls=[]` / `task_id="real-task-id"`）。
- `backend/tests/008-ocr-assist-and-legacy-cleanup/test_ticket02_flow.py:1224`：`style=None,` → `scene=None, detail=None,`。
- `backend/tests/011-failed-task-retry/test_failed_task_retry.py:55`：payload 字面量 `"style": None,` → `"scene": None, "detail": None,`。

### 测试制造的一个真实坑：`VideoRequest` 会跑真实平台识别

`backend/app/routers/note.py:126` 附近有一个 `@field_validator("video_url")`，构造 `VideoRequest` 时会真的走平台识别 —— 用 `https://example.com/v` 会抛 `app.exceptions.note.NoteError: 选择的平台不受支持`。测试里必须用合法链接，已定义 `BILIBILI_URL = "https://www.bilibili.com/video/BV1xx411c7mD"`。

另有一处自伤：最初断言 `hasattr(task_recovery, "recover_unfinished_tasks")` —— 该函数**不存在**（真实入口是 `start_recovery_thread`）。已换成结构性断言 `test_build_task_kwargs_keys_match_the_whitelists`：`set(_build_task_kwargs(...)) - {"task_id"} == set(PAYLOAD_KEYS) == set(_PAYLOAD_KEYS)`。

### CHANGELOG / GLOSSARY 已同步

- `CHANGELOG.md`（CRLF，改后 CRLF=314 / LF=314，无混行尾）：`## [Unreleased]` → `### Changed` 顶部新条目，写明九预设的三个病（`business` 与 `meeting_minutes` 逐字相同、`xiaohongshu` 一段 648 字是其余平均的 12 倍、`tutorial` 与「目录」编号撞号）与「`style` 直接移除、不做旧值映射」这条破坏性说明。
- `GLOSSARY.md`：新增 `## 场景与详略（Scene / Detail）` —— 组合数**相乘而非相加**，把正交维度压成互斥列表正是退化成九个同质预设的原因。

### 证据

- `backend/tests/015-note-preset-scene-and-detail` → **29 passed**。
- 后端全量回归 → **806 passed, 5 warnings, 13 subtests passed in 80.71s**（历史基线 777，spec 015 前是 800）。
- 运行时断言：`dataclasses.fields(GPTSource)` 与 `VideoRequest` / `BatchGenerateRequest` 的 `model_fields` 都含 `scene` / `detail`、无 `style`。

## Answer

**已完成**。契约 `scene`(life/academic/professional) + `detail`(brief/detailed) 贯通「请求模型 → 任务参数 → 白名单 → GPTSource → 检查点签名 → 提示词拼接」；两段提示词无编号、以 `**场景：××**` / `**篇幅：××**` 起头，拼接顺序 OCR → format → 场景 → 详略 → extras。

`test_preset_vocabulary_sync.py` 把前端 / 扩展 / 后端**三处词表**（含顺序与扩展的类型联合）钉在一起，任何一侧单方面改动都会红 —— 这是 spec 015 背景问题 1（三份拷贝漂移）的根治点。
