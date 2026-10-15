# Changelog

本项目所有重要变更记录于此。格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [Unreleased]

### Changed

- **笔记风格预设改为「场景 × 详略」两个正交维度（spec 015，⚠️ 破坏性变更）**：原先把两个独立维度压平成 9 个互斥预设（`minimal` / `detailed` / `academic` / `xiaohongshu` / `life_journal` / `task_oriented` / `business` / `meeting_minutes` / `tutorial`），其中 `business` 与 `meeting_minutes` 除标号外逐字相同、`xiaohongshu` 一段就占了全部风格提示词体积的 12 倍、`tutorial` 的段号还与「目录」片段的编号撞号（都叫 `9.`）。现在请求字段 `style` 拆成 **`scene`**（`life` / `academic` / `professional`）与 **`detail`**（`brief` / `detailed`），两轴提示词可自由组合；提示词片段本身不再带编号。
  - **破坏性变更**：`style` 被直接移除，**不做旧值映射** —— 存量历史 payload 里的 `style` 在重试或重启恢复时会静默拿不到场景与详略指令（笔记仍能生成，只是少了这两条约束）。前端与浏览器扩展的常量、表单、展示随之改造（spec 015 ticket 02 / 03）。
  - **主提示词 `BASE_PROMPT` 一并重写（spec 015 ticket 04）**：原先它写死了「用户宁可笔记长一些，也不要漏掉内容」「**不要**以『精简』为由删掉知识点」—— 与新增的「篇幅：精简」**直接对立**，同一份提示词里两句话互相拉扯。现在改成「默认完整；任务里指定了篇幅就以任务为准」，并把「精简」明确定义为**压缩表达**（「不再逐段展开，不是删内容」），两条规则才可能共存。六条写作原则逐条重过：补上原本缺失的**标题层级约定**（`## ` / `### `，此前只有勾选目录或原片跳转时才被间接提到）、把 6 行编号转义说明压成 1 行、把两句重复的逃逸口改成一条明确的优先级规则。
  - **所有「按勾选追加」的片段去掉行首编号**：format 四项、OCR 截图分支、以及历史 provider 用的 `LINK` / `SCREENSHOT`。这些片段一次只追加一条，编号**无法保证连续**（没勾目录时就会从 8. 直接跳到 9.），孤立数字只消耗注意力。编号此后只留给 `BASE_PROMPT` 里那六条恒定原则。
- **后端任务状态与只读端点缓存优化（spec 014）**：三条高频路径不再重复做同步系统调用。端到端实测（N=200，`cd backend && .venv\Scripts\python.exe tests\014-backend-cache-optimization\baseline_measure.py --tasks 200 --repeat 5 --cache both`）：

  | 端点 | stat 前 → 后 | p50 前 → 后 |
  |---|---|---|
  | `POST /api/task_status/batch`（200 条/轮） | 1260.8 → **12.4** | 166.97ms → **5.52ms**（30.25×） |
  | `GET /task_list`（整表） | 1970.6 → **908.6** | 162.27ms → **78.80ms**（2.06×） |
  | `GET /transcriber_models_status` | 82.4 → **7.0** | 6.88ms → **1.32ms**（5.21×） |

  - **任务状态改为内存权威**：批量轮询此前对每个任务做一次同步 `os.path.exists` + `open` + `json.load`（N=200 时约 198ms/轮、899 stat/轮，且**与任务是否在动无关** —— 终态文件内容不变却每轮重读）。新增进程内注册表 `backend/app/services/task_status_cache.py`，读状态先查字典、未命中才回落到 `<task_id>.status.json`；状态文件降级为**投影**，职责收敛为「重启后把权威读回来」，spec 009 的重启恢复不受影响。后端是单进程 uvicorn（`backend/main.py:137` `reload=False`），进程内缓存天然一致，不需要跨进程失效协议。
  - **`/task_list` 合并同文件两次读**：`_task_title_from_file` 与 `_task_has_note` 读的是同一个结果文件、做同一遍解析，现合并为一次读取（每行文件读 112.68ms → 60.67ms）；解析改用仓库里早已写进 `requirements.txt`、却从未被任何代码调用的 `orjson`（单独 159.88ms → 54.49ms，2.93×）。该端点**不加缓存**，「入队即落库、新建任务立刻可见」的既有承诺不变。
  - **`transcriber_models_status` 目录扫描加 5s TTL**：此前每次请求都对每个可见模型重扫一次模型目录（HF 布局还要 `iterdir()`）。只缓存扫描结果，**不**缓存下载状态（那是进程内内存态、直读零成本）；下载流程收尾时主动失效，让新落盘的模型立刻可见。`/sys_health`、`/deploy_status`、`/transcriber_config` 经核对**刻意不改**：`/sys_health` 的 5s 轮询只在 Tauri 挂（浏览器探活走不查任何外部依赖的 `/sys_check` 且就绪即停），`/deploy_status` 仅在监控页打开时 30s 一次，`/transcriber_config` 切页一次 —— 收益接近 0。
  - **删除 / 重试的失效挂载点**：删除收敛到 `task_cleanup.delete_task_completely` 一处，且**先删投影文件、后删内存**（反过来的话，中间任何一次轮询都会把已删除的任务状态从文件里读回来重新缓存，表现为「删了又冒出来」）；重试用「覆盖」而不是「清空」，避免「内存已清、磁盘仍是旧值」的同款窗口。
  - **零新增依赖**：未引入 `cachetools` / `redis` / `celery` —— 本项目的部署形态是 PyInstaller 单文件 + Docker + Tauri 三者并存，`cachetools` 技术上可加但净收益≈0（它给 LRU/TTL 容器，而这里要的是「按 task_id 存 dict + 写方推失效」，用了仍要自己写失效钩子）。`git diff backend/requirements.txt` 为空。
  - 新增 `BILINOTE_CACHE=off` 开关（默认开启），用于在同一次运行内做前后对比。

