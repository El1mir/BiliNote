# 021 · W7 集成验收门禁记录

日期：2026-11-11 · 卡：T-075 · 分支 flow/T-066 · 基线提交 f657ab2

所有命令都在本 worktree（`C:/Users/Administrator/Desktop/prjs/.flow-worktrees/BiliNote/T-066`）内执行，结果的 exit code 与摘要如下。

## 环境准备

- worktree 目录曾只剩一个 `.env`（git 元数据丢失）：备份 `.env` → 删除目录 → 主仓库 `git worktree add <path> flow/T-066` → 还原 `.env`。
- `BillNote_frontend`：`pnpm install --frozen-lockfile` → exit 0（11.6s）。
- `BillNote_extension`：`pnpm install --frozen-lockfile` → exit 0（8s）。

## 前端（BillNote_frontend）

| 命令 | exit | 输出摘要 |
|---|---|---|
| `pnpm exec vitest run` | 0 | Test Files 30 passed (30) · Tests 197 passed (197) · Duration 5.18s |
| `pnpm exec tsc -b` | 0 | 无诊断输出 |
| `pnpm lint` | 0 | `eslint .` 无 error / warning |
| `node scripts/i18n-contract.cjs` | 0 | `i18n contract OK — 572 keys, zh-CN and en-US aligned` |
| `pnpm build` | 0 | `✓ built in 10.74s`；仅有 rollup chunk-size 提示，非失败 |

## 扩展（BillNote_extension）

| 命令 | exit | 输出摘要 |
|---|---|---|
| `pnpm typecheck` | 0（修复后） | 见下「typecheck 修复」 |
| `pnpm exec vitest run`（`CI=1`） | 0 | Test Files 4 passed (4) · Tests 10 passed (10) · Duration 3.09s |
| `pnpm build` | 0 | `✓ built in 1.03s`，产物写 `../extension/dist/{background,options,popup,sidepanel}` |
| `pnpm test:e2e`（`CI=1`） | **1（红）** | 3 failed：`basic.spec.ts:3` example test、`:12` popup page、`:17` options page |

### typecheck 修复（合并后暴露）

首跑 exit 2：

```
src/logic/cookies.ts(15,19): error TS7006: Parameter 'c' implicitly has an 'any' type.
```

根因：`BillNote_extension/tsconfig.json` 的 `compilerOptions.types` 只有 `["vite/client"]`，`@types/webextension-polyfill` 的全局 `browser` 声明因此不在 program 里（TypeScript 5.5.4，与前序卡同一把锁）。验证：

```
pnpm exec tsc --noEmit --types "vite/client,webextension-polyfill"   # exit 0
pnpm exec tsc --noEmit --types webextension-polyfill                # exit 2（缺 vite/client）
```

修复：`tsconfig.json` 的 `types` 增加 `"webextension-polyfill"`（本卡提交，无运行时行为变化）。

### test:e2e 红的原因

1. `@playwright/test@1.46.1` 需要 chromium-1129；本机 `%LOCALAPPDATA%/ms-playwright` 无该版本。`pnpm exec playwright install chromium` 跑到 40 分钟仍无任何输出（下载未完成），已终止。
2. 为取出真实失败原因，把本机已装的 chromium-1181 复制为 chromium-1129 目录后复跑（版本替代，见下方偏差），得到的是**用例本身过期**：

```
basic.spec.ts:14  await expect(page.locator('button')).toHaveText('Open Options')
basic.spec.ts:19  await expect(page.locator('img')).toHaveAttribute('alt', 'extension icon')
```

这两个断言来自 vitesse-webext 模板脚手架（`e2e/basic.spec.ts` 自 b8f359e 起未改过），而 popup / options 已在 spec 017 整体重写为 BiliNote 界面，不再有「Open Options」按钮与模板 logo。属于**陈旧用例**，不是本次重绘引入的回归。

未在本卡修 e2e（scope 为证据与文档；测试改写走修复卡，建议：删除模板断言、改为断言 popup 的「生成笔记」按钮与 options 的「后端地址」卡片）。补跑命令：

```
pnpm exec playwright install chromium
CI=1 pnpm test:e2e
```

## 收口轮复跑（同一 worktree，HEAD f657ab2，T-075 最后一轮）

