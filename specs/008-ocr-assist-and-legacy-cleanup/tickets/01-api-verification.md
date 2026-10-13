# 01 · 接口验证记录（GLM-OCR / 版面解析）

- **状态**：✅ **真机验证已完成**（2026-10-04）——结论见 **§9**
- **上游 ticket**：`specs/008-ocr-assist-and-legacy-cleanup/tickets/01-ocr-config-and-layout-client.md` §3
- **调研日期**：2026-02（spec 008 实现期间）；**真机验证日期**：2026-10-04

> **阅读指引**：§0–§8 是**验证之前**的文档级调研结论，其中一部分已被真机推翻
> （尤其 §0「零实测」、§3 的「未验证项→可配置字段」映射、§5 的 `openai_chat` 备选路径）。
> **§9 才是权威结论**，与前八节冲突时以 §9 为准。前八节保留是为了记录推理过程与
> 「当初为什么做了通用抽象、又被什么事实推翻」。

## 0. 一句话结论（**已被 §9 取代**）

**本仓库没有任何一次对上游 OCR 服务的已认证调用。** 下面每一条结论都来自搜索引擎索引到的厂商文档页面与公开 SDK 源码，并做过至少两轮独立交叉核对；但**没有一条是抓包或真机响应**。

因此 ticket 01 的验收标准「在验证完成前，不要声称 OCR 可用」被严格执行：

- 所有本文标注为**未验证**的项，在实现里一律**可配置**（见 §3 的映射表），不写死。
- 设置页与 `test_connection()` 的失败分支都会把上游原始响应体透出，便于真机验证时直接读数。
- 本文件在真机验证完成后应被**改写**为实测结论，并把「未验证」标记逐项摘掉。

## 1. 来源与可信度分级

| 级别 | 含义 | 本文中的用途 |
| --- | --- | --- |
| A | 多个独立来源一致（厂商文档 + 官方 SDK 源码 + 第三方实现） | 可以作为默认值 |
| B | 单一来源，或来源之间措辞不一致但可收敛 | 作为默认值 + 必须可配 |
| C | 来源之间**直接矛盾**，或只有间接推断 | **只做兼容处理，不假定任何一种** |

## 2. 逐项确认表

### 2.1 端点与鉴权

| 项 | 结论 | 级别 | 实测 |
| --- | --- | --- | --- |
| 端点路径 | `POST {base_url}/api/paas/v4/layout_parsing` | A | ❌ |
| 国内基地址 | `https://open.bigmodel.cn` | A | ❌ |
| 国际基地址 | `https://api.z.ai` | A | ❌ |
| 鉴权头 | `Authorization: Bearer <API_KEY>`，**两个站点都一样** | B | ❌ |
| 鉴权头疑点 | 国内 `layout_parsing` 文档页**漏写了 `Bearer`**，但国内「HTTP 调用简介」页与所有可用 SDK 都带 `Bearer`；判定为文档笔误 | B | ❌ |

> **实现取舍**：`auth_scheme` 做成配置项，默认 `"Bearer "`，拼接方式固定为 `f"{auth_scheme}{api_key}"`。若真机发现国内确实要裸 key，把该字段清空即可，不需要改代码。

### 2.2 请求体

| 字段 | 结论 | 级别 | 实测 |
| --- | --- | --- | --- |
| `model` | 单值枚举 `"glm-ocr"` | A | ❌ |
| `file` | **http URL 或 `data:<mime>;base64,...` data URI**；该接口**不接受 multipart 上传** | A | ❌ |
| `return_crop_images` | 可选布尔，返回裁切图 | B | ❌ |
| `need_layout_visualization` | 可选布尔，返回版面可视化图 | B | ❌ |
| `start_page_id` / `end_page_id` | 可选，仅 PDF，**1-based** | B | ❌ |
| `request_id` / `user_id` | 可选，透传标识 | B | ❌ |

> **实现取舍**：`file` 的字段名、端点路径、上述可选字段全部走 `file_field` / `endpoint_path` / `extra_params` 配置，不写死。

### 2.3 响应体

