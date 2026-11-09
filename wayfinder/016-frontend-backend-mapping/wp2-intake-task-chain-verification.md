# T-050 WP2：Workspace single/batch intake 与任务状态链 — 验证证据

日期：2026-11-09 · 分支 flow/T-048 · 只读验证，无产品源码改动。

结论：**PARTIAL / BLOCKED**。single 与 batch 两条 UI→HTTP 链路真实命中隔离 backend，请求 payload、HTTP 业务码、错误原文均已取得；但**转写引擎初始化失败**（本机无 faster-whisper 模型、huggingface.co 不可达），任务行在创建前即失败，因此**没有 task_id、状态序列、终态内容**，无法交付 WP3 可消费的 SUCCESS 契约。

## 1. 环境（严格按案卷口径）

- 数据：复制 `.quarantine/orphan-T-052-1794220574030/backend/bili_note.db` 到临时运行目录 `.tmp-T050-run/`（含 provider `kouri` / base_url `https://api.kourichat.com/v1` / DB 内 API Key 仅显示掩码）。
- 依赖：`T-048/backend/.venv`（只读共享）。
- .env：复制 `T-048/backend/.env`；`TRANSCODER=fast-whisper`, `WHISPER_MODEL_SIZE=base`。
- 后端：`BACKEND_PORT=8491 BACKEND_HOST=127.0.0.1 .venv/Scripts/python.exe backend/main.py`，cwd=`.tmp-T050-run`，即 SQLite 落在临时目录。
- 前端：`VITE_API_BASE_URL=http://127.0.0.1:8491/api ./node_modules/.bin/vite --port 3021 --strictPort`。
- `GET /api/sys_check` → HTTP 200 `{"code":0,"msg":"success","data":null}`。
- 主库 `backend/bili_note.db` 未被读写：mtime 全程保持 `Oct 31 19:14`。

## 2. single 路径

| 环节 | 证据 |
|---|---|
| 输入 | Workspace「单集生成」，`https://www.bilibili.com/video/BV1xx411c7mD` |
| 请求 payload（浏览器 console） | `{"video_url":"https://www.bilibili.com/video/BV1xx411c7mD","platform":"bilibili","quality":"medium","format":[],"scene":"life","detail":"detailed","video_understanding":false,"video_interval":6,"sampling_mode":"interval","max_frames":60,"frames_per_second":2,"frame_limit_mode":"total","ocr_assist":null,"grid_size":[2,2]}` |
| HTTP（UI） | `POST /api/generate_note` 状态 0、耗时 30002ms：axios 客户端 30s 超时；UI 报 `{"code":-1,"msg":"请求失败，请检查网络连接","data":null}` |
| HTTP（直连 curl，绕过客户端超时） | `HTTP=500 total=42.262730s`，body `{"detail":"Cannot find an appropriate cached snapshot folder for the specified revision on the local disk and outgoing traffic has been disabled. ..."}` |
| taskId / 状态序列 / 终态 | **无**。`GET /api/task_list` 始终 `{"tasks":[],"total":0}`；隔离 DB `video_tasks` = 0 |

## 3. batch 路径

| 环节 | 证据 |
|---|---|
| 输入 | 批量生成，两个真实链接 `BV1xx411c7mD`、`BV1GJ411x7h7`（后者解析出标题 `Never Gonna Give You Up - Rick Astley`），「全选」后 2 个分P |
| 解析请求 | `POST /api/v1/intake/resolve` HTTP 200，body `{"mode":"batch","urls":["https://www.bilibili.com/video/BV1xx411c7mD","https://www.bilibili.com/video/BV1GJ411x7h7"],"contractVersion":1}` |
| 提交请求 payload | `{"platform":"bilibili","items":[{"bvid":"BV1xx411c7mD","p":1,"video_id":"BV1xx411c7mD","url":"https://www.bilibili.com/video/BV1xx411c7mD","title":""},{"bvid":"BV1GJ411x7h7","p":1,"video_id":"BV1GJ411x7h7","url":"https://www.bilibili.com/video/BV1GJ411x7h7","title":"Never Gonna Give You Up - Rick Astley"}],"quality":"medium","scene":"life","detail":"detailed","format":["toc","link","summary"],"extras":"","video_understanding":false,"video_interval":6,"sampling_mode":"interval","max_frames":60,"frames_per_second":2,"frame_limit_mode":"total","grid_size":[2,2],"ocr_assist":null,"group_name":"T050 WP2 isolated"}` |
| HTTP（UI） | `POST /api/generate_notes` 状态 0、耗时 30005ms（客户端 30s 超时） |
| HTTP（直连 curl） | `HTTP=200 total=42.118362s`，body `{"code":500,"msg":"批量生成失败: Cannot find an appropriate cached snapshot folder ...","data":null}` — 业务失败仍走 HTTP 200（`ResponseWrapper` 不设状态码） |
| groupId | 已创建：`8a7e00fdda484166a05e6a4b3e149a74`（首次 UI 提交）、`54bfd7f169be4607a65b68eaa59a3c90`（重试）、curl 一次再建一条 `T050 WP2 curl` |
| 子任务 / 状态序列 / 终态 | **无**。`video_tasks` = 0，`task_list` 空 |