在把 W7 工件提交前重跑一遍，确认数字与上文记录一致（下表为复跑实测，不是引用上一轮）：

| 命令 | exit | 输出摘要 |
|---|---|---|
| `pnpm exec vitest run`（BillNote_frontend） | 0 | Test Files 30 passed · Tests 197 passed |
| `pnpm exec tsc -b` | 0 | `TypeScript: No errors found` |
| `pnpm lint` | 0 | `ESLint: No issues found` |
| `node scripts/i18n-contract.cjs` | 0 | `i18n contract OK — 572 keys, zh-CN and en-US aligned` |
| `pnpm build` | 0 | `✓ built in 14.96s`（仅 rollup chunk-size 提示） |
| `pnpm typecheck`（BillNote_extension） | 0 | `tsc --noEmit` 无诊断 |
| `CI=1 pnpm exec vitest run` | 0 | Test Files 4 passed · Tests 10 passed |
| `pnpm build` | 0 | `✓ built in 1.48s` |

`test:e2e` 本轮未复跑：浏览器版本缺失的阻塞与上一轮相同，结论维持「红 / BLOCKED」，见下节。

## 对比度审计输出（原文粘贴）

命令：`node docs/ui-audit/021/contrast-audit.mjs` · exit 0 · 结论 `Result: all pairs pass`（13 对 × 2 主题；正文 ≥4.5:1、非文本控件 ≥3:1）。

```
## light
| pair | ratio | required | verdict | role |
|---|---|---|---|---|
| ink on canvas | 15.11:1 | 4.5:1 | PASS | body text on the page |
| ink on surface | 16.38:1 | 4.5:1 | PASS | body text on a card |
| ink on raised | 15.94:1 | 4.5:1 | PASS | body text on a raised panel |
| ink-soft on surface | 6.42:1 | 4.5:1 | PASS | secondary text |
| ink-muted on canvas | 4.93:1 | 4.5:1 | PASS | muted helper text |
| ink on accent-soft | 14.45:1 | 4.5:1 | PASS | current nav item text |
| on-accent on accent | 5.55:1 | 4.5:1 | PASS | label on a solid accent button |
| success on surface | 5.41:1 | 4.5:1 | PASS | success text |
| warning on surface | 5.34:1 | 4.5:1 | PASS | warning text |
| danger on surface | 6.57:1 | 4.5:1 | PASS | error text |
| info on surface | 5.77:1 | 4.5:1 | PASS | info text |
| line-strong on surface | 3.40:1 | 3:1 | PASS | control border (non-text) |
| accent on surface | 5.55:1 | 3:1 | PASS | focus ring / accent marks (non-text) |

## dark
| pair | ratio | required | verdict | role |
|---|---|---|---|---|
| ink on canvas | 16.23:1 | 4.5:1 | PASS | body text on the page |
| ink on surface | 14.69:1 | 4.5:1 | PASS | body text on a card |
| ink on raised | 13.02:1 | 4.5:1 | PASS | body text on a raised panel |
| ink-soft on surface | 10.19:1 | 4.5:1 | PASS | secondary text |
| ink-muted on canvas | 6.88:1 | 4.5:1 | PASS | muted helper text |
| ink on accent-soft | 12.47:1 | 4.5:1 | PASS | current nav item text |
| on-accent on accent | 8.18:1 | 4.5:1 | PASS | label on a solid accent button |
| success on surface | 7.95:1 | 4.5:1 | PASS | success text |
| warning on surface | 10.19:1 | 4.5:1 | PASS | warning text |
| danger on surface | 7.28:1 | 4.5:1 | PASS | error text |
| info on surface | 9.02:1 | 4.5:1 | PASS | info text |
| line-strong on surface | 3.89:1 | 3:1 | PASS | control border (non-text) |
| accent on surface | 7.87:1 | 3:1 | PASS | focus ring / accent marks (non-text) |

Result: all pairs pass
```

后续复核以本段输出为准；`contrast.txt` 是同一脚本早先一次运行的落盘副本。

## 交付树复跑（HEAD d82c628，W7 工件全部入库后）

在提交了 W7 证据的树上再跑一遍，确认已提交状态与门禁一致（命令与 exit 全部为本次实测）：