| 项 | 结论 | 级别 | 实测 |
| --- | --- | --- | --- |
| Markdown 文本位置 | 顶层 `md_results`，类型是**扁平字符串**（不是数组、不是对象） | A | ❌ |
| 版面块位置 | 顶层 `layout_details`，类型 `object[][]` = **页数组的数组**，每页内是元素数组 | B | ❌ |
| 版面块字段 | `index`、`label`、`content`、`height`、`width`、`bbox_2d` | B | ❌ |
| `label` 枚举 | 恰好是 `{image, text, formula, table}` 四种 | **A** | ❌ |
| `label` 分层 | SDK 自托管层有 10 种细粒度 label（`title/text/table/figure/formula/header/footer/page_number/reference/seal`），托管 API 经 `label_visualization_mapping` 归并成上述 4 种后才返回 | **A** | ❌ |
| `label == "image"` 的 `content` | **恒为 `null`**（键存在、值为空）；不是 URL、不是 base64、不是 alt 文字 | **A** | ❌ |
| 单张图片是否返回 `layout_details` | **返回**，外层数组长度为 1 | **A** | ❌ |
| 「该区块没有可用文字」信号 | API 原生**没有**布尔标志位，隐式信号就是 `content is null` | **A** | ❌ |
| 图片在 `md_results` 里的形态 | markdown 图片引用 `![](...)`；**只有位置、没有文字** | B | ❌ |
| `layout_details[].index` 进制 | ⚠️ **未验证**：国内示例从 `1` 开始，国际示例从 `0` 开始 | **C** | ❌ |
| `bbox_2d` 量纲 | ⚠️ **未验证**：托管 API 规格说归一化 `0..1`，官方 SDK 文档说 `0..1000` | **C** | ❌ |

> **实现取舍（两项 C 级矛盾）**：
>
> - `layout_details` 的解析同时接受 `object[][]`（逐页）与扁平一维数组，`index` 只作透传、不参与任何计算，所以进制矛盾不影响结果。
> - `bbox_2d` 统一归一化到 `0..1`：**取该块所有坐标的最大值，若 > 1 则按 1000 除**，再夹紧到 `[0, 1]`。这个启发式对两种量纲都能得到正确结果，但仍需真机复核。
> - `response_path` 可配（默认 `md_results`），若真机响应结构不同，无需改代码。

### 2.4 护栏与计费

| 项 | 结论 | 级别 | 实测 |
| --- | --- | --- | --- |
| 图片大小上限 | 10 MB | B | ❌ |
| PDF 大小上限 | 50 MB | B | ❌ |
| 页数上限 | ⚠️ **未验证**：国内文档写 100 页，国际文档写 30 页 | **C** | ❌ |
| 计费 | $0.030 / 1M input tokens | B | ❌ |

> **实现取舍**：页数按 ticket §3 的要求**取小值 30** 作为默认护栏（`max_pages`），可配。本功能只发单帧图片，页数护栏实际只对 PDF 输入生效。
> 体积超限时**抛错而不是自动压缩**（沿用 spec 007 决策 10 的质量原则）：`_file_to_data_uri` 在超过 `max_file_mb` 时抛 `OcrError`，消息里明说「为避免精度损失这里不做自动压缩」。

### 2.5 错误响应形状

| 项 | 结论 | 级别 | 实测 |
| --- | --- | --- | --- |
| 包裹形态 | 两种都出现：`{"error": {"code": ..., "message": ...}}` 与平铺 `{"code": ..., "message": ...}` | B | ❌ |
| 解析顺序 | **先取 `error.code`，没有再取顶层 `code`** | B | ❌ |

已知错误码：

| code | 含义 | HTTP |
| --- | --- | --- |
| `1000` / `1001` / `1003` | 鉴权失败 | 401 |
| `1113` | 余额不足 | 429 |
| `1210` | API 参数非法（`file` 形态错误、模型不存在等） | — |
| `1211` | 模型不存在 | — |
| `1212` | 模型不支持该调用方式 | — |
| `1213` | 参数未收到 | — |
| `1214` | 参数取值非法 | — |
| `1301` | 内容敏感 | — |
| `500` | 上游内部错误 | 500 |

> ⚠️ **没有**「文件过大」或「格式不支持」的专用错误码。因此超限/格式错误只能落到 `1210`/`1214` 一类泛化参数错误里，实现**不按专用码分支**，而是把原始响应体整段记进日志与错误详情（截断到 2000 字符）。

## 3. 「未验证项 → 可配置字段」映射