### Fixed

- **并发写任务状态时，读者可能读到半截 JSON**：`NoteGenerator._update_status` 在 `os.replace` 失败时会降级为**原地覆盖** —— 先截断再写。Windows 下目标文件被别的线程打开时 `os.replace` 会抛 `WinError 5 (ACCESS_DENIED)`（截图阶段有 8 个 `screenshot_*` 线程写同一个 task_id），于是这条「兜底」路径反而成了唯一会产生半截文件的路径：实测并发读 121 次拿到空文件或截断 JSON。现改为 `os.replace` 重试（5 次 × 10ms），并**删掉原地覆盖兜底** —— 失败时让磁盘投影停在上一次的完整值（内存才是权威，且本函数有约 35 个调用点，下一次状态更新马上会重试落盘）。「不写」的代价是投影短暂偏旧，「乱写」的代价是读者拿到垃圾。同一用例重跑：半截读 121 → **0**。
- **`/task_list` 遇到非字典形态的结果 JSON 会让整个接口 500**：旧的 `_task_title_from_file` 在 `try` 之外访问 `result.get("audio_meta")`，非 dict 的结果会抛 `AttributeError`，被外层 `except` 捕获成 `R.error(..., code=500)`，任务列表整体不可用。现退化为「无标题、无笔记标记」。

### Internal

- 新增 `specs/014-backend-cache-optimization/`（spec + 6 张实现工单，状态 `implemented`）与 `backend/tests/014-backend-cache-optimization/`（98 用例 + 基线/对比测量脚本与结果 JSON）。
- 新增 `backend/tests/014-backend-cache-optimization/conftest.py` —— 仓库第一份 pytest 测试基建（此前无 `conftest.py` / `pytest.ini` / `pyproject.toml`）。
- 新增 `backend/pyrightconfig.json`：`pyright` 与 LSP 此前都无法发现 `backend/.venv`（会落到系统 Python 的 site-packages），导致任何 `import pytest` 的测试文件误报 `reportMissingImports`。
- `GLOSSARY.md` 补两组概念：**权威 / 投影**（任务状态的两份来源地位不平等）与**缓存槽 / 陈旧窗口**（槽丢了只是慢一次，权威丢了才是丢数据）。
- 全量后端回归 **777 passed**（历史基线 653，无退化）；pyright 与 ruff 对本次改动零新增问题。
- 新增 `specs/015-note-preset-scene-and-detail/`（spec + 4 张实现工单）与 `backend/tests/015-note-preset-scene-and-detail/`（后端 40 用例，含一份把前端 / 扩展 / 后端三处词表钉在一起的同步测试，以及一份用 `string.Formatter` 钉住 `BASE_PROMPT` 占位符集合的契约测试；前端 `BillNote_frontend/tests/015-note-preset-scene-and-detail/` 另有一份词表测试）。全量后端回归 **817 passed**（历史基线 777）。
- `GLOSSARY.md` 再补一组概念：**场景 / 详略**（笔记呈现方式的两个正交维度，组合数相乘而非相加）。

