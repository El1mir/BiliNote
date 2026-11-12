# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

BiliNote is an AI video note generation tool. It extracts content from Bilibili video links (single video, multi-part, or a batch of URLs) and generates structured Markdown notes using LLM models. Full-stack app with a FastAPI backend, React frontend, and a browser extension. The Tauri desktop build was removed; the product is Web + extension only.

## Development Commands

### Backend (Python 3.11 + FastAPI, 用 uv 管理环境)

```bash
cd backend
uv venv --python 3.11 .venv       # 创建 Python 3.11 虚拟环境（首次）
uv pip install -r requirements.txt
uv pip install "setuptools<81"    # ctranslate2 依赖 pkg_resources，必须锁 <81
.venv\Scripts\python.exe main.py # Starts on 0.0.0.0:8483（Windows）
# source .venv/bin/activate && python main.py   # macOS / Linux
.venv\Scripts\python.exe -m pytest             # Run tests in backend/tests/
pytest tests/test_request_chunker.py::test_name   # Run a single test
```

### Frontend (React 19 + Vite + TypeScript)

```bash
cd BillNote_frontend
pnpm install
pnpm dev          # Dev server on port 3015, proxies /api to backend
pnpm build        # Production build
pnpm lint         # ESLint
```

### Docker

```bash
docker-compose up                              # Web stack (backend + frontend + nginx)
docker-compose -f docker-compose.gpu.yml up    # GPU variant
```

### Browser Extension (Vue 3 + vitesse-webext, MV3)

```bash
cd BillNote_extension
pnpm install
pnpm dev          # watch mode → ./extension/
pnpm build        # production build → ./extension/
pnpm typecheck
pnpm test         # Vitest unit tests
pnpm test:e2e     # Playwright e2e
```

Load unpacked at `chrome://extensions/` → select `BillNote_extension/extension/`. Talks to the same backend at `http://localhost:8483` (configurable in the options page). CORS in `backend/main.py` already accepts `chrome-extension://` and `moz-extension://` via regex.

## Architecture

**Backend** (`backend/`) — FastAPI app, entry point `main.py`:

- `app/routers/` — API routes: `note.py` (generation), `note_group.py` (note groups), `provider.py`, `model.py`, `config.py`
- `app/services/` — Business logic:
  - `note.py` — `NoteGenerator` orchestrates the full pipeline (download → transcribe → LLM → notes)
  - 并发调度没有独立队列模块：`routers/note.py` 的 `_ParallelGate` 是唯一并发上限（设置里的并行数，热更新），任务体直接执行；批量入口用固定 8 worker 的分发池接住请求
  - `cookie_manager.py` — per-platform cookie storage; injected into yt-dlp by downloaders (e.g. Bilibili)
  - `transcriber_config_manager.py` — persisted transcriber settings
- `app/downloaders/` — Platform adapters with a shared `base.py` interface; only the Bilibili adapter is registered for generation (`SUPPORT_PLATFORM_MAP` in `app/services/constant.py`), while source intake (`app/services/source_intake.py`) stays platform-neutral so more adapters can be added without touching the intake contract.
- `app/transcriber/` — Speech-to-text engines with the factory in `transcriber_provider.py`: `fast-whisper` (local) and `openai-asr` (any openai-compatible online endpoint). The bcut / kuaishou / groq / mlx-whisper engines were removed — the first three are rate-limited or discontinued third-party free APIs, and the last is macOS-only; an openai-compatible endpoint covers all of them.
- `app/gpt/` — LLM integration with factory pattern (`gpt_factory.py`), prompt templates (`prompt.py`, `prompt_builder.py`), and `request_chunker.py` for long transcripts
- `app/db/` — SQLite + SQLAlchemy: DAO pattern (`provider_dao.py`, `model_dao.py`, `video_task_dao.py`), models in `models/`
- `app/utils/` — `response.py` (ResponseWrapper for consistent JSON), `video_helper.py` (screenshots via FFmpeg), `export.py` (PDF/DOCX), `ppt_generator.py`, `minio_client.py`
- `app/validators/video_url_validator.py` — URL → platform detection (mirrored client-side in the extension)
- `app/exceptions/` — `BizException` + handlers wired in `main.py` via `register_exception_handlers`
- `backend/events/` — Blinker signal system for post-processing (e.g., temp file cleanup after transcription); registered in `lifespan` startup
- `backend/ffmpeg_helper.py` — `ensure_ffmpeg_or_raise` is called at startup; respects `FFMPEG_BIN_PATH`