> ⚠️ **本节已过时（2026-10-04 收敛）**。真机验证完成后，下面这张「未验证项 → 可配置字段」
> 的表被**整体撤销**：端点、鉴权头、字段名、响应路径全部实测确认，不再需要配置兜底，
> 而把七个底层字段暴露给用户的代价远大于收益。见 **§9 真机验证结果与配置面收敛**。
> 保留本节是为了记录「当初为什么做了通用抽象」以及它被什么事实推翻。

ticket 01 验收要求「每个未能验证的项都被显式标注，并且对应的值在实现里是可配的」。对应关系：

| 未验证项 | 配置字段 | 默认值 |
| --- | --- | --- |
| 端点路径 | `endpoint_path` | `/api/paas/v4/layout_parsing` |
| 基地址 | `base_url` | `https://open.bigmodel.cn` |
| 鉴权头形态 | `auth_scheme` | `"Bearer "`（清空即裸 key） |
| 请求体里文件字段名 | `file_field` | `file` |
| 其它可选请求字段 | `extra_params`（自由字典，先铺开再被必填项覆盖） | `{}` |
| 响应里 Markdown 的取值路径 | `response_path`（点分路径，数字段作列表下标） | `md_results` |
| 模型名 | `model_name` | `glm-ocr` |
| 超时 | `timeout` | `300` 秒 |
| 体积护栏 | `max_file_mb` | `10` |
| 页数护栏 | `max_pages` | `30` |

协议本身也可配：`protocol ∈ {"layout_parsing", "openai_chat"}`，见 §5。

## 4. 已实现但未经真机确认的调用方式

- **统一对外形态**：`OcrResult(markdown, blocks, raw, protocol, model_name)`；`blocks` 是归一化后的 `OcrBlock(label, content, bbox, page, index)`，`bbox` 一律 `0..1`。
- **`raw` 不落盘 base64**：`_slim_raw` 会剥掉 `layout_visualization` / `crop_images` 这类大字段并截断超长字符串（上限 20000 字符）。
- **不做自动压缩**：见 §2.4。
- **`test_connection()` 永不抛异常**：用 `make_test_image()` 现画的 900×340 PNG 打通一次调用，失败返回 `{ok: False, message, detail, code, status_code}`，`detail` 是上游原始响应体。测试图**只用 ASCII**（`ImageFont.load_default()` 无 CJK 字形，写中文会渲染成方框反而干扰排查）。

## 5. 备选路径（`protocol = "openai_chat"`）

glm-ocr **不在**智谱的对话模型枚举里，只能走专用端点；但「多模态视觉模型当 OCR 用」这条路真实存在，所以适配器两条都实现：

| 项 | 结论 | 级别 | 实测 |
| --- | --- | --- | --- |
| 硅基流动基地址 | `https://api.siliconflow.cn/v1` | A | ❌ |
| 硅基流动 OCR 模型 | `PaddlePaddle/PaddleOCR-VL-1.5`，**免费** | A | ❌ |
| 调用形态 | 标准 OpenAI 兼容 `/chat/completions` | A | ❌ |
| 必需的提示词前缀 | `"OCR:"`、`"Table Recognition:"`、`"Formula Recognition:"`、`"Chart Recognition:"`、`"Spotting:"`、`"Seal Recognition:"` 之一 | B | ❌ |
| `detail` 语义 | ⚠️ 与 OpenAI **相反**，此处 `"high"` 才是期望值 | B | ❌ |
| 智谱视觉模型 | 走 `/api/paas/v4/chat/completions`：`glm-4.6v`、`glm-4.5v`、`glm-4.6v-flash` | B | ❌ |
| 自建 | `zai-org/GLM-OCR` 权重可经 vLLM 暴露为 chat/completions，api_key 传 `"EMPTY"` | B | ❌ |

> **实现取舍**：`prompt` 是配置项（默认 `"OCR:"`），`image_detail` 走 `extra_params`（默认 `"high"`；置空串则完全不发 `detail` 字段，以适配语义相反的网关）。

## 6. 复现步骤（真机验证时执行）

