# T-053 WP4b：Onboarding 首启配置写链 — 验证证据

日期：2026-11-09 · 分支 flow/T-048 · 只读审计，无产品源码改动。

## 1. 环境

- 隔离 backend：`BACKEND_PORT=8491`，`DATABASE_URL=sqlite:///<worktree>/.t053-tmp/db/bili_note.db`，`OUT_DIR=<worktree>/.t053-tmp/out`，启动命令 `./.venv/Scripts/python.exe main.py`（工作目录 `backend/`）。
- 隔离前端：`vite --port 3019 --host 127.0.0.1`，`BillNote_frontend/.env.local` 临时改为 `VITE_API_BASE_URL=http://127.0.0.1:8491/api`。
- 主仓库 `backend/bili_note.db` 与主工作区未触碰；`.t053-tmp/` 仅测试期存在，结束后已删除；`.env.local` 已还原为 `http://127.0.0.1:8484/api` / 3017。
- 端口 3019 / 8491 结束后均已关闭。

## 2. 实测路径与结果

| 步骤 | 操作 | 结果 |
|---|---|---|
| backend ping | `GET http://127.0.0.1:8491/api/sys_check` | HTTP 200 `{"code":0,"msg":"success","data":null}` |
| 首启进入 | 浏览器打开 `http://127.0.0.1:3019/onboarding` | 步骤 1 显示「后端已就绪，可以继续。」；注：探活 URL 由 `VITE_API_BASE_URL` 直接拼接，写成 `http://host:port` 会打到 `/sys_check`（404）并停在启动画面，必须带 `/api` 后缀或留空走 Vite 代理 |
| 重试 | 点击「重新检测」 | 仍显示已就绪，按钮 loading 后恢复；不发写请求 |
| 步骤 2 写入 | 填供应商名 `t053-provider`、模型 `t053-model` → 「保存并下一步」 | `POST /api/add_provider` 200、`POST /api/models` 200、`POST /api/connect_test` 200（业务码 200104，仅记日志不阻塞）→ 进入步骤 3 |
| 步骤 3 写入 | 保持默认 Faster Whisper → 「保存并下一步」 | `PUT/POST /api/transcriber_config` 成功 → 进入步骤 4；落盘 `backend/config/transcriber.json`：`{"transcriber_type":"fast-whisper","whisper_model_size":"tiny"}` |
| 步骤 4 完成 | 「完成，进入 BiliNote」 | 写 `localStorage['bilinote-onboarded']='1'`，跳转 `/`，渲染 Workspace（输入框、单集/批量入口、空状态、分组） |
| 刷新回显 | 重新打开 `/onboarding` 与 `/` | `/` 直接进 Workspace，`localStorage` 仍为 `1`；`/onboarding` 仍可访问且显示已就绪 |

隔离 DB 写入核对（`sqlite3` 直读）：

- `providers` = 1 行：`('t053-provider', 'https://api.openai.com/v1', enabled=1)`
- `models` = 1 行：`('t053-model')`
- `general_settings` = 1 行（启动默认值）
- `video_tasks` / `note_groups` / `media_resources` = 0

## 3. 未执行 / 缺口

- **跳过语义**：四个步骤均无独立「跳过」按钮，仅步骤 4（Cookie）文案写「先跳过也没问题」；`OnboardingGuard.tsx:16` 只对 Tauri 生效（`if (!isTauri) return <>{children}</>`），Web 构建不会因未完成首启被拦截。因此「跳过」在 Web 路径上不存在可执行入口，本轮标记 NOT APPLICABLE（产品现状），未以 synthetic 方式伪造通过。
- **真实外部依赖**：`connect_test` 用的是占位 API Key，业务码 200104；未调用真实模型厂商，连接成功与否不影响首启流程（源码 `OnboardingPage.tsx:146-152` 明确吞掉该错误）。
- **失败态**：本轮未重复制造 backend 宕机场景；此前轮次已记录「后端未运行 → 停留在『正在启动后端服务』→ 60s 后切失败页」。

## 4. 命令与结果

