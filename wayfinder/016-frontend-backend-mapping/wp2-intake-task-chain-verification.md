# T-050 WP2：Workspace single/batch intake 与任务状态链 — 验证证据

日期：2026-11-09（rev 2 重跑）· 分支 flow/T-048 · 只读验证，无产品源码改动。

结论：**PASS**。single 与 batch 两条 UI→HTTP→DB→终态链路在隔离 backend 上真实跑通到 **SUCCESS**，已取得 payload、HTTP 码、task_id / group_id、状态序列、终态 markdown + transcript、页面刷新恢复，并交付 WP3 可消费的 SUCCESS 契约。上一轮的转写阻塞（本机无 faster-whisper 模型且 huggingface.co 不可达）已按调度授权改为**在线 ASR**（硅基流动 XingChenASR-V3.2，`api_style=transcriptions`）后解除。

## 1. 隔离环境（严格按案卷口径）

- 数据：复制 `.quarantine/orphan-T-052-1794220574030/backend/bili_note.db` 到临时目录 `.quarantine/t050-run/`（含 provider `kouri` / `https://api.kourichat.com/v1` / model `gpt-6-luna-codex`，active model 已配置）。API Key 全程由服务脱敏返回，本文不回显。
- 依赖：`T-048/backend/.venv`（只读共享）。
- 转写：`backend/config/transcriber.json` 改为 `transcriber_type=openai-asr` + 从 master 复制的 `openai_asr_endpoints`，`openai_asr_id` 指向硅基流动 XingChenASR-V3.2。验证后已还原为原 `fast-whisper/tiny`。
- 后端：`DATABASE_URL=sqlite:///<tmp>/bili_note.db`、`BACKEND_PORT=8490`、`OUT_DIR/DATA_DIR` 指向临时目录，启动器 `run_backend.py` 内显式设置 `STATIC=/static`（宿主环境残留 `STATIC` 变量会让 `app.mount` 断言失败）。
- 前端：`BillNote_frontend/.env.local` → `VITE_API_BASE_URL=http://127.0.0.1:8490/api`、`VITE_FRONTEND_PORT=3020`（`.env.local` 被 `BillNote_frontend/.gitignore:13` 忽略；使用后已还原为 `http://127.0.0.1:8484/api` / 3017）。
- `GET /api/sys_check` → HTTP 200 `{"code":0,"msg":"success","data":null}`。
- 主库 `C:/Users/Administrator/Desktop/prjs/BiliNote/backend/bili_note.db` mtime 全程保持 `2026-10-31 19:14:29`。

## 2. single 路径（`BV1GJ411x7h7`）

| 环节 | 证据 |
|---|---|
| 请求 payload（浏览器 XHR 记录） | `{"video_url":"https://www.bilibili.com/video/BV1GJ411x7h7","platform":"bilibili","quality":"medium","format":[],"scene":"life","detail":"detailed","video_understanding":false,"video_interval":6,"sampling_mode":"interval","max_frames":60,"frames_per_second":2,"frame_limit_mode":"total","ocr_assist":null,"grid_size":[2,2]}` |
| HTTP | `POST /api/generate_note` → **200**（275ms），随后 `POST /api/expand` 200、`GET /api/v1/task-groups/snapshot` 200 |
| task_id | `a167ffbf-ec14-4f4f-adc5-fd7360a7fa91` |
| 状态序列 | 轮询期首次采样即 `SUCCESS/saving`；终态 `{"status":"SUCCESS","stage":"saving","progress":100}` |
| 终态内容 | `result.markdown` 610 字符（含大纲小标题与来源链接）；`result.transcript` = `{language, full_text, segments[26]}`；`result.audio_meta` 含 `file_path`（指向临时 `DATA_DIR`）、`title`、`duration` 212.393 |
| 页面渲染 | 任务卡显示标题、`已完成`、`进度 100%`，笔记/转写双 Tab、大纲、复制/下载 Markdown |
| 刷新恢复 | `F5` 后历史列表仍显示该任务「已完成 / 保存结果」，分组计数「全部笔记 1 / 未分组 1」 |
| 存储侧 | 隔离 DB `video_tasks` 1 行：`task_id`、`video_id=BV1GJ411x7h7`、`group_id=NULL`、`payload_json` 与上方 payload 键集一致 |

