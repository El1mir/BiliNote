# T-074 · 彻底移除 Tauri（W6）证据

基线：父分支 `flow/T-066`，本轮起点 `b665f8a`。Tauri 的主体移除在父分支早先的
`6fc8d80`（refactor: remove Tauri desktop target end to end）完成；本卡补完最后
三处不一致并复跑门禁。

## 验收 1 · 目录、依赖、脚本、版本来源

| 检查 | 命令 | 结果 |
|---|---|---|
| src-tauri 不存在 | `Test-Path BillNote_frontend/src-tauri` | False |
| @tauri-apps 依赖 / tauri 脚本 | `Select-String BillNote_frontend/package.json -Pattern tauri` | 0 行 |
| 版本来源 | `vite.config.ts:14` | `readFileSync(path.resolve(__dirname, 'package.json'))` |
| 版本兜底 | `vite.config.ts:11` | `fallbackVersion = '0.0.0'`，读不到 package.json 也不炸 |

`src-tauri/` 与依赖、脚本、`.env.tauri`、PyInstaller sidecar 的删除记录见
`CHANGELOG.md` 顶部「彻底移除 Tauri 桌面端」条目。

## 验收 2 · Router 与 grep 归零

```
git grep -c -i tauri -- BillNote_frontend/src        → 0
Select-String src / package.json / vite.config.ts    → 0
git grep -n -E 'HashRouter|__TAURI_INTERNALS__|isTauri' -- BillNote_frontend/src
```

Router 只剩 `BrowserRouter`（`EmberApp.tsx:2,45`）；`HashRouter` 分支与
`__TAURI_INTERNALS__` 检测已删除。

本卡顺手清掉三处「桌面/HashRouter」残留注释与一句过期文案（原以为桌面端会自动
拉起后端进程）：

- `src/ember/lib/taskUrl.ts`：说明改为「只经 useSearchParams，不依赖具体 Router」。
- `src/ember/features/reader/anchors.ts`、`MarkdownNote.tsx`：去掉 HashRouter 措辞。
- `src/ember/startup/StartupScreen.tsx`：桌面端专属路径的措辞改为桌面端已移除。
- `i18n strings.ts` 的 `onboarding.step1.description`（zh+en）：改成「后端需先启动
  （Docker / pnpm dev / 自己的部署）」。

仓库里仍出现 tauri 的只有历史文档与规格（`CHANGELOG.md`、`CLAUDE.md`、`README.md`
更新记录、`specs/`、`wayfinder/`、`docs/ui-audit/evidence/`），属「文档说明文字」，
按验收口径不计入。

## 验收 3 · 门禁（`BillNote_frontend/`，pnpm 10.10.0）

```
pnpm exec tsc -b            → exit 0
pnpm lint                   → exit 0
node scripts/i18n-contract.cjs → exit 0（572 keys）
pnpm build                  → exit 0（✓ built in 11.36s）
pnpm exec vitest run        → 30 files / 197 tests, exit 0
```

base 仍为 `/`（`vite.config.ts:38`），构建产物直接引用根路径：
`dist/index.html` → `<script src="/assets/index-*.js">`、`href="/icon.svg"`。

## 验收 4 · 文档口径

`README.md` 的「桌面版下载」整节替换为「部署形态」：Web（docker-compose 或
`pnpm dev`）+ 浏览器扩展（`BillNote_extension` 解包加载），并明确桌面版已移除
（`src-tauri/`、`@tauri-apps/*`、sidecar、安装包流水线不再存在）。历史版本说明保留在
「更新记录」与 `CHANGELOG.md`。