| 命令 | exit | 输出摘要 |
|---|---|---|
| `pnpm exec vitest run`（BillNote_frontend） | 0 | Test Files 30 passed (30) · Tests 197 passed (197) · Duration 8.37s |
| `pnpm exec tsc -b` | 0 | 无诊断 |
| `pnpm lint` | 0 | `eslint .` 无 error / warning |
| `node scripts/i18n-contract.cjs` | 0 | `i18n contract OK — 572 keys, zh-CN and en-US aligned` |
| `pnpm build` | 0 | `✓ built in 18.18s`（仅 rollup chunk-size 提示） |
| `pnpm typecheck`（BillNote_extension） | 0 | `tsc --noEmit` 无诊断 |
| `CI=1 pnpm exec vitest run` | 0 | Tests 10 passed (10) · Duration 4.55s |
| `pnpm build`（BillNote_extension） | 0 | `✓ built in 1.66s`，产物写 `../extension/dist` |
| `pnpm test:e2e` | 未复跑 | 环境阻塞未变（chromium-1129 缺失、官方下载无进展）；结论维持红 / BLOCKED，见上节 |

截图与对比度证据未重拍：本轮只验证已提交树的门禁可复现，产物字节未变。

## 偏差与限制

- e2e 的浏览器是 chromium-1181 复制成 chromium-1129 目录后运行的（Playwright 版本检查通过，协议兼容）；这是**本机环境替代**，CI 上仍应安装官方 chromium-1129。
- `pnpm exec playwright install chromium` 在本机不可用（无输出、无进展），未在 CI 验证。
- 浏览器截图与扩展截图用的是 mock 后端（见 `w7-acceptance.md`），不能替代真实后端生成链路。

## 遗留：CI 复跑扩展 e2e（官方 chromium-1129）

记录于 2026-11-11，来源 T-077。上一节「test:e2e 未复跑 / 红」的结论已被 T-076 的重写与本机复跑取代，但**仍缺官方浏览器环境下的复跑**，故保留此债务。

### 已经做的

- T-076（提交 `532fc7e`）改写 `BillNote_extension/e2e/basic.spec.ts`：删 `example test`（断言模板 `Vitesse WebExt` h1），popup 断言真实「生成笔记」按钮，options 断言「后端地址」标题与「模型供应商」导航；模板断言 `Open Options` / `extension icon` 已不存在。
- 本机 `CI=1 pnpm test:e2e` → **2 passed (17.3s)，exit 0**。

### 本机替代做法（为什么本机结果不等于 CI 结果）

- `@playwright/test@1.46.1` 固定要求 `chromium-1129`；本机 `%LOCALAPPDATA%/ms-playwright` 只有 chromium 1169/1181/1208/1234/1248。
- `pnpm exec playwright install chromium` 在本机长期无进展（40 分钟无输出，已终止）。
- 为拿到真实用例结果，把已装 `chromium-1181` 目录**复制**为 `chromium-1129`，于是 Playwright 版本检查通过、协议兼容，用例得以执行；跑完即删除该替代目录，不入库。
- 因此本机 `2 passed` 只证明**用例断言正确、可执行**，不证明 CI 环境等价：浏览器内核版本不同（1181 vs 1129），扩展 API 行为、`--headless=new` 与 MV3 service worker 时序都可能有差异。

### CI 动作（最终判据）

```
cd BillNote_extension
pnpm install --frozen-lockfile
pnpm exec playwright install chromium        # 必须装到官方 chromium-1129
pnpm build                                  # e2e 读 extension/ 产物
CI=1 pnpm test:e2e                          # 以退出码与用例数为准
```

判定口径：官方 chromium-1129 上 `2 passed` 且 exit 0 才算 e2e 门禁闭合；若红，贴完整失败栈，不得以本机替代运行的结果视为通过。

### 当前状态

| 项 | 状态 |
|---|---|
| 用例断言 | 已修正（T-076，`532fc7e`） |
| 本机运行（chromium-1181 替代） | 2 passed，exit 0 |
| 官方 chromium-1129 复跑 | **未做（BLOCKED：本机无法安装该版本）** |
| CI 上的最终复跑 | 待 CI 安装官方 chromium-1129 后执行 |