## [2.4.4] - 2026-06-23

### Security

- **升级 Starlette 0.46.1 → 0.47.2 修复 CVE-2025-54121**（[GHSA-2c2j-9gv5-cj73](https://github.com/advisories/GHSA-2c2j-9gv5-cj73)，#411）：旧版在解析 multipart 表单中的大文件时，`SpooledTemporaryFile` 从内存溢写到磁盘的 rollover 在事件循环线程内**同步执行**，攻击者可借大文件上传阻塞事件循环造成拒绝服务（DoS）。新版把该写入移到线程池。FastAPI 同步升级 0.115.12 → 0.116.2（其 starlette 约束由 `<0.47.0` 放宽，以容纳修复版本），与现有 pydantic / anyio / python-multipart 均兼容。

## [2.4.3] - 2026-06-23

### Fixed

- **Whisper `large-v3-turbo` 模型无法下载**（#402）：内置映射指向的 `Systran/faster-whisper-large-v3-turbo` 仓库已从 HuggingFace 下架（返回 401/404），点击下载会静默失败、状态一直显示「未下载」。改用社区维护的 CT2 转换版 `deepdml/faster-whisper-large-v3-turbo-ct2`（直链可达、含 `model.bin`，与 faster-whisper 的 `large-v3-turbo` 等价）。
- **模型下载失败时前端无任何提示**（#402 衍生）：`/transcriber_models_status` 此前只回传 `downloading`/`downloaded`，后台下载失败状态被丢弃。现新增 `model_download_state` 统一维护下载状态与失败原因，状态接口新增 `failed` 字段并透传 `error`；前端模型列表展示「下载失败」徽标 + 错误详情，按钮变为「重试」，并对新出现的失败弹出提示。

## [2.4.2] - 2026-06-17

### Fixed

- **Docker 部署打开显示 nginx 欢迎页**：`nginx/default.conf` 被 docker-compose（多容器）与 `Dockerfile.complete`（单镜像）共用，但两种模式对 `location /` 的需求相反（多容器需反代独立的 frontend 容器，单镜像需直接服务本地静态文件），导致其中一种部署方式总会回退到 nginx 默认欢迎页。现拆分为两份配置：`nginx/default.conf`（compose，反代 frontend 容器）与新增的 `nginx/standalone.conf`（单镜像，静态前端 + 本地 backend 代理）；`Dockerfile.complete` 改用后者并删除 Debian 默认站点，两种部署方式均恢复正常。

## [2.4.1] - 2026-06-17

### Added

- **YouTube Shorts 链接支持**：后端 URL 校验与 video id 提取支持 `youtube.com/shorts/<id>` 形态，Shorts 链接可正常提交生成笔记（#381）。

### Fixed

- **B 站 412（wbi/playurl 风控）**：B 站 `x/player/wbi/playurl` 网关新增 `dm_img_list`/`dm_img_str`/`dm_cover_img_str`/`dm_img_inter` + `web_location` 风控校验，缺失即返回 HTTP 412。多数视频网页内嵌 playinfo、yt-dlp 不调此 API；而网页不内嵌 playinfo、必须走 API 的视频（如 BV1X9L16oEgB）会撞上风控，刷新 cookie 无效、yt-dlp（含最新版）上游尚未适配。现于 wbi 签名前注入哑值 dm_img 风控参数（形态对齐 yt-dlp 自身 arc/search 用法）恢复 200（#410）。
- **B 站分 P 视频字幕取错集**：分 P 视频提交 `?p=N` 时，字幕优先链路未透传 p 参数，始终取第 1 集 cid，导致笔记内容与实际下载的 p=N 音频不一致。现从 `data.pages[N-1]` 取对应分 P 的 cid（#409）。

## [2.4.0] - 2026-06-07

### Added

- **可配置 Whisper 模型**：转写设置支持自定义 Whisper 模型与名称映射，可指定自定义 HuggingFace repo 或本地路径（新增 `backend/app/transcriber/whisper_models.py` + 测试），转写设置页可选择 / 配置模型。
- **关注公众号获取交流群**：关于页群二维码改为公众号二维码，关注公众号后回复「交流群」即可获取最新群二维码，避免群码过期失效。

### Fixed

- **浏览器扩展**：修复标题显示异常，优化脑图（Markmap）导出。

### Docs

- **GPU/CUDA 部署**：README 补全 GPU/CUDA 部署说明。

## [2.3.4] - 2026-05-27

### Added

- **一对一搭建服务二维码**：新增「BiliNote AI 笔记系统一对一搭建服务」二维码（README + 关于页），扫码加微信、备注「搭建服务」即可咨询。

## [2.3.3] - 2026-05-22

### Fixed

- **预构建 Docker 镜像数据持久化**：文档的 `docker run` 只挂了 `data/`（媒体缓存），而 SQLite 数据库（LLM 供应商配置 + 笔记历史）和笔记文件不在该卷下，导致删除 / 升级容器时丢失配置与历史。现将数据库重定向到 `/app/backend/data/bili_note.db`、笔记到 `data/note_results`（随 data 卷持久化）；README 更新为挂载 `data` / `config` / `static` / `models` 四个数据卷，并提示**勿**挂整个 `/app/backend`（命名卷会固化镜像内代码，导致 `docker pull` 升级不生效）。`docker-compose` 路径本就正确（`./backend:/app` 整目录绑挂），未受影响。

## [2.3.2] - 2026-05-22

### Fixed

- **后端启动崩溃（Docker）**：`python:3.11-slim` 基础镜像升级到 Debian 13 / glibc 2.41 后，`ctranslate2` 4.5.0 预编译库带「可执行栈」标记被 glibc 拒绝加载（`cannot enable executable stack ... Invalid argument`）。由于 `from faster_whisper import WhisperModel` 在顶层 import，import 失败直接拖垮整个后端启动 → 容器反复重启。升级 `ctranslate2` 4.5.0→4.6.0（wheel 加入 `noexecstack` 链接标志，从二进制层根治）
- **whisper 模型误报「离线模式找不到模型」**：下载（modelscope 自定义目录）与加载（faster-whisper HF cache）布局不一致导致命不中缓存。统一为下载 / 加载 / 完整性检测 / 损坏自愈都走 HF cache 布局，并向后兼容老 modelscope 目录
- **桌面端构建产物版本恒为 2.0.0**：Release 工作流在 `pnpm tauri build` 前从 git tag 注入版本号到 `tauri.conf.json`，使产物版本与 Release 版本对齐

## [2.3.1] - 2026-05-22

### Changed

- **更新微信交流群二维码**：旧二维码即将失效，替换 README 中 5 个交流群（群 1-5）的入群二维码。

## [2.3.0] - 2026-05-14

主线：一波部署与运行时韧性专项——Docker / 桌面端 / 在线引擎三端的"装不上、起不来、跑一半挂"问题集中清理，并新增全局代理与转写模型就绪门禁。

### Added

- **全局代理**：新增 `ProxyConfigManager`（`config/proxy.json` 持久化 + `HTTP_PROXY`/`HTTPS_PROXY`/`ALL_PROXY` 环境变量兜底）。一处配置同时作用于 LLM API、转写 API（Groq 等）、yt-dlp 视频下载、youtube-transcript-api 字幕拉取。前端「设置 → 下载配置」页新增代理卡片，会显示当前实际生效值（含 env 兜底来源提示）
- **转写模型就绪门禁**：`/generate_note` 在排队前检查本地转写引擎（fast-whisper / mlx-whisper）的模型是否已下载完整，未就绪直接拦截并返回 `reason=transcriber_model_not_ready`，不再让任务静默卡在首次大文件下载；前端引导用户去「音频转写配置」页下载
- **桌面端后端健康监控韧性**：Tauri 侧 spawn sidecar 后以 HTTP 探针轮询 `/api/sys_check` 判就绪并 emit `backend-ready`；`RunEvent::Exit` 钩子在 app 退出前 kill sidecar，杜绝孤儿进程占用 8483 端口；启动失败对话框展示原因 + 最近 stderr + 一键重启 / 复制日志
- `/sys_health` 重构为结构化健康响应 `{backend, ffmpeg, db, whisper_model}`；部署监控页显示 Whisper 模型本地下载状态
- 所有 Dockerfile 新增 `BASE_REGISTRY` build-arg，国内拉不到 docker.io 时可换 daocloud 等镜像源

### Fixed

- **whisper 模型损坏自愈**：`model.bin` 截断 / 损坏导致 `Unable to open file 'model.bin'` 死循环——加载失败时删除损坏目录、重新下载、重试一次；mlx-whisper 同样按 `config.json` 判定完整性
- **空 API Key 天书报错**：空 key 会让 httpx 拼出非法 header `Bearer ` 并抛 `LocalProtocolError: Illegal header value b'Bearer '`。新增 `build_openai_client` 在入口校验，给出「xxx 的 API Key 未配置」的清晰提示
- **新模型 temperature 不兼容**：OpenAI o1 / o3 / gpt-5 系列拒绝自定义 `temperature`，命中后就地去掉该参数重试，不消耗重试预算
- **桌面端「后端加载中」死循环**：`useCheckBackend` 重写——60s 总超时取代 `while(true)` 无限轮询，订阅 Tauri `backend-ready` / `backend-terminated` / `backend-startup-timeout` 事件；裸 `fetch` 探测避免启动期 toast 叠堆
- **CORS 漏配桌面端 origin**：补全 `tauri://localhost` / `https://tauri.localhost`，修桌面端 fetch 拿到 200 却被浏览器 CORS 拒绝读响应（表现为"连不上后端"但后端日志全 200）
- `/api/api/sys_health` 双 `/api` 前缀导致健康检查 404
- `docker-compose` 的 `restart: on-failure:3` 改为 `unless-stopped`，避免短暂崩溃后容器被永久打死；GPU compose 补齐 `healthcheck` / `restart` / `mem_limit`
- `Dockerfile.complete` 的 supervisord 用 `%(ENV_*)s` 透传环境变量给 backend 子进程（此前只白名单 2 个，`docker run -e` 配的变量后端看不到）
- `.env.example`：修正 `VITE_API_BASE_URL` 端口（8000→8483）、`WHISPER_MODEL_SIZE`（medium→tiny，首次启动不被 ~1.5GB 下载卡住）
- Onboarding：第 1 步后端连通检测改为自动重试 + Tauri 事件触发 + 手动重检按钮；第 2 步撞预置供应商名时改为更新已存在供应商而非报错
- 模型供应商列表卡片整行可点击切换（此前仅 icon 区域响应）
- `connect_test` 改用真实 chat completion 探测而非 `/v1/models`（后者在 key 无 inference 权限 / 供应商不实现该端点时会误判）

### Internal

- `backend/main.py` lifespan 拆为 `[startup 1/5]…[startup 5/5]` 分段日志，启动期异常可一眼定位死在哪一步
- `request.ts` 新增 `suppressToast` 配置位，预期内的失败（如 onboarding 撞名重试）不弹全局红 toast
- `CLAUDE.md` 勘误：移除不存在的 `app/messaging/` / `app/i18n/` / `worker_registry.py` 描述，修正 `events/` 路径，补 `pytest` / 前端 `typecheck` 命令

## [2.2.3] - 2026-05-09

### Fixed

- 前端 vite build 在 Docker / Tauri CI 中失败：`Rollup failed to resolve import '@tauri-apps/api/event'`。v2.2.0 加的 P1/P2 桌面端组件用了 `await import('@tauri-apps/api/event')` 与 `'@tauri-apps/api/core'`，但 `@tauri-apps/api` 只是 `@tauri-apps/plugin-shell` 的间接依赖，没在 `BillNote_frontend/package.json` 直接声明，Rollup 在 production build 时静态分析报"无法解析"
  - `BillNote_frontend/package.json`：把 `@tauri-apps/api` 加为直接依赖（`^2.10.1`，与 lockfile 中已有的 transitive 版本一致）
  - 本地 `DOCKER_BUILD=1 pnpm run build` 复现 + 验证修复

## [2.2.2] - 2026-05-09

补 v2.2.1 漏掉的 Tauri 桌面端 build 修复。

### Fixed

- 桌面端 Tauri 构建失败：v2.2.1 的 hotfix 只修了 Docker 镜像构建里的 pnpm 版本，`main.yml` 的 `pnpm/action-setup@v4 with: version: 'latest'` 没改，于是桌面端 build 仍然在 `Install frontend dependencies` 步报 `ERR_UNKNOWN_BUILTIN_MODULE: No such built-in module: node:sqlite`（pnpm 11 要求 Node 22+，但 main.yml 用的 node 20）。pin 到 `9.15.0`，与 Docker 侧一致。

## [2.2.1] - 2026-05-09

补 v2.2.0 ghcr.io 镜像构建失败。

### Fixed

- Docker 镜像构建失败：`v2.2.0` tag 触发的 ghcr.io 推送在 frontend-builder 第 5/7 步 `pnpm install --frozen-lockfile` 报 `ERR_UNKNOWN_BUILTIN_MODULE`。根因：`corepack prepare pnpm@latest` 拉到了 pnpm 11.0.9，而 pnpm 11 要求 Node 22+，跟我们的 `node:20-alpine` 不兼容。
  - `Dockerfile.complete` 与 `BillNote_frontend/Dockerfile` 的 pnpm 版本 pin 到 `9.15.0`（lockfile 由 pnpm 9 生成，匹配 Node 20）

## [2.2.0] - 2026-05-09

主线：浏览器插件功能与 web 端 NoteForm 完整对齐；桌面客户端 UX 与错误恢复一波重炼。

### Added — 浏览器插件

- 笔记选项与 web 端 NoteForm 完整对齐：
  - `style` 由自由文本改成 9 个预设下拉（minimal / detailed / academic / tutorial / xiaohongshu / life_journal / task_oriented / business / meeting_minutes），与 backend `prompt_builder.note_styles` 严格匹配（之前自由文本不命中 enum 等于没传——隐性 bug）
  - `format` 完整 4 个 checkbox（toc / link / screenshot / summary，原来只有 screenshot/link）
  - `extras` 文本框：拼接到 prompt 末尾的 ad-hoc 提示
- 多模态视频理解：`video_understanding` 开关 + `video_interval`（1-30 秒）+ `grid_size`（[r,c]，1-10），抽帧拼图喂视觉模型，提示需选视觉模型才生效

### Added — 桌面客户端

- **首启 4 步引导**（`/onboarding`）：后端连通性自检 → LLM 供应商 + 模型 → 转写引擎选择（默认推荐 Groq）→ Cookie 同步说明。完成后 `localStorage('bilinote-onboarded')` 标记，纯 web 端不打扰
- **Sidecar 健康度面板**：右下角浮动状态点（绿/黄/红，5s 轮询 `/sys_health`），点开抽屉看最近 200 行后端日志、一键重启后端（新增 Tauri command `restart_backend_sidecar`）、复制日志
- **启动期路径诊断**：Tauri `setup` 中检测安装路径含非 ASCII / 含空格 / 父目录不可写时，emit `backend-warning` 让前端顶端横幅显式告警，主动暴露 README 长期文字警告但无防御的"中文路径"等坑

### Changed

- Whisper 默认模型 size 从 `medium`（~1.5GB）改为 `tiny`（~75MB）：新装用户没主动设置时不再卡在首次大模型下载；高精度可在「音频转写配置」页主动切
- 切到 `fast-whisper` / `mlx-whisper` 且当前 size 未下载时，「音频转写配置」页保存前 confirm 体积提示，并推荐改用在线引擎
- Tauri sidecar 启动逻辑抽出 `spawn_backend_sidecar()`；child handle 存进 `SidecarHandle` state 以支持后续 restart
- sidecar stdout/stderr emit 时不再用 `format!("'{}'", ...)` 包引号，原文直传（前端 hook 兼容旧格式兜底剥引号）

### Fixed

- WhisperTranscriber 在半成品模型目录上死循环报 `Unable to open file 'model.bin'`：判定从「目录存在」改为「`model.bin` 落盘」，半成品目录会被识别并重新下载（PR `fix/backend-deploy-resilience`）
- `/api/deploy_status` 在没装 torch 的部署上 `ModuleNotFoundError: No module named 'torch'` 500：torch 改 try/except，未装时返回 `{available: false, torch_installed: false}`；transcriber 配置 + ffmpeg 也都裹 try，单项失败不再打死整个监控页（同上 PR）
- `routers/config._check_whisper_model_exists` 同步改用 `model.bin` 判定，避免「已下载」状态在监控页误报

## [2.1.4] - 2026-05-07

CI 工程化修复，无运行时行为变化。

### Internal

- 桌面端 Tauri 构建矩阵去掉 Linux（`ubuntu-22.04 / x86_64-unknown-linux-gnu`）。Linux 桌面端构建持续 17m+，且无对应分发渠道；Linux 用户继续可以走 Docker 镜像 (`ghcr.io/jefferyhcool/bilinote`)
- commitlint workflow 去掉无效的 `firstParent` input（wagoid/commitlint-github-action@v6 不支持，被忽略并打 warn）
- 规范 release merge commit 标题：`chore(release): vX.Y.Z`（合 master）/ `chore(release): merge release/X.Y.Z back into develop`（回灌 develop），让 commitlint 能正确识别。`RELEASING.md` §3 与 `CONTRIBUTING.md` §6.3 同步更新

## [2.1.3] - 2026-05-07

### Fixed

- DeepSeek 等非多模态供应商被 400 拒绝（issue #282）：`UniversalGPT.create_messages` 与 `_build_merge_messages` 此前**无条件**把 content 拼成 OpenAI 多模态数组 `[{"type":"text",...}]`，DeepSeek `deepseek-chat` 等模型不识别 `image_url` 变体直接报 `invalid_request_error`。`GPTFactory.from_config` 一律实例化 `UniversalGPT`，所以问题覆盖**所有**通过模型设置页接入的非多模态供应商，不止 DeepSeek。
  - 现按 `video_img_urls` 是否非空切换 content 形态：有图保留多模态数组（视觉模型不退化），无图退回 string。合并阶段历来不带图，统一改 string。
  - 与同包内 `deepseek_gpt.py` / `openai_gpt.py` / `qwen_gpt.py` 的 message builder 行为对齐。
  - 新增 `backend/tests/test_universal_gpt_content_format.py` 6 个 case 回归覆盖（含 `image_url` 字面 not-in JSON 断言）。

感谢 @voidborne-d 的修复（#345）。

## [2.1.2] - 2026-05-07

补 v2.1.1 上 ghcr.io 镜像构建失败的坑。

### Fixed

- Docker 镜像构建失败：v2.1.1 tag 触发的 ghcr.io 推送在 frontend-builder 第 7/7 步 `pnpm run build` 挂掉（vite `loadConfigFromBundledFile` 加载 `@tailwindcss/vite` plugin 时 1.5s 内异常退出）。
  - `Dockerfile.complete` 与 `BillNote_frontend/Dockerfile` 升 `node:18-alpine` → `node:20-alpine`：Tailwind v4 已不再支持 Node 18，Vite 6 也推荐 Node 20+
  - `Dockerfile.complete` 的 frontend 阶段同时复制 `pnpm-lock.yaml` 并改用 `--frozen-lockfile`，杜绝每次构建重解析 semver 拉到比本地新的 native dep
  - `BillNote_frontend/pnpm-lock.yaml` 强制入库（之前一直未提交，导致 CI / 本地依赖图持续漂移）
- README 联系社区段补上微信群二维码（之前只写"年会恢复更新以后放出最新社区地址"）

## [2.1.1] - 2026-05-07

工程化与文档收尾，无运行时行为变化。

### Added

- [`CONTRIBUTING.md`](./CONTRIBUTING.md) — 贡献指南，落地简化 Git Flow（master + develop + 短生命周期分支）+ 提交规范 + 合并规范
- [`RELEASING.md`](./RELEASING.md) — 发版手册（Release Manager 视角），含 release/* 流程 + 各商店人工上传步骤 + 自动发布所需 secrets
- `.github/ISSUE_TEMPLATE/{config,bug_report,feature_request}.yml` — 表单形式的 issue 模板，按工作区分类
- `.github/pull_request_template.md` — PR 模板，把 CONTRIBUTING §5.2 落成 checklist
- `.commitlintrc.json` + `.github/workflows/commitlint.yml` — commitlint CI（PR + push develop/master 时校验，自定义 type 白名单，兼容中文 subject）
- `.github/workflows/release-extension.yml` — `v*` tag push 时自动构建插件 .zip / .xpi / .crx 并挂到对应 GitHub Release（商店自动发布以注释形式预留）

### Changed

- 关于页二维码改为 `import @/assets/wechat.png`，不再依赖腾讯云 COS CDN，更新只需替换文件 + 跑构建
- 群聊 QR 替换为最新版本（`doc/wechat.png` + `BillNote_frontend/src/assets/wechat.png`）

### Removed

- 关于页 QQ 群联系方式（号 785367111，已不再活跃维护）
- 旧版 `.md` 格式 issue 模板（被新 yml 表单模板取代）

## [2.1.0] - 2026-05-07

本次发布的主线是**浏览器插件**和 **B 站字幕优先链路**。配合一些后端 / 前端体验修复。

### Added — 浏览器插件 (`BillNote_extension/`)

全新 Chrome / Edge / Firefox MV3 扩展。Vue 3 + Vite + UnoCSS，骨架基于 vitesse-webext。

- **入口四件套**
  - 工具栏 popup：识别当前 tab → 一键提交，紧凑展示标题 + 封面 + 进度
  - 视频页悬浮按钮：仅在支持平台注入，点击即触发任务
  - 右键菜单"用 BiliNote 总结此视频"：限定 4 个支持域名
  - 侧边栏（side panel）：详情视图 + 三模式切换
- **侧边栏三视图**
  - Markdown：渲染笔记，复制 / 下载 .md
  - 思维导图：基于 markmap-lib + markmap-view 的可缩放 mind map
  - AI 问答：复用后端 RAG `/chat/index`、`/chat/status`、`/chat/ask` 三件套，自动索引 + 多轮历史
- **设置页五大块**（搬入 web 端全部配置能力，今后插件即配置中心）
  - 通用：后端地址、连通性测试、默认供应商 / 模型 / 画质 / 截图 / 跳转 / 风格
  - 模型供应商：完整 CRUD、启用切换、连接测试、模型增删
  - 音频转写配置：fast-whisper / mlx-whisper / Groq / 必剪 / 快手 切换、Whisper 模型大小、本地下载状态、触发下载
  - 下载配置：每平台 cookie 显示、浏览器一键同步、手动粘贴
  - 部署监控：后端 / FFmpeg / CUDA / Whisper 状态总览
- **浏览器 cookie 直通**：`chrome.cookies.getAll` 一键把 `.bilibili.com` 等域 cookie 同步到后端 `/api/update_downloader_cookie`
- **B 站字幕浏览器抓取**：插件直接调 player API 拿字幕，借 host_permissions 自动带本地登录态 cookie，绕过 CORS；随提交以 `prefetched_transcript` 字段附给后端，后端跳过 `download_subtitles` + 音频转写，直接进 GPT 总结

### Added — 后端

- `BilibiliSubtitleFetcher`（`app/downloaders/bilibili_subtitle.py`）：直接调 B 站 player API 拿字幕，作为非插件场景下 yt-dlp 路径的更可靠替代
- `VideoRequest.prefetched_transcript` 字段：客户端预取的字幕直接落到 `<task_id>_transcript.json`，NoteGenerator cache-hit 自动复用

### Added — 前端 Web

- Zustand persist 迁移到 IndexedDB（#318）

### Changed

- 后端 CORS：从静态 origin 列表改为 regex，兼容 `chrome-extension://`、`moz-extension://`、`localhost`、`tauri.localhost`
- mlx-whisper 仓库 ID 改用 `MLX_MODEL_MAP`：`whisper-{size}-mlx` 命名（`large-v3-turbo` 例外），不再 hardcode 出 404
- BilibiliDownloader 从 `CookieConfigManager` 读取 cookie 并注入 yt-dlp cookiefile（#333）
- CLAUDE.md 补充 v2.0.0 引入的子系统说明（RAG / Chat、可选 Nacos+RabbitMQ、i18n、cookie/transcriber 管理器）以及浏览器插件 workspace

### Fixed

- AILogo：自定义供应商（`logo='custom'`）走兜底渲染时不再误报 `console.error`，未匹配的名称降级为 warn
- SettingPage `Model.tsx` 双栏布局加 `min-h-0 overflow-y-auto`：供应商列表过长时无法滚动
- 供应商开关切换不能实时生效（#336）
- `/get_all_providers` 中 301 行历史伪内置脏数据清理 + `add_provider` 加防御（强制 `type='custom'`、同名查重、错误向上抛）
- `/api/task_status` 拆 ResponseWrapper：插件侧进度条因未拆 `data` 全灰；同时把 `R.error` 翻译为 `status:'FAILED'`，避免 UI 卡在轮询循环
- ESLint / ESM `__dirname` 在 production build 中未定义（多个 docker / vite 配置修复）
- GitHub Actions 构建错误 + apt-get 安装失败 + 删除仓库内 ffmpeg 二进制
- 渲染时剥掉 backend 注入的 `> 来源链接：URL` 行（与 web 端 MarkdownViewer 一致），导出文件保留原行便于溯源
- 侧边栏布局收紧：完成后不再渲染 8 段进度条；标题压成单行；视图切换 + 复制 / 下载并入一行；历史任务从底部 details 改为顶栏下拉

### Internal

- 新增分支策略：`develop` / `release/x.y.z` / `master` git-flow
- 备份 backend SQLite DB 前 / 清理脏数据后均落盘存档