## 3. batch 路径（3 链接，1 条已生成故实际提交 2 条）

| 环节 | 证据 |
|---|---|
| 解析 | `POST /api/expand` ×3 → 200；UI「已展开 3 个视频，共 3 个分P」，第 1 条标注「已生成」 |
| 提交请求 | `POST /api/generate_notes` → **200**（57ms） |
| group_id | `fc2be11205cd40ff9d2339ca2dd01b34`（分组名 `T050 batch verify`） |
| task_id × 2 | `08759c4f-ca1d-4182-bc2a-1d7e8f9aadcf`、`5a0cc597-28ce-47b3-8520-04e2ac5c1e08` |
| payload（DB `payload_json`） | 两条均为 `video_url/platform/quality/link:false/screenshot:false/_format:["toc","link","summary"]/scene:"life"/detail:"detailed"/extras:""/video_understanding:false/video_interval:6/grid_size:[2,2]/sampling_mode:"interval"/max_frames:60/frames_per_second:2/frame_limit_mode:"total"/ocr_assist:null/group_id:<同一 gid>/merge_items:null/merge_title:null/merge_polish:false` |
| 状态序列 | `5a0cc597`: 首次采样即 `SUCCESS/saving`；`08759c4f`: `SUMMARIZING/summarizing` → 约 4 分钟后 `SUCCESS/saving` |
| 终态内容 | `08759c4f` markdown 1312 字符 / transcript 86 段；`5a0cc597` markdown 800 字符 / transcript 3 段 |
| 刷新恢复 | `F5` 后 3 条任务全部「已完成 / 保存结果」，分组面板出现「T050 batch verify 2」与「未分组 1」，`全部笔记 3`，横幅「已完成 3 个任务」 |

## 4. WP3 可消费的 SUCCESS 契约（交接）

- 读取入口：`GET /api/task_status/<task_id>` → `data.{status,stage,stage_label,progress,updated_at,result}`。
- 终态判定：`status === "SUCCESS"`（`stage` 停在 `saving`，`progress` 100）。
- 笔记内容：`data.result.markdown`（字符串，Markdown）。
- 转写内容：`data.result.transcript = { language: string|null, full_text: string, segments: [{start:number,end:number,text:string}] }`。
- 音频元信息：`data.result.audio_meta = { file_path, title, duration, ... }`（`file_path` 指向本次隔离 `DATA_DIR`，清理临时目录后失效）。
- 列表入口：`GET /api/task_list` → `data.{tasks,total}`，行内含 `task_id / title / group_id / created_at`。
- 可用 fixture（**仅本次隔离运行期内有效，临时目录已删除**）：single `a167ffbf-ec14-4f4f-adc5-fd7360a7fa91`；batch `08759c4f-…` / `5a0cc597-…`（group `fc2be11205cd40ff9d2339ca2dd01b34`）。

## 5. 清理

- 停止后端（PID 29344）与前端（PID 38356）进程，`netstat` 确认 8490 / 3020 无 LISTENING。
- 删除临时运行目录 `.quarantine/t050-run/`（含 DB、data、screenshots、启动器）。
- 还原 `backend/config/transcriber.json` 为 `fast-whisper/tiny`；还原 `BillNote_frontend/.env.local`；删除临时根 `.env`。
- 主库 mtime 未变；`git status --short` 无输出（`## flow/T-048...origin/flow/T-048`，无未提交改动）。

## 6. 未执行 / 边界

- **合并任务（`merge_items`）**：本次批量未勾选「合并为一个任务」，故 `merge_items/merge_title/merge_polish` 落库为 `null/false`，未产生合并终态证据。
- **多 P 范围（`batch-range` 页码范围）**：三个链接均为单 P，未应用页码范围，`batch-range` 未产生 payload 差异。
- **截图/链接开启态**：`screenshot/link` 均为 `false`，未验证开启后终态截图产物。
- **前端单测/tsc/lint**：本轮未执行（本轮为浏览器端到端验证）；上一轮同 worktree 的 12 files / 71 tests、`tsc -b`、`pnpm lint` 均 exit 0。