## 4. 刷新恢复

刷新 `http://127.0.0.1:3021/` 后：分组栏显示 3 个分组（`T050 WP2 isolated` ×2、`T050 WP2 curl`），计数 `0`；历史区「还没有历史记录」；笔记区空状态。即**分组持久化与刷新回显可用**，但无任务可恢复。

## 5. 阻塞点（环境限制，非产品缺陷）

- 后端日志：`加载 whisper-base 失败` + `LocalEntryNotFoundError: Cannot find an appropriate cached snapshot folder ... outgoing traffic has been disabled`；`Systran/faster-whisper-base` 本地无缓存，HF 拉取失败。
- 复现：`curl -m 12 https://huggingface.co` → `curl: (28) Connection timed out after 12013 milliseconds`（HTTP 000）。
- 本机无 HF 缓存：`~/.cache/huggingface/hub/models--*whisper*` 为空；`backend/data` 下无 model.bin。
- 影响：`/generate_note` 在 readiness 之后、任务行落库之前初始化转写器即抛错，故无 task_id；batch 同样在逐条处理阶段抛错。
- 未采用 openai-asr 绕过：需要外部端点与凭据，属于环境外供给，且改转写配置属于 WP4a 范围。

## 6. 观察（未修复，需判定）

batch 在**逐条处理之前**就创建 note group；当所有条目失败时留空分组（本轮两次 UI 提交 + 一次 curl 复现 3 条 0 任务分组）。是否为既有 spec 违规取决于 batch 分组语义，本轮不改代码，交父卡判定。

## 7. 命令与结果（本轮实际执行）

```
# 后端 focused（backend/ 为 cwd）
T-048/backend/.venv/Scripts/python.exe -m pytest tests/test_openai_compatible_provider.py -q
  → 3 passed, 1 warning, exit 0（与本卡相邻，非 WP2 主体）

# 前端 focused
./node_modules/.bin/vitest run tests/001-bilibili-batch-import tests/018-single-batch-and-merged-note tests/020-note-rendering-and-batch-options
  → Test Files 5 passed (5) / Tests 25 passed (25), exit 0
./node_modules/.bin/tsc -b --noEmit            → TSC_EXIT=0
./node_modules/.bin/eslint src/ember/features/workspace/IntakeForm.tsx \
  src/ember/features/workspace/BatchImportPanel.tsx \
  src/ember/features/workspace/TaskList.tsx \
  src/store/taskStore/index.ts src/hooks/useTaskPolling.ts src/services/note.ts
  → ESLINT_EXIT=0
```

## 8. 清理

- 停：`bash-177`（8491）、`bash-200`（3021）已 kill；`curl 127.0.0.1:8491/api/sys_check` / `3021` 均 `Could not connect`。
- 删：`.tmp-T050-run/`（含隔离 DB 副本、note_results、logs）已删除。
- 主库 `backend/bili_note.db` mtime 未变（`Oct 31 19:14`）；工作树无 tracked 改动。

## 9. 逐条验收

1. single payload/HTTP/taskId/状态/终态/刷新 — **PARTIAL**：payload、HTTP、错误原文有；taskId/状态序列/终态/任务刷新恢复无（转写模型缺失）。
2. batch payload/HTTP/groupId/子任务/状态/终态/刷新 — **PARTIAL**：payload、HTTP（200/code 500）、groupId、分组刷新回显有；子任务/状态序列/终态无。
3. 真实隔离 backend 达终态 — **BLOCKED**：卡在转写引擎初始化，原始错误见 §5。
4. WP3 可消费 SUCCESS task 与数据契约 — **NOT RUN**：无 SUCCESS 任务可交付。
5. 共享 TaskList/selection 由 WP2 先验证 — **PARTIAL**：分组/任务列表刷新与空态行为已观察；selection 回调未在真实任务上验证。
