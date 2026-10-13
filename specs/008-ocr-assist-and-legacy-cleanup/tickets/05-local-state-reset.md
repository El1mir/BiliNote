# 05 · 本地缓存与历史任务重置

- **状态**：已实现
- **依赖**：03 / 04（重置要在功能删除之后做，避免清完又被旧逻辑写回）
- **上游 spec**：`specs/008-ocr-assist-and-legacy-cleanup/spec.md` §9

## 目标

提供一个**一次性**重置脚本，把本地生成物与历史任务记录清干净，让用户可以「删掉重新生成」；同时通过前端 persist 版本号提升，丢弃浏览器里残留的旧任务列表。

## 范围

| 目标 | 路径/表 | 现状体量 |
| --- | --- | --- |
| 抽帧中间产物 | `backend/data/output_frames/` | 158MB / 831 文件 |
| 拼图中间产物 | `backend/data/grid_output/` | 14.4MB / 71 文件 |
| 生成的截图 | `backend/static/screenshots/` | 111MB / 644 文件 |
| 笔记产物 | `backend/note_results/` | 41 json + 18 md + 40 status + 18 transcript + 若干 `.tmp` |
| 历史任务 | `video_tasks` 表 | 17 行 |
| 资源登记 | `media_resources` / `media_cleanup_runs` | 644 / 17 行 |
| 向量集合 | `backend/vector_db/` | 8.7MB，17 个 UUID 集合 + `chroma.sqlite3` |
| 日志 | `backend/logs/app.log` | 3.7MB（可选） |

同时清理**孤儿表**（无 ORM、无代码引用，明确的历史遗留）：`media_resource_refs`、`note_versions`、`note_groups`、`note_migration_markers`、`note_migration_diagnostics`。

> 注意：`note_versions` 这张孤儿表是历史遗留，与 ticket 04 删除的**前端**版本管理没有关系，不要混淆。

## 安全要求（硬性）

1. **默认干跑**：不加参数只报告「将删除什么 + 合计多少字节」，不做任何删除。必须显式传 `--apply` 之类才真删。
2. **绝不触碰**：
   - `backend/models/`（whisper 模型，564MB）
   - `.venv/`、`node_modules/`
   - 数据库文件本身（`bili_note.db`）—— 只清表，不删库
   - 用户配置（`.env`、`config/`、`transcriber` 等配置）
   - `backend/data/data/`（这是 `get_data_dir()` 双重拼接 bug 产生的空目录，保留以免掩盖问题）
3. 删除前打印**解析后的绝对路径**，避免相对路径在错误的 cwd 下误删。
4. 每个删除步骤独立 try/except，单步失败不中断整体，并在最后汇总报告。

## ⚠️ 必须先解决的坑：DATABASE_URL

`backend/app/db/engine.py` 的 `DATABASE_URL` 默认值是 `sqlite:///bili_note.db`（**相对路径**），`.env` 里没有设置它。

这意味着：**从仓库根目录运行脚本会连到一个新的空库 `./bili_note.db`**，于是脚本会「成功」报告删了 0 行，而真正的 `backend/bili_note.db` 丝毫未动。

脚本必须：

- 显式解析并打印实际使用的数据库绝对路径；
- 在连到的库里**表不存在或行数异常为 0** 时给出明确警告，提示可能是路径问题；
- 建议脚本内部显式指向 `backend/bili_note.db`，或在运行说明里要求设置 `DATABASE_URL`。

这是本 ticket 最容易被误判为「脚本没生效」的地方。

## 前端侧

- 提升 `taskStore` persist 的 `version`（当前 storage name 为 `'task-storage'`，见 `taskStore/index.ts:284-298`），使旧任务列表在下次加载时被丢弃。
- 若 `persist` 已配置 `migrate`，在其中直接返回初始状态；否则通过提升 `version` + 无匹配迁移来落回默认值。
- 注意与 ticket 04 的容错读取协调：ticket 04 保证「万一还有数组数据也能渲染」，本 ticket 保证「正常路径下旧列表被整体丢弃」。两者不冲突。

## 交付物

- `scripts/reset_local_state.py`（建议位置）
- 运行说明（写进脚本 `--help` 或 spec 008 的 ticket 里），至少覆盖：干跑、确认执行、`DATABASE_URL` 注意事项、脚本不会碰哪些东西

## 验收

- 干跑输出与实测体量吻合（截图 ~111MB、`output_frames` ~158MB、`grid_output` ~14.4MB、`video_tasks` 17 行、`media_resources` 644 行）。
- 干跑**不产生任何删除**（跑完文件数与之前一致）。
- 执行后：中间产物目录、截图目录、`note_results`、`video_tasks`、Chroma 集合均为空；`backend/models/`（564MB）、`.venv/`、`bili_note.db`、`.env`、`config/` **仍在**。
- 数据库绝对路径被打印出来；在 `DATABASE_URL` 未设置且从仓库根运行的情况下，脚本**不会**静默地什么也没删。
- 浏览器端旧任务列表在版本号提升后不再出现。
- 脚本可重复执行（第二次运行报告 0 项，不报错）。