1. 启动后端，打开 GUI → 设置 → **OCR 辅助**。
2. 填 `base_url` / `api_key` / `model_name`，协议选 `layout_parsing`。
3. 点「连接测试」。成功时返回 `{ok: true, protocol, model_name, ...}`；失败时页面会把上游**原始响应体**原样显示在 `<pre>` 里。
4. 用同一份响应核对 §2.3 的两个 C 级项：
   - `layout_details[0][0].index` 是 `0` 还是 `1`；
   - `layout_details[0][0].bbox_2d` 的坐标量级是 `0..1` 还是 `0..1000`。
5. 把实测结果回填到本文件，并把对应行的「实测」改为 ✅。

> **真机测试由用户本人执行**（用户明确要求：实现方只做功能实现与前端目视检查）。

## 7. 残余风险

1. **未认证调用 = 零实测**。上述所有 A 级结论仍有整体推翻的可能，尤其是响应体结构。
2. **两个 C 级矛盾**（`index` 进制、`bbox_2d` 量纲）已做兼容处理，但兼容是启发式的：若 `bbox_2d` 实际是 `0..1` 但某块坐标恰好等于 `1.0`，会被误判为千分制。当前用途只做展示与排障，不影响插图正确性。
3. **错误码表没有「文件过大 / 格式不支持」**，只能靠日志里的原始响应体定位。
4. `glm-ocr` 若改为经 `chat/completions` 暴露（自建 vLLM），必须把 `protocol` 切到 `openai_chat`，并注意 api_key 传 `"EMPTY"`。
5. **`label_visualization_mapping` 归并表未公布**：细粒度 label（`seal` / `header` / `footer` / `page_number` / `reference`）各自归并到 `text` 还是 `image` 查不到。若某一类被判进 `text`，就会带出非空 `content`。
6. **`formula` 的 `content` 具体格式无证据**：无法证实它一定是 LaTeX，也无法证实可以直接当引用块塞进文档 —— 官方文档未描述该字段的格式规范。因此分流只做「内容型 → 引用块」的搬运，**不做任何格式转换或渲染假设**。

## 8. `label` 语义对分流逻辑的影响（2026-02 补充核实）

spec 008 ticket 02 的分流判据是「OCR 结果里出现 `formula` / `table` → 不插图，把内容当引用块」。补充核实后的结论：

| 断言 | 结论 | 级别 |
| --- | --- | --- |
| `label == "image"` 恒无内容（`content: null`） | 成立 | **A** |
| 因此「出现 formula/table」与「这是张纯插图」**互斥** | 成立，分流逻辑本身可靠 | **A** |
| 反过来**不成立**：没有 formula/table ≠ 图里没有可用文字 | 成立 | **B** |
| 文字型截图（幻灯片、代码截图）会被识别成 `label: "text"` + 非空 `content` | 成立 | **B** |

**结论性影响**：只查 `formula`/`table` 会**漏判文字型截图** —— 那类图 OCR 读出了大段文字，却仍被当插图插进笔记，违背「保留高价值信息」的初衷（比如一整页立体几何题目截图）。

因此判据里补一个分支：**除 `image` 之外任何非空 `content` 都算「读出了内容」**，其中 `formula`/`table` 走公式引用块，`text` 走普通引用块。`image` 类永远视为「没有读出文字」，落回插图分支。

> 实现要点：判断有无内容必须写 `el.get("content")`，**不能写 `"content" in el`** —— 键始终存在，只有值是 `null`。
>
> 证据不足之处（仍标 C）：无法证实 `formula` 的 `content` 是 LaTeX；无法证实「按 label 分流后直接当引用块」在下游渲染层没有副作用。所以引用块一律**原文搬运**，不加 `$$` 包裹、不做公式渲染假设。

## 9. 真机验证结果与配置面收敛（2026-10-04）

**真机验证已完成**，上面 §0「零实测」的结论至此失效。本节是权威结论；前八节保留为
「验证之前我们是怎么想的」，冲突时以本节为准。

### 9.1 首次真机调用：401，根因不在代码

用户在设置页填入 Key 后，5 张截图全部返回：

```
POST https://open.bigmodel.cn/api/paas/v4/layout_parsing
HTTP 401 {"error":{"code":"401","message":"令牌已过期或验证不正确"}}
```

排查结论（决定性）：**智谱的 Key 是 `{id}.{secret}` 两段式**（32 位十六进制 id + `.` +
签名密钥），用户当时只复制到点之前那一段。证据三条：

