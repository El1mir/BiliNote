# 007 来源输入 Module：单视频、批量 URL 与 Bilibili adapter

- 类型：架构决策
- 状态：designed
- 依赖：001-capability-inventory-and-information-architecture（输入能力已列入保留边界）
- 协同：002-task-read-model-and-update-transport（提交后返回任务组；本 ticket 不重复定义任务状态）
- 阻塞：前端工作区数据层、Bilibili 生成链路收敛、非 Bilibili adapter 删除、批量导入回归测试
- 设计范围：定义输入识别、规范化、展开和提交前预览；不实现下载器、生成流水线或任务读取模型。

## 1. 目标与删除测试

当前 URL parser 同时包含平台分支、Bilibili 短链解析、合集/系列识别和多 P 解析；validator 既承担平台判断又承担请求校验；note router 暴露 /expand、/generate_note、/generate_notes 多个入口；BatchImportDialog 还自行提取 P 号和估算成本。页面因此拥有了本应属于来源领域的规则。

目标是建立一个 Source Intake 深 module：给它单个或多个用户输入，返回有顺序、可去重、可展示、可提交的标准化输入项。页面只处理文本输入、预览结果和用户确认，不拥有 URL 正则、短链重定向、合集展开、P 号解析或成本估算。

删除测试：删除前端 extractPFromUrl、estimateBatchCost 和平台分支后，输入预览与提交仍然可用；删除旧 /expand 拼装逻辑后，旧 command adapter 仍能从标准化输入项生成任务。否则不迁移表单。

## 2. 领域边界

### 2.1 Source Intake 负责

- 接收 single 或 batch 模式的原始 URL 行，去除首尾空白并丢弃空行。
- 识别来源 adapter、输入类型和可继续处理的状态。当前唯一可执行 adapter 是 bilibili。
- 规范化 Bilibili 视频 URL，解析 b23.tv 短链、BV 号、分 P、合集/系列链接。
- 将合集/系列展开成有序 canonical items，并保留来源父项、原始 URL 与展示标题。
- 按 canonical key 去重，保留第一次出现的位置并返回重复项的可解释状态。
- 返回数量、预计时长/体积等 adapter 能提供的预览信息；无法估算时返回 null，不在前端猜测。
- 返回稳定错误 code、可翻译 messageKey 和安全 detail，供中文/英文界面使用。

### 2.2 Source Intake 不负责

- 下载、字幕/ASR、采样、OCR、LLM、导出、聊天或任务进度。
- 校验 LLM/转写器/下载器配置；这些属于设置或生成 command。
- 直接暴露非 Bilibili downloader，也不通过通用 yt-dlp fallback 偷渡非 Bilibili 生成。
- 页面文案、成本公式、进度展示和移动端交互。

## 3. 统一识别模型

### 3.1 请求

IntakeResolveRequest：

- mode：single 或 batch。single 只接受一个逻辑输入；batch 接受多行 URL。
- inputs：[{ rawUrl: string; clientIndex: number }]；服务端保留 clientIndex 以稳定排序和定位错误。
- options：{ expandCollections: boolean; includeParts: boolean }，默认开启；选项不能改变 adapter 的安全上限。
- contractVersion：请求方支持的主版本，首版为 1。

前端可以在本地做换行和空白切分，但不得在本地判断来源或解析 URL。空输入直接得到 empty_input，不发送无意义的网络请求。

### 3.2 响应

IntakeResolveEnvelope：

- schemaVersion：首版为 1。
- requestId：用于诊断，不作为业务主键。
- source：当前响应的 adapter 名称或 unknown。
- summary：inputCount、readyCount、invalidCount、duplicateCount、expandedCount、limits。
- items：按 clientIndex 和 adapter 展开顺序返回的 IntakeItem 数组。

IntakeItem：

- itemId：本次预览内稳定的临时 id；提交时不得作为 taskId 使用。
- clientIndex：原始输入行序号。
- rawUrl：用户原始输入，仅用于回显和诊断。
- canonicalUrl：可提交的规范 URL；不可用时为 null。
- source：bilibili 或 unknown；未来 adapter 只新增 source，不改变 item 形状。
- kind：video、part、collection、series、unsupported 或 invalid。
- sourceId：Bilibili 的 bvid、collection id 或 series id；未知时为 null。
- parentItemId：由合集/系列展开的项指向父输入项；单视频为 null。
- part：P 号或 null；同一 bvid 的不同 P 号拥有不同 canonical key。
- title、durationSec、sizeMb：可获取时返回，否则为 null。
- state：ready、duplicate、invalid、unsupported、unavailable、limit_exceeded。
- error：{ code: string; messageKey: string; params: safe object } 或 null。

canonical key 固定为 source + sourceId + part；没有 sourceId 时不得用原始 URL 猜测去重。服务端返回 duplicateOf 指向第一项，页面不能把重复项误显示为新的生成任务。

## 4. Adapter interface 与 Bilibili 范围

后端以 Python Protocol 或等价 interface 约束 adapter：

- source_name：稳定字符串，例如 bilibili。
- recognize(raw_url) -> Recognition：只判断是否属于该来源及输入 kind，不触发下载。
- normalize(raw_url, context) -> NormalizedSource：处理 canonical URL、sourceId、part 和安全重定向。
- expand(normalized, limits) -> list[CanonicalItem]：对合集/系列展开，保留顺序和父项关系。
- preview(items, context) -> PreviewMetadata：只读取可安全展示的元数据，不进入生成流水线。

Bilibili adapter 必须覆盖当前已存在的输入形状：

