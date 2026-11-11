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
## 第二轮补充（m06424）：残留清点、Web 发布流水线、死依赖

### 1. 残留清点（命令与结果）

```
git grep -il tauri                    # 只剩文档与历史材料
git grep -n -i -E 'tauri' -- BillNote_frontend/src   # 0
Select-String BillNote_frontend/package.json -Pattern tauri   # 0
Select-String BillNote_frontend/pnpm-lock.yaml -Pattern tauri # 0
git grep -n -E 'HashRouter|__TAURI_INTERNALS__|isTauri' -- BillNote_frontend/src  # 0
```

仍出现 `tauri` 的位置（全部属于「CHANGELOG / 迁移说明 / 历史证据」）：

| 文件 | 性质 |
|---|---|
| `CHANGELOG.md`、`README.md` 更新记录、`CLAUDE.md` | 迁移说明与历史记录 |
| `backend/main.py:95` | 注释：「桌面端（Tauri）已移除 … 不再放行」 |
| `backend/tests/014-*` 的 after-result / make_after_report | 历史测量报告快照 |
| `docs/ui-audit/evidence/*`、`docs/ui-audit/t072-*`、`docs/ui-audit/t074-*` | 历史证据 |
| `specs/005`、`specs/014`、`specs/017`、`specs/018`、`specs/021`、`wayfinder/*` | 历史规格 |

不存在 `src-tauri/`、`@tauri-apps/*`、`tauri.localhost` 的代码或配置引用；Router 只有
`BrowserRouter`（`EmberApp.tsx:2,45`）。

### 2. Web 发布流水线

新增 `.github/workflows/release-web.yml`：`v*` tag 或 `workflow_dispatch` 触发。

- pnpm 10 + Node 20，`pnpm install --frozen-lockfile`，`VITE_APP_VERSION` 由 tag 推导
  （无 tag 落 `0.0.0`）。
- `pnpm build` 后把 `dist` 打成 `bilinote-web-X.Y.Z.tar.gz`，`actions/upload-artifact@v4`
  上传；tag 触发时 `softprops/action-gh-release@v2` 挂到对应 Release。
- 后端镜像仍由既有 `docker-build.yml` 发布到 `ghcr.io/<repo>:X.Y.Z`，插件由
  `release-extension.yml` 发布；README「发布产物」表与 `RELEASING.md` 第 4 节同步列出。

校验：`yaml.safe_load` 解析通过（jobs=build-web，steps=10）；本机无 Actions runner，
流水线未在 CI 上实跑，只做了 YAML 解析 + 本机 `pnpm build` 对等命令验证。

### 3. 死依赖

```
cd BillNote_frontend && pnpm remove react-medium-image-zoom
# dependencies: - react-medium-image-zoom 5.4.1   exit 0
git grep -n 'react-medium-image-zoom'   # 只剩 MarkdownNote.tsx:144 说明注释与文档/历史规格
```

`package.json` −1 行、`pnpm-lock.yaml` −14 行；`MarkdownNote.tsx:144` 的注释保留（说明
灯箱为什么不再用该库）。

### 4. 门禁（第二轮，`BillNote_frontend/`）

```
pnpm exec tsc -b            → 0
pnpm lint                   → 0
node scripts/i18n-contract.cjs → 0（572 keys）
pnpm exec vitest run        → 30 files / 197 tests, 0
pnpm build                  → 0（✓ built in 10.38s）
```