1. Key 形态探针显示 `len=32 has_dot=False parts=1 hex32=True`；
2. 同一个 Key 打最简单的 `glm-4-flash` `chat/completions` 也是 401（带 `Bearer` 与裸 key 都一样）
   → 排除本项目请求构造的问题；
3. 官方 SDK 的 `generate_token` 会做 `id, secret = apikey.split(".")`，没有点根本拆不开
   （`ValueError: not enough values to unpack (expected 2, got 1)`）。

补全 Key（`len=49 parts=2`）后：`chat/completions` → **HTTP 200**，
`layout_parsing` → 400 `1214`（1×1 测试 PNG 太小），**鉴权已通过**。

> 设置页因此新增了一行提示，明说「中间那个点以及点之后的部分都不能少」——
> 这是真机上最容易踩、且报错信息完全指不到这一点的一个坑。

### 9.2 已确认的接口事实（用真实截图 173.5 KB 跑通）

用项目自己的 `OcrClient` 打真实截图，返回 `markdown=332 chars, blocks=4`：

| 项 | 实测结论 | 原级别 | 现级别 |
| --- | --- | --- | --- |
| 端点路径 | `{base_url}/api/paas/v4/layout_parsing` | A | **A（实测）** |
| 鉴权头 | `Authorization: Bearer <API_KEY>`，裸 key 也能通，按文档走 Bearer | B | **A（实测）** |
| 请求体 | `{model, file: <data URI>}`，**非 multipart** | A | **A（实测）** |
| 响应 | `md_results` 是扁平 markdown 字符串；`layout_details` 是 `object[][]` | B | **A（实测）** |
| `bbox_2d` 量纲 | **0–1 归一化**（响应 markdown 里的 `![...](page=0,bbox=[805,174,1177,517])` 是像素坐标，与归一化值一一对应） | C | **A（实测）** |
| `label == "image"` 的 `content` | **恒为空**（实测 `len=0`） | A | **A（实测）** |
| 图片在 `md_results` 里的形态 | `![](page=N,bbox=[x,y,x,y])`，**只有位置、没有 URL** | B | **A（实测）** |
| `formula.content` 的格式 | **是 LaTeX**（行内 `$ v_{0} $`、块级 `$$ ... $$`） | C | **A（实测）** |
| 单张图片 | **返回** `layout_details`，外层数组长度为 1 | A | **A（实测）** |
| `layout_details[].index` 进制 | 仍是 0/1 都可接受的透传项（实测值 0,1,2,3，`index` 不参与任何计算） | C | B |

实测的 4 个 block（真实几何题截图）：

```
label='text'     index=0 bbox=[0.113, 0.164, 0.787, 0.539] len=93
label='image'    index=1 bbox=[1.0, 1.0, 1.0, 1.0]         len=0   ← 印证「image 恒空」
label='text'     index=2 bbox=[1.0, 1.0, 1.0, 1.0]         len=151
label='formula'  index=3 bbox=[1.0, 1.0, 1.0, 1.0]         len=44
```

### 9.3 配置面从 11 个字段收敛到 7 个

用户明确要求：「OCR 辅助这里不要做通用，先专门写成智谱清言的」。

**被撤销的可配置字段**（连同 `protocol` 抽象一起删除，改为模块常量）：

| 原字段 | 去处 |
| --- | --- |
| `protocol` | 删除。只剩智谱一条路。 |
| `endpoint_path` | → 常量 `ENDPOINT_PATH = "/api/paas/v4/layout_parsing"` |
| `auth_scheme` | → 常量 `AUTH_SCHEME = "Bearer "` |
| `file_field` | → 常量 `FILE_FIELD = "file"` |
| `response_path` | → 常量 `RESPONSE_PATH = "md_results"` |
| `prompt` | 删除（那是 openai_chat 路径的概念） |
| `extra_params` | 删除 |

**保留可配的 7 个字段**：

| 字段 | 为什么保留 |
| --- | --- |
| `enabled` | 用户开关 |
| `base_url` | 国内站 `open.bigmodel.cn` / 国际站 `api.z.ai` / 自建网关**确实不同**，是唯一真正会因部署而变的项 |
| `api_key` | 用户凭据 |
| `model_name` | 上游改名时不必改代码 |
| `timeout` | 多页 PDF 要放宽（厂商 SDK 亦暴露 `GLMOCR_TIMEOUT`） |
| `max_file_mb` | 与上游体积限制相关的真实护栏 |
| `max_pages` | 与上游页数限制相关的真实护栏 |

