# 01 · OCR 辅助配置与版面解析客户端

- **状态**：已实现；**协议抽象已于 2026-10-04 按用户要求撤销**（详见 §6）
- **依赖**：无（本 ticket 是 OCR 辅助模式的地基）
- **上游 spec**：`specs/008-ocr-assist-and-legacy-cleanup/spec.md` §6

> ⚠️ **本 ticket 的 §2「协议必须可配」在实现后被推翻。** 真机验证（见
> [01-api-verification.md](./01-api-verification.md) §9）把所有原本「不确定」的接线细节
> 全部证实，于是通用抽象失去了存在前提，被收敛为智谱 glm-ocr 专用。
> **§6 是实现后的实际情况**；§1–§5 保留原文，用于记录「当初为什么这么设计」。

## 目标

落地「OCR 辅助」的**配置层**与**调用层**，使上层流程可以拿到「给一张图片，返回它上面的 Markdown 文本」这一个能力，而不关心背后是 glm-ocr 的版面解析接口还是某个 OpenAI 兼容的视觉模型。

本 ticket **不改动**任何既有生成流程；它只新增能力与设置页。

## 范围

### 1. 配置存储 `config/ocr.json`

新增一个与 `TranscriberConfigManager` 同构的配置管理器（独立 JSON 文件、独立读写方法、不动数据库表）。

最少字段：

- `enabled`：总开关，默认 `false`
- `base_url`：服务基地址
- `api_key`
- `model_name`
- `protocol`（见下）
- `max_file_mb` / `max_pages`：护栏项

读写要求：

- 读取接口返回的 `api_key` **必须脱敏**（复用 provider 侧的 mask 思路）。
- 写入时若 `api_key` 含 `*`（即前端回传的是掩码值），**丢弃该字段**而不是存进掩码，避免污染已存密钥。这是 `ProviderService.update_provider` 已经踩过的坑。
- 提供「连接测试」方法：用一张内置的最小测试图打通一次调用，返回成功/失败与原始错误信息。

### 2. 协议适配：`protocol` 必须可配

调研结论是两条路都真实存在，且**不能假定只有一条**：

| protocol | 形态 | 说明 |
| --- | --- | --- |
| `layout_parsing` | 智谱 `glm-ocr` 类版面解析接口 | 结构化文档接口，输入 `file`（URL 或 base64 data URI），返回整页 Markdown |
| `openai_chat` | OpenAI 兼容 `/chat/completions` + `image_url` | 用多模态视觉模型充当 OCR（如 PaddleOCR-VL 一类） |

**为什么必须可配**：glm-ocr 不在智谱的对话模型枚举里，只能走专用端点；而不同部署（国内 open.bigmodel.cn / 国际 api.z.ai / 自建网关 / 第三方中转）的端点前缀、鉴权头是否带 `Bearer`、请求体字段名都可能不同。把这些**硬编码**会让一次上游改动直接打死整个功能。

因此适配器要把下面这些全部做成可配置或可探测，而不是写死：

- 端点路径（默认取 `layout_parsing` 形态的路径，但允许覆盖）
- 请求体字段名（`file` 字段名本身、以及可选的 `return_crop_images` / `need_layout_visualization` / 页范围字段）
- 鉴权头形态（`Authorization: <key>` vs `Authorization: Bearer <key>`）
- 响应取值路径（从响应 JSON 里取出 Markdown 文本的路径）

### 3. ⚠️ 必须先做接口验证

本 spec 写作时**没有拿到一手官方文档**（文档站点在该环境下不可达）。因此实现前必须先做一次真机验证，把结果写成本仓库可复现的记录（建议 `specs/008-.../tickets/01-api-verification.md`）：

需要逐项确认并记录：端点路径、鉴权头形态、请求体实际接受的字段、响应体里 Markdown 文本的真实位置与类型、单文件大小上限、页数上限（**注意：国内文档与国际文档在页数上限上存在 100 vs 30 的矛盾，取小值作为默认护栏**）、错误响应体形状。

**在验证完成前，不要声称 OCR 可用。** 验证不了的项目一律保持可配置，并在设置页给出明确提示。

### 4. 统一返回形态

无论走哪条 protocol，适配器对外只暴露一个统一结构，例如：

- `markdown`：提取到的文本
- `blocks`：可选的版面块列表（类型/位置/内容）
- `raw`：原始响应（用于排障，注意不要落盘 base64）

### 5. 输入形态

上层会递进来一个**本地图片文件路径**（抽出的单帧）。适配器负责：

- 读取文件并编码为 base64 data URI（若走 `layout_parsing`），或
- 按 OpenAI 兼容形态构造 `image_url`（若走 `openai_chat`）
- 发送前校验体积上限，超限给出**明确错误**，不静默压缩（沿用 spec 007 决策 10 的质量原则）

## 前端

新增「OCR 辅助」设置页：

- 注册进 `SettingPage/Menu.tsx` 的菜单列表与 `App.tsx` 路由
- 表单字段对应上述配置项
- 「连接测试」按钮，展示真实错误原文
- 未启用时页面可见但给出「当前未启用」的明确状态

## 验收

- 配置可存可读，读取回来的 `api_key` 是掩码；用掩码回写不会覆盖已存密钥。
- 连接测试在配置正确时返回成功，在错误配置时返回**可读的原始错误**（不是吞掉异常后的空返回值）。
- ~~两条 protocol 都能构造出请求；请求体不含硬编码的、本应可配的字段名。~~
  → **已作废**（§6）。现为：只有智谱一条路径，请求体形状是常量，由 `test_layout_parsing_request_shape_is_zhipu_specific` 与 `test_layout_parsing_request_has_no_stray_config_fields` 锁住。