**Frontend** (`BillNote_frontend/src/`) — React 19 + Vite + Tailwind 4, Ember Studio design system:

- `ember/` — the entire presentation layer (the pre-rewrite `pages/`, `components/`, `layouts/`, `App.tsx` were deleted):
  - `ember/tokens.css` + `ember/motion.css` — design tokens (terracotta `#c2410c`, warm neutrals, Playfair Display / Source Sans 3 / Fira Code) and the shared motion vocabulary; `src/index.css` is just those two imports.
  - `ember/ui/` — primitives: Button, Card, Input, Textarea, Field, Chip, Badge, Progress, Skeleton, EmptyState, Tabs, Dialog, Drawer, Switch, Checkbox, Select, Tooltip, Spinner.
  - `ember/shell/AppShell.tsx` — 256px sidebar at >=1280px, 76px icon rail at 768–1279px, top bar + Drawer below 768px; content does not remount across breakpoints.
  - `ember/pages/` — `WorkspacePage`, `SettingsPage` (+ `sections/`), `OnboardingPage`, `NotFoundPage`; `ember/EmberApp.tsx` owns routing (`BrowserRouter` only - the Tauri HashRouter branch was removed).
  - `ember/features/` — `workspace/` (IntakeForm, BatchImportPanel, TaskList, GroupPanel, TaskProgressCard, `useNoteGroups`, `archive`) and `reader/` (NotePanel with note + transcript tabs, MarkdownNote, TranscriptView, outline).
  - `ember/i18n/` — `strings.ts` (zh-CN / en-US dictionaries, `MessageKey`) + `context.ts` (`useI18n`) + `locale.ts` (`translate` for non-React modules).
- `store/taskStore/` — the only Zustand store left; tasks carry `revision` and stale status updates are rejected.
- `services/` — Axios clients matching backend routes (`note`, `noteGroup`, `model`, `provider`, `transcriber`, `config`, `system`, …). The response interceptor unwraps the `ResponseWrapper` envelope, so call sites receive `data` directly.
- `hooks/useTaskPolling.ts` — 3 s polling, but it subscribes to `GET /api/v1/task-groups/events` (SSE) while tasks are active and skips polling while the stream is connected.
- `utils/request.ts` — shared Axios instance, `REASON_KEYS` and `localizedError()` map structured backend `data.reason` values to i18n keys.
- Path alias: `@` → `./src`.

**Core Workflow**: User submits a Bilibili URL (single, multi-part, or batch) → source intake normalises it → task queued → download video → extract audio (FFmpeg) → transcribe (fast-whisper or an openai-compatible ASR endpoint) → generate notes (LLM) → frontend follows progress over SSE → display Markdown + transcript, with inline screenshots that zoom on click.

**Browser Extension** (`BillNote_extension/`) — Vue 3 + Vite + UnoCSS + webextension-polyfill, MV3:

- `src/popup/Popup.vue` — main entry: detects platform from active tab URL, drives generate flow, shows progress + markdown
- `src/options/` — settings pages: backend URL, providers/models (loaded from `/get_all_providers` + `/model_enable/{provider_id}`), transcriber (fast-whisper / openai-compatible ASR), downloader cookies, monitor, quality and screenshot/link toggles
- `src/logic/api.ts` — backend API client (uses `settings.backendUrl`, unwraps `ResponseWrapper`, absolutizes `/static/screenshots/...` image paths)
- `src/logic/storage.ts` — `chrome.storage.local`-backed Pinia-like state via `useWebExtensionStorage` for settings + last 30 tasks
- `src/logic/platform.ts` — URL → platform detection mirroring `backend/app/validators/video_url_validator.py`
- `src/sidepanel/Sidepanel.vue` — side panel that follows one task and renders its Markdown (copy / download); the mind map and RAG-chat views were removed together with their backend
- `src/manifest.ts` — MV3 manifest, popup is default action; `host_permissions: *://*/*`
- Polling lives client-side in popup (3 s interval while open); MV3 service worker is intentionally thin in P1

