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

## 偏差与限制

- e2e 的浏览器是 chromium-1181 复制成 chromium-1129 目录后运行的（Playwright 版本检查通过，协议兼容）；这是**本机环境替代**，CI 上仍应安装官方 chromium-1129。
- `pnpm exec playwright install chromium` 在本机不可用（无输出、无进展），未在 CI 验证。
- 浏览器截图与扩展截图用的是 mock 后端（见 `w7-acceptance.md`），不能替代真实后端生成链路。