- 超限图片给出明确错误，且**没有**被静默压缩后送出去。
- ~~接口验证记录落盘，其中每个「未能验证」项都被显式标注，并且对应的值在实现里是可配的。~~
  → **已完成并反向执行**：验证记录已落盘（`01-api-verification.md` §9，含 10 项实测确认），但「对应的值可配」被推翻——实测确认的值改成了常量。
- ~~新增后端测试覆盖配置读写、掩码回写、两条 protocol 的请求构造。~~
  → 实际覆盖：配置读写、掩码回写、**单条**请求构造、认证头、端点拼接、旧配置兼容、不可重试判定、CWD 无关的默认路径。

## 6. 实现后的实际情况（2026-10-04，本节取代 §2）

### 6.1 协议抽象被撤销

用户明确要求：「OCR 辅助这里不要做通用，先专门写成智谱清言的」。

**撤销的前提已被消除**：§2 存在的唯一理由是「接线细节无一手文档、可能因部署而异」。真机验证之后，
端点路径、鉴权头形态、请求体字段名、响应取值路径**全部实测确认**（`01-api-verification.md` §9.2），
不再有需要靠配置兜的未知量；而把这些字段摆在设置页，等于让用户回答「响应取值路径是什么」这种
他们不可能知道的问题。收益归零、代价仍在，故删除。

### 6.2 配置面：11 → 7

**保留可配**：`enabled` / `base_url` / `api_key` / `model_name` / `timeout` / `max_file_mb` / `max_pages`。

> `base_url` 是唯一真正会因部署而变的项（国内站 `open.bigmodel.cn` / 国际站 `api.z.ai` / 自建网关前缀不同）。
> 三个护栏项保留是因为它们与上游的真实限制相关，不是部署差异。

**改为模块常量**（`backend/app/services/ocr_config_manager.py`）：

| 常量 | 值 |
| --- | --- |
| `ENDPOINT_PATH` | `/api/paas/v4/layout_parsing` |
| `AUTH_SCHEME` | `"Bearer "` |
| `FILE_FIELD` | `"file"` |
| `RESPONSE_PATH` | `"md_results"` |

**直接删除**：`protocol`、`prompt`（那是 `openai_chat` 路径的概念）、`extra_params`。

`CONFIG_FIELDS` 是配置面的唯一真相；`OcrClient` 固定使用上述常量，`OcrResult.protocol` 字段保留但恒为 `PROTOCOL_NAME = "layout_parsing"`（落盘/日志/测试三处在用，删字段的改动面远大于收益）。

### 6.3 API 与前端

- 删除 `GET /api/ocr_config/protocols` 端点。现存路由：`GET /api/ocr_config`、`POST /api/ocr_config`、`POST /api/ocr_config/test`。
- 设置页删除协议下拉框与 6 个底层字段输入框（`endpoint_path` / `response_path` / `auth_scheme` / `file_field` / `prompt` / `extra_params`）。
- **卡片标题「高级（兼容性）」改名为「请求限制」**——注意这三个输入框与已删字段在同一张卡里，不能整卡删。
- Key 输入框下新增提示：智谱的 Key 形如 `{id}.{secret}`，中间那个点以及点之后的部分都不能少（这是真机上最容易踩、且 401 报错完全指不到的一个坑）。

### 6.4 升级兼容

`_normalize` 对旧文件里的已删键**读时忽略**：不报错、不迁移、不写入。老用户配置文件不会被判成损坏。
实测（构造完整旧格式配置）：可读、用户字段保留、协议残留被忽略、端点回到常量、写回后磁盘只剩 7 个键。

**已接受的代价**：原先配 `openai_chat` + 硅基流动（`base_url = https://api.siliconflow.cn/v1`）的用户，
升级后那套 key 会被拿去打智谱端点并必然失败。配置不会坏，但需改成智谱 Key；
401/403 已标为**不可重试**，所以不会白跑三轮。

### 6.5 真机暴露并修掉的三个缺陷

| # | 缺陷 | 修法 |
| --- | --- | --- |
| A | 认证失败被无意义重试：401 会完整重试三轮，每轮重新抽帧 + 两次 LLM 调用 | `OcrError.non_retryable`，由 `_NON_RETRYABLE_STATUS = (401, 403, 413)` 与 `_NON_RETRYABLE_CODES` 判定；接上 `note.py` 的 `last_error_non_retryable`。**500/502/504/429 保持可重试** |
| B | `OcrConfigManager` 相对路径依赖 CWD：从仓库根启动时静默读成空配置，却报「未配置 OCR 服务地址」 | `__init__` 把相对路径解析为 `Path(__file__).resolve().parents[2] / <relative>` |
| C | `generate_screenshot` 的 ffmpeg 无 timeout：跑在 `ThreadPoolExecutor.map` 里，卡住会让整个任务永久阻塞且无日志 | `_FFMPEG_TIMEOUT_SECONDS = 60` + `try/except subprocess.TimeoutExpired`，超时记 error 并 `return ""` |

### 6.6 收敛后的验证

- 后端全量 `pytest -q` → **409 passed, 5 warnings, 13 subtests passed**；spec 008 目录 → **120 passed**。
- 前端 `npx vite build` → 成功；OCR chunk **14.83 kB → 10.74 kB**（被删的抽象不再进包）。
- 真机回归：收敛后的 `OcrClient` 打真实截图 → `protocol=layout_parsing, markdown=332, blocks=4`，
  与收敛前**逐块一致**（text/image/text/formula，bbox 相同）→ 行为零回归。