- <www.bilibili.com/video/BV>... 与带 query 的视频 URL。
- b23.tv 短链；解析失败返回 short_url_unresolved，不静默使用短链作为可提交 canonical URL。
- ?p=N 与 /pN 多 P 形式；非法或超出范围返回 part_invalid。
- space.bilibili.com/{mid}/lists/{sid}?type=season 或 series。
- /channel/collectiondetail?sid= 与 /channel/seriesdetail?sid=。
- 合集/系列展开失败返回 collection_unavailable，不返回半截 ready 列表，除非响应明确标出 partial=true 并由用户确认。

展开限制由服务端 capability 返回并执行：maxInputUrls、maxExpandedItems、maxResolveConcurrency、resolveTimeoutMs。现有前端 BATCH_CONFIRM_THRESHOLD=200 只能迁移为确认提示，不得成为唯一安全边界；最终数值在性能基线和部署配置中锁定。

## 5. 稳定错误模型

错误 code 至少包括：empty_input、invalid_url、unsupported_source、short_url_unresolved、collection_unavailable、collection_limit_exceeded、duplicate_item、part_invalid、resolve_timeout、adapter_unavailable、auth_required。

每个错误必须包含 messageKey 和安全 params；不得包含 cookie、请求头、服务器绝对路径、供应商堆栈或完整远端响应。网络超时、来源不支持和用户输入错误必须能被前端区分，不能统一成“解析失败”。

## 6. 端到端流程与旧接口 adapter

1. 前端输入框只做换行切分、空白清理和重复行提示。
2. 调用 POST /api/v1/intake/resolve，拿到完整预览；resolve 不创建任务、不写任务历史。
3. 用户确认 ready 项；重复、invalid、unsupported、unavailable 项默认不提交，但可在预览中查看原因。
4. 调用 POST /api/v1/tasks，提交 canonical items 与生成选项；任务组和状态读取由 ticket 002 负责。
5. 迁移期间，旧 /expand、/generate_note、/generate_notes 作为薄 adapter：先调用 Source Intake，再转换为旧 command 需要的请求形状。
6. 新页面禁止同时调用旧解析 helper 和新 intake endpoint；切换完成后删除旧 helper、平台分支和旧 adapter。

## 7. 非 Bilibili 移除边界

- 删除前端平台选择和 YouTube、Douyin、Kuaishou 的生成入口。
- 删除 backend/app/utils/url_parser.py 中非 Bilibili 的 extract 分支，但保留 source-neutral 的 request/interface 形状。
- validator 对非 Bilibili 输入返回 unsupported_source，而不是尝试匹配后进入下载器。
- 删除或隔离非 Bilibili downloader 的生成引用；文件清理在实现 ticket 中以调用图和测试结果为准，不凭文件名盲删。
- 扩展端不在本网页重构中改 UI；若仍调用旧接口，必须由旧 adapter 维持 Bilibili 行为。

## 8. 实现顺序

1. 以现有 backend/app/utils/url_parser.py、backend/app/validators/video_url_validator.py、note.py 和 BatchImportDialog.tsx 建立输入 fixture，覆盖现有 Bilibili URL 形状。
2. 定义 Python/TypeScript schema 与 adapter contract，先让旧 helper 通过 Bilibili adapter 运行，保持行为对照。
3. 实现 resolve endpoint、限制与错误模型；前端预览切换到 contract，移除本地 P 号和成本估算。
4. 将单视频/批量生成 command 接到 canonical items；保留旧 endpoint adapter 作为迁移护栏。
5. 执行非 Bilibili 调用图清理与回归；确认没有页面或生成 command 继续依赖已移除 adapter。
6. 在 ticket 002 的任务读取模型和 ticket 006 的迁移门禁通过后，删除旧解析和旧 endpoint adapter。

## 9. 测试与验收

### 后端

- 单视频：BV URL、query、b23.tv、规范化、非法输入、unsupported source。
- 分 P：?p=N、/pN、重复 P、非法 P、canonical key。
- 合集/系列：四种当前 URL 形状、顺序、父子关系、空结果、超限、超时和部分失败。
- 批量：空行、重复行、跨输入重复、稳定 clientIndex、输入上限和展开上限。
- 安全：不泄漏 cookie、绝对路径、堆栈；不触发非 Bilibili downloader。
- 兼容：旧 /expand、/generate_note、/generate_notes 经 adapter 输出相同的 Bilibili command 语义。

### 前端

- BatchImportDialog 不再解析 P 号、估算成本或判断平台；只渲染 IntakeResolveEnvelope。
- preview 到 submit 只提交 state=ready 且去重后的 canonical items。
- 中文/英文 messageKey 映射完整；长错误和批量数量在手机/平板/桌面不溢出。
- 网络超时、unsupported、limit_exceeded 与业务失败显示不同状态，重试不会重复创建任务。

### 验收

- 页面代码不再包含来源正则、Bilibili P 号解析和成本公式。
- Bilibili 单视频、短链、分 P、合集/系列和批量 URL 均能生成相同 canonical item 形状。
- 非 Bilibili 输入明确显示 unsupported_source，不进入生成链路。
- 同一 canonical key 在一个提交中只创建一个任务项，原始顺序和父子关系可追溯。
- resolve 只负责预览，不创建任务；submit 只接受已确认的 canonical items。

## 10. 未决问题

- ticket 003 基线后锁定输入上限、展开上限、并发度和超时默认值。
- ticket 006 决定旧 /expand 与旧单/批生成 endpoint 的最终下线日期。
- 若合集需要登录 cookie，确定 auth_required 的设置引导和扩展端兼容方式。