## Key Configuration

- **Ports**: Backend 8483, Frontend dev 3015, Docker maps 3015→80
- **Environment**: Root `.env` (copy from `.env.example`). LLM API keys are configured through the UI, not env vars.
- **Database**: SQLite at `backend/bili_note.db` (`app/db/engine.py` uses the relative `sqlite:///bili_note.db`, so it lands in the backend working directory), auto-initialized on first run
- **FFmpeg**: Required system dependency for video/audio processing
- **Vite proxy**: Dev server proxies `/api` and `/static` to backend (configured in `vite.config.ts`, reads env from parent dir; falls back to current dir when `DOCKER_BUILD` is set)
- **CORS**: `backend/main.py` uses a regex (`CORS_ORIGIN_REGEX`) that allows localhost and `chrome-extension://` / `moz-extension://` origins — required for the web app and the browser extension.

## Specs & Tickets

非平凡改动在 `specs/` 下落档。**默认在当前 spec 内修正**；只有当 (a) 明确开启一个新需求，或 (b) 要修正的内容不属于当前 spec 时，才新建目录（`NNN-slug`，编号递增）：

- `specs/<NNN>-<slug>/spec.md` —— 设计规格：背景 / 目标 / 非目标 / 已定决策 / 接口草案 / 流程 / 测试要点。状态标 `draft` / `approved` / `implemented`。
- `specs/<NNN>-<slug>/tickets/*.md` —— 实现工单，按顺序编号，每个含「依赖 / 关联 spec 章节 / 目标 / 改动点 / 验收」。
- `specs/README.md` —— 合集索引，新增目录后在里面登记。

Rules:

- **默认不新建 spec**：只有「明确开启新需求」或「要修正不属于当前 spec 的内容」时才新建目录；bug 修复、决策调整、补测试等只要不脱离当前 spec，就直接改当前 spec（在 spec 里注明日期与来源，并与既有决策交叉引用）。
- **spec 稳定、ticket 易变**：实现细节写 ticket，不塞进 spec。
- **决策不沉默**：已拍板的写「已定决策」，未拍板的写「待确认问题」，不留隐含假设。
- ticket 完成后，在 `spec.md` 的「实现清单」里更新状态，并在 `specs/README.md` 索引里同步。
- 测试与实现同一 ticket，并**按改动分目录**：后端 `backend/tests/<NNN>-<slug>/`、前端 `BillNote_frontend/tests/<NNN>-<slug>/`，编号与 `specs/<NNN>-<slug>/` 对应。
- 完成后 spec 状态改 `implemented`。

## 与用户交互的硬规则

- **一切提问必须走 `ask_user_question`（askuser）工具，禁止在正文里用「❓ Q1 …… ➡️ 选 A」这类文字形式提问。** 每一次提问都生效，没有例外：设计选择、需求确认、方案取舍、参数取值、是否继续，一律弹成选项。正文只用于陈述已确认的结论、给出证据、报告进度。
- 每个问题都要列出可选项、把推荐项放第一位并在 label 末尾标「（推荐）」，同时用一句话说明该选项的代价或影响。
- 一次可以批量提多个问题（同一个 `ask_user_question` 调用里放多条），但不要用正文代替工具。

## Code Style

- **Frontend**: ESLint + Prettier (2 spaces, single quotes, 100 char width, Tailwind plugin). TypeScript strict mode.
- **Backend**: Python with type hints. No configured linter. Uses Pydantic models for validation.
- **Note**: The frontend directory is named `BillNote_frontend` (not "Bili").
- **Specs**: Non-trivial changes are documented under `specs/`. **Default to amending the current spec**; only create a new `specs/<NNN>-<slug>/` when starting an explicitly new requirement or correcting something outside the current spec's scope.