**判决理由**：通用抽象的初衷是「上游一改就不至于打死功能」，但真机验证之后，
端点、鉴权、字段名、响应路径全部已实测确认，不再有不确定性需要靠配置兜；
而这些字段在设置页是**用户看不懂的**（「响应取值路径」这种问题不该让用户回答）。
代价大于收益，故收敛。

### 9.4 升级兼容：旧配置文件不会被判成损坏

`_normalize` 对旧文件里的 `protocol` / `endpoint_path` / `response_path` / `auth_scheme` /
`file_field` / `prompt` / `extra_params` **读时忽略、不报错、不迁移**；写入时不再落这些键
（`CONFIG_FIELDS` 是唯一真相）。

实测（构造一份完整的旧格式配置）：

```
1) 老文件可读，不报错 : ['api_key','base_url','enabled','max_file_mb','max_pages','model_name','timeout']
2) 用户字段保留       : https://api.siliconflow.cn/v1 | PaddlePaddle/PaddleOCR-VL-1.5 | timeout = 120
3) 协议残留被忽略     : []
4) 端点回到常量       : /api/paas/v4/layout_parsing | md_results
6) 写回后的磁盘键     : ['api_key','base_url','enabled','max_file_mb','max_pages','model_name','timeout']
7) 老键是否清除       : []
```

> ⚠️ **一个真实后果**：如果用户原先配的是 `openai_chat` + 硅基流动
> （`base_url = https://api.siliconflow.cn/v1`），升级后那套 key 会被拿去打智谱的
> `layout_parsing` 端点，必然失败。这是「只保留一条路」的**预期代价**：
> 配置不会坏，但需要用户改成智谱的 Key。失败信息会带上游原始响应体，
> 且 401/403 被标为**不可重试**（见 §9.5），所以不会白跑三轮。

### 9.5 真机暴露的三个代码缺陷（已修）

| # | 缺陷 | 修法 |
| --- | --- | --- |
| A | **认证失败被无意义重试**：401 会完整重试三轮，每轮都要重新抽帧与两次 LLM 调用。 | `OcrError` 新增 `non_retryable` 属性，由 `_NON_RETRYABLE_STATUS = (401, 403, 413)` 与 `_NON_RETRYABLE_CODES`（含 `1000/1001/1003/1005/1113/1210~1214/1301`）判定；接上 `note.py` 里已有的 `self.last_error_non_retryable`，`routers/note.py` 据此提前终止。**500/502/504/429 保持可重试**。 |
| B | **`OcrConfigManager` 相对路径依赖 CWD**：从仓库根启动时静默读成空配置，却报「未配置 OCR 服务地址」。 | `__init__` 里把相对路径解析成 `Path(__file__).resolve().parents[2] / <relative>`，变成绝对路径。 |
| C | **`generate_screenshot` 的 ffmpeg 无 timeout**：跑在 `ThreadPoolExecutor.map` 里，卡住会让整个任务永久阻塞且无日志。 | 新增 `_FFMPEG_TIMEOUT_SECONDS = 60`，`subprocess.run` 包 `try/except subprocess.TimeoutExpired`，超时记 error 并 `return ""`，走上层已有的失败分支。 |

### 9.6 本节之后仍然未知的事项（残余风险，收窄后）

1. **`label_visualization_mapping` 归并表仍未公布**：细粒度 label（`seal` / `header` /
   `footer` / `page_number` / `reference`）各自归并到 `text` 还是 `image` 查不到。
2. **`bbox` 的启发式兜底仍在**：`_normalize_bbox` 保留了「最大值 > 1 则除以 1000」的分支，
   以防某个自建网关返回千分制。真机确认托管 API 是 0–1。
3. **错误码表没有「文件过大 / 格式不支持」专用码**：仍靠日志与错误详情里的原始响应体定位。
4. **页数上限仍然取保守值 30**：真机未验证 PDF 场景（本功能只发单帧图片）。
5. **国际站（`api.z.ai`）未实测**：只验证了国内站。`base_url` 可配，但换站后的行为未经确认。