```
./node_modules/.bin/vitest run tests/onboardingTranscriber.test.ts
  → Test Files 1 passed (1) / Tests 9 passed (9), exit 0
./node_modules/.bin/tsc -b --noEmit
  → exit 0
./node_modules/.bin/eslint src/ember/pages/OnboardingPage.tsx \
    src/ember/pages/OnboardingGuard.tsx src/hooks/useCheckBackend.ts
  → exit 0
```

隔离 DB 检查、HTTP 探活、浏览器步骤均为本轮实际执行；无模拟数据冒充端到端。

## 5. 返工补验（rev 2，2026-11-09 21:20–21:22，隔离环境 3020/8490）

调度返工指令要求把「未执行真实凭据初始化」补掉，并把「跳过」按源码事实写成结论而非阻塞。本轮按该口径在隔离环境完整走通第 2–4 步。

环境：隔离 backend `BACKEND_PORT=8490`、`DATABASE_URL=sqlite:///.quarantine/t050-run/bili_note.db`（源 `orphan-T-052-1794220574030`，含真实 provider `kouri`）、隔离前端 `VITE_FRONTEND_PORT=3020`（`.env.local`，用后已还原）。转写配置在本次运行中临时切换为在线 ASR，用于邻近的 T-050 验证；本卡第 3 步保存的是 `openai-asr`。

| 步骤 | 操作 | 真实结果 |
|---|---|---|
| 1 backend ping | 打开 `http://127.0.0.1:3020/onboarding` | `GET /api/sys_check` HTTP 200，页面「后端已就绪，可以继续」；`localStorage` 初始为 `{}`（先 `localStorage.clear()` 以复现首启） |
| 2 供应商写入 | 填 `kouri` / `https://api.kourichat.com/v1` / 真实 Key（从隔离 DB 读取，不回显）/ `gpt-6-luna-codex` → 「保存并下一步」 | `POST /api/add_provider` **200**(10ms) → `GET /api/get_all_providers` **200**(5ms，同名已存在走复用) → `POST /api/update_provider` **200**(10ms) → `POST /api/models` **200**(7ms) → `POST /api/connect_test` **200**(16418ms)；随后进入步骤 3 |
| 3 转写器写入 | 选中「OpenAI 兼容 ASR（在线）」→ 「保存并下一步」 | `POST /api/transcriber_config` **200**(11ms)；进入步骤 4 |
| 4 完成 | 点「完成，进入 BiliNote」 | URL 变为 `/`（Workspace 渲染：单集/批量入口、生成设置、分组、空历史）；`localStorage = {"bilinote-onboarded":"1"}` |
| 刷新回显 | `F5` 重载 `/` | 仍停在 Workspace，未被引导拦截；`localStorage` 保持 `{"bilinote-onboarded":"1"}`，`location.pathname === "/"` |

隔离 DB 落库核对（`sqlite3` 直读，运行期）：`providers = [('kouri','https://api.kourichat.com/v1')]`、`models = [('gpt-6-luna-codex')]`、`general_settings.active = ('47bc11f4-1748-49c4-a1db-53ab21bd823b','gpt-6-luna-codex')`。

### 跳过语义（结论，非阻塞）

- `OnboardingPage.tsx` 四步流程**无独立「跳过」按钮**（仅有「上一步 / 下一步」与第 4 步的 `onboarding.finish`）；`strings.ts` 无 `onboarding.*skip*` 键。
- 唯一语义上的「跳过」出现在第 4 步 Cookie 的文案「先跳过也没问题」，其正常终止动作即 `onboarding.finish` 按钮 —— 也就是**由第 4 步完成承担**，不存在被绕过的独立入口。
- `OnboardingGuard.tsx:16-18` 只在 Tauri 下拦截（`if (!isTauri) return <>{children}</>`），因此 Web 构建下未完成首启也不会被守卫拦下；本卡在 Web 上以 `localStorage` 键 + 刷新行为作为等价回显证据。

### 本轮清理

- 停后端（PID 29344）与前端（PID 38356），`netstat` 确认 8490 / 3020 无 LISTENING。
- 删除 `.quarantine/t050-run/`；还原 `backend/config/transcriber.json`（`fast-whisper/tiny`）、`BillNote_frontend/.env.local`（`8484` / 3017）、删除临时根 `.env`。
- 主库 `backend/bili_note.db` mtime 未变（`2026-10-31 19:14:29`）；`git status --short` 无输出。
