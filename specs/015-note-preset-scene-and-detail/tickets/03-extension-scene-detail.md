# 03 · 浏览器扩展：两个下拉 + 设置项

- **依赖**：01（后端契约）
- **关联**：spec 015（§已定决策 6、7、9；§影响面）
- **状态**：resolved 2026-10-15

## 目标

扩展端的风格下拉从 9 项换成场景 / 详略两个下拉，设置页同步，请求体发 `scene` + `detail`。

## 背景

`BillNote_extension/src/logic/types.ts:95-105` 是三份拷贝里的第三份。扩展与 web 共用同一套 value，但各自维护常量（决策 6）。

## 改动点

1. `BillNote_extension/src/logic/types.ts`
   - L86-90 `NoteStyle` → `NoteScene`（`'life' | 'academic' | 'professional'`）与 `NoteDetail`（`'brief' | 'detailed'`）。
   - L95-105 `NOTE_STYLES` → `NOTE_SCENES` + `NOTE_DETAILS`。
   - L123 `GenerateRequest.style?: string` → `scene?: NoteScene` + `detail?: NoteDetail`。
   - `Settings`（L114+）里的 `style: NoteStyle` → `scene: NoteScene` + `detail: NoteDetail`。
   - L86 的注释「与 `backend/app/gpt/prompt_builder.py note_styles` 一一对齐」要改：那条路径已经不存在，改成指向 spec 015。
2. `BillNote_extension/src/popup/Popup.vue`：L7 import 改名；L204 的一个 `<option>` 列表 → 两个 `<select>`（场景 / 详略），默认值与 web 一致（`life` / `detailed`）。
3. `BillNote_extension/src/options/pages/General.vue`：L6 import 改名；L138-139 同样换成两个 `<select>`；保存到 `settings` 时写新字段。
4. 扩展的持久化里可能已有旧的 `settings.style`：读取时**忽略**（决策 4 不做映射），落到默认值即可。

## 验收

- `pnpm typecheck` 通过。
- `pnpm build` 通过，产物落在 `BillNote_extension/extension/`。
- `grep -rn "NOTE_STYLES\|NoteStyle" BillNote_extension/src` 无命中。
- 手动（`chrome://extensions/` 加载 unpacked）：popup 与设置页各出现两个下拉；发起一次生成，Network 里请求体是 `scene` / `detail`。

## 测试

- 扩展的 `package.json` 里 `"test": "vitest test"` 这条命令是坏的（子命令拼错），且 `BillNote_extension/tests/` 目录不存在 —— **本 ticket 不修这个**（超出 spec 015 边界），只记在这里。
- 因此扩展端的一致性由 01 的 `test_preset_vocabulary_sync.py` 覆盖：它直接读 `types.ts` 源码文本提取 value，与后端 key 集合比对。

---

## Comments

### 实施记录（2026-10-15）

| 文件（全部 **CRLF**） | 改动 |
| --- | --- |
| `BillNote_extension/src/logic/types.ts` | `NoteStyle` → `NoteScene` + `NoteDetail`；`NOTE_STYLES` → `NOTE_SCENES` + `NOTE_DETAILS`；`Settings.style` → `scene` + `detail`；请求 payload 类型的 `style?: string` → `scene?` + `detail?` |
| `src/logic/constants.ts` | `DEFAULT_SETTINGS`：`style: 'minimal'` → `scene: 'life'` + `detail: 'detailed'`（**决策 4：老 `settings.style` 直接忽略**） |
| `src/background/main.ts` | 离线生成请求体（L90）改成两条 |
| `src/popup/Popup.vue` | import(L7)、请求体(L83)、网格 `grid-cols-2` → `grid-cols-3`、「笔记风格」拆成两个下拉 |
| `src/options/pages/General.vue` | import(L6)、网格 `grid-cols-2` → `grid-cols-3`、同样拆成两个下拉 |

### `node_modules` 此前不存在

`BillNote_extension/node_modules` **在本次之前从未安装过**。已跑 `pnpm install --prefer-offline`（34.3s）后才做得动类型检查与构建。

### ⚠️ 偏差 1：ticket 写的验收项「`pnpm typecheck` 通过」**在改动前就不成立**

`cd BillNote_extension; pnpm typecheck`（= `tsc --noEmit`，见 `package.json:30`）结果：**18 条错误**，全部是 `TS2304: Cannot find name 'browser'` 与 `TS7006: Parameter ... implicitly has an 'any' type`，分布在：

- `src/background/contentScriptHMR.ts`（6 条）
- `src/background/main.ts`（11 条）
- `src/contentScripts/index.ts`（1 条）
- `src/logic/cookies.ts`（2 条）

根因是 `browser` 这个全局（来自 `webextension-polyfill`）的类型声明没有接进 `tsconfig`。**本次改动的四个文件（`types.ts` / `constants.ts` / `Popup.vue` / `General.vue`）零错误。**

这条不在 spec 015 的边界内（它是扩展脚手架的类型环境问题，与预设改造无关），**故本 ticket 不修**，仅记录在此。ticket 的这条验收项应视为**写错了**（拿一个改动前就红的命令当验收）。

### ⚠️ 偏差 2：不要用 `npx vue-tsc`

`npx vue-tsc --noEmit` 会失败：

- `Error [ERR_PACKAGE_PATH_NOT_EXPORTED]: Package subpath './lib/tsc' is not defined by "exports" in .../_npx/.../node_modules/typescript/package.json`

npx 缓存里拉到的 vue-tsc 3.x 与它自己装的 typescript 不兼容。**用仓库脚本 `pnpm typecheck`（`tsc --noEmit`）**，它用本地 `node_modules` 里的版本，正常工作。

### 验证证据

- `pnpm typecheck` → 见偏差 1（18 条既有错误，本次改动文件 0 条）。
- `pnpm build` → **exit 0**，产物落在 `BillNote_extension/extension/`：`dist/background/index.mjs` 35.43 kB（gzip 10.35 kB）、`dist/contentScripts/index.global.js` 87.07 kB（gzip 31.13 kB）、`dist/contentScripts/style.css` 4.10 kB。
- `grep -rn "NOTE_STYLES\|NoteStyle" BillNote_extension/src` → 无命中。

### 未做（诚实记录）

ticket 验收里的「`chrome://extensions/` 加载 unpacked、发起一次生成看 Network 请求体」**没有执行** —— 需要真人操作浏览器。构建产物与类型层面已覆盖；**扩展的实际运行行为未经人眼确认**。

## Answer

**已完成**。扩展的设置项与 popup / 设置页下拉都改成「笔记场景」+「笔记详略」，请求体发 `scene` / `detail`，老 `settings.style` 被忽略并落到默认值（life / detailed）。

两个偏差已在上文记录：验收项「`pnpm typecheck` 通过」在改动前就不成立（18 条既有的 `browser` 类型错误），本 ticket 不修；类型检查必须走 `pnpm typecheck` 而非 `npx vue-tsc`。
