# Chinese and English i18n contract

- Type: task
- Status: implemented（新前端全量收口 + 契约闸门落地；扩展端文案仍为中文，见「仍未做」）
- Depends on: 001-capability-inventory-and-information-architecture
- Blocks: frontend shell and settings migration

## Question（原始问题，保留）

Decide translation namespace structure, locale persistence and fallback, backend error message keys, pluralization/date/number rules, generated-content boundary, accessibility labels, and how long English strings are tested against responsive layouts.

## 已定决策

### 1. 命名空间：扁平 + 前缀

`BillNote_frontend/src/ember/i18n/strings.ts` 里每个语言是一份**扁平**字典，键用点分前缀分组：
`app.*` / `nav.*` / `common.*` / `workspace.*` / `batch.*` / `history.*` / `reader.*` / `chat.*` / `settings.*` / `startup.*` / `onboarding.*` / `poll.*` / `note.*` / `serverError.*` / `platform.*` / `notFound.*`。

理由：查表 O(1)；缺键在 review 里一眼可见（相邻行就是同族文案）；嵌套对象会让「哪个键不存在」变成运行时问题。代价是键名较长，靠前缀保证可发现性。

### 2. 类型安全：由 zh-CN 定义键集

```ts
export type MessageKey = keyof typeof zhCN
export type Dictionary = Record<MessageKey, string>
export const dictionaries: Record<Locale, Dictionary> = { 'zh-CN': zhCN, 'en-US': enUS }
```

`Dictionary` 让 en-US **少一个键就编译失败**（这是类型系统能保证的那一半）；多的键同样是错误。另一半（占位符对不上、英文值仍是中文、空值）类型系统看不见，交给下面的闸门。

### 3. 语言持久化与回退

- 存储键 `bilinote-locale`（localStorage），只认 `'en-US'`，其余一律 `'zh-CN'`；
- `localStorage` 被禁用时回退 `'zh-CN'` 且**不抛错**（隐私模式下引导流程不能被锁死）；
- Provider 在 `locale` 变化时同步 `document.documentElement.lang`；
- 查不到的键回退成**键名本身**（`dictionary[key] ?? key`），绝不抛错 —— 界面上出现 `settings.foo` 比白屏好排查。

### 4. React 之外也要能翻译

保留的数据层（`src/services`、`src/hooks`、`src/store`）在普通模块里发 toast，没有组件上下文：

```ts
export function translate(key: MessageKey, values?): string
```

它从**同一个** localStorage 键读语言，所以和 Provider 不会漂移。`src/hooks/useTaskPolling.ts`、`src/services/note.ts`、`src/utils/request.ts` 都改走它。

### 5. 后端错误 → 用户语言：按 `data.reason` 查表，不匹配文案

`src/utils/request.ts` 维护 `REASON_KEYS`：

| reason | key |
| --- | --- |
| `task_in_progress` | `serverError.taskInProgress` |
| `insufficient_disk_space` | `serverError.insufficientDiskSpace` |
| `transcriber_model_not_ready` | `serverError.transcriberNotReady` |
| `already_generated` | `serverError.alreadyGenerated` |
| `group_create_failed` | `serverError.groupCreateFailed` |
| `provider_name_exists` | `serverError.providerNameExists` |
| `model_name_exists` | `serverError.modelNameExists` |

查不到 reason 才回退后端原文 —— 回退原文总比吞掉错误强。

**反面教材（已修）**：onboarding 曾用 `errorText(e).includes('已存在')` 判断供应商重名。三个后果：

1. 判定绑死中文文案，后端改字即静默失效；
2. 英文界面被迫保留 `onboarding.error.existsMarker` 这个「不许翻译」的键；
3. **模型重名分支从来匹配不上** —— `POST /models` 无论重名还是其它失败都只回「模型添加失败」，于是模型已存在会把整个引导步骤判为失败。

修法：后端 `app/routers/provider.py` 重名时回 `code=400, data={'reason': 'provider_name_exists'}`（异常类型 `ProviderNameExistsError(ValueError)`，保持既有 `except ValueError` 语义）；`app/routers/model.py` 改用 `ModelService.create_model_outcome()` 返回 `created` / `exists` / `provider_missing` / `failed`，重名回 `data={'reason': 'model_name_exists'}`。前端 `OnboardingPage.tsx` 改用 `errorReason(e) !== 'provider_name_exists'`。契约由 `backend/tests/017-web-rebuild-and-architecture/test_error_reason_contract.py`（6 条）钉住。

### 6. 占位符与复数

统一 `{name}` 语法，`format(template, values)` 做单次替换。**不做 ICU 复数**：本项目所有计数文案都能用「{count} 个任务」/「{count} task(s)」表达，引入 ICU 会为一个不存在的需求付运行时与心智成本。日期与数字走 `Intl`（`Intl.RelativeTimeFormat` 在 `src/ember/features/workspace/TaskList.tsx`，`toLocaleString` 在设置页）。

### 7. 生成内容边界：只翻译界面，不翻译笔记

LLM 生成的笔记正文、转写文本、任务标题一律**原样展示**，不进字典。界面文案与用户内容混译会把「笔记里出现了英文」误判成漏译。

### 8. 无障碍标签也算文案

`aria-label`、`title`、`alt` 全部走 `t()`：`src/ember/ui/Dialog.tsx`、`src/ember/ui/Drawer.tsx`（`common.close`）、`src/ember/shell/AppShell.tsx`（`openNav`）。扫描脚本会把这些漏网之鱼一起抓出来。

### 9. 契约闸门

`BillNote_frontend/scripts/i18n-contract.cjs`（`pnpm test:i18n`）在类型检查之外再抓三类只有运行时才暴露的问题：

1. **占位符不匹配** —— en 写 `{second}` 而 zh 写 `{seconds}`，界面会把花括号原样打印出来；
2. **英文值仍是中文** —— 复制粘贴没翻译（en 值与 zh 值相同且含中日韩字符）；
3. **空值** —— 键在但渲染为空。

顺带做键集双向对比（缺键/多键）。实现用 Node ≥ 22.6 的 TS 类型剥离直接 `import()` 那个 `.ts`，不引入构建步骤。这个闸门第一次跑就抓到 `onboarding.error.existsMarker` 在英文里仍是「已存在」—— 正是第 5 节那个不许翻译的键，现已删除。

### 10. 英文长文案的响应式验证

英文比中文长 1.5–2 倍，是布局最容易破的语言。`BillNote_frontend/scripts/ember-en-shots.cjs` 在 3 视口 × 4 路由（1440×900 / 834×1112 / 390×844 × 工作区、general、download、monitor）下把 `localStorage.bilinote-locale` 预置成 `en-US`，每张图统计 `overflowX` 与 main 内是否残留中日韩字符。

## 实现清单

- [x] 扁平字典 + `MessageKey` 类型约束（350 键，zh/en 对齐）
- [x] 语言持久化 `bilinote-locale` + 回退 + `documentElement.lang` 同步
- [x] `translate()` 供非 React 模块使用（轮询、服务层、axios 拦截器）
- [x] 后端错误结构化 `data.reason` + 前端 `REASON_KEYS` 查表
- [x] `src/ember` 内硬编码中文清零（`scripts/scan-cjk.cjs`：仅剩 `useEmberNav.ts` 的 zh/en 三元与 `LanguageSwitcher` 的切换标签，属刻意双语）
- [x] 契约闸门 `scripts/i18n-contract.cjs` + `pnpm test:i18n`
- [x] 无障碍标签走 `t()`
- [x] 英文 × 三视口截图脚本 `scripts/ember-en-shots.cjs`
- [ ] 扩展端（`BillNote_extension`）文案仍为中文；扩展是独立 UI，本 spec 不动它，若要跟随语言需另开 ticket

## 待确认问题

- 扩展端是否要跟随语言？（当前不动：扩展有独立的 popup/options UI，接 i18n 需要它自己的字典与持久化，属于另一个交付面。）
- 是否要第三种语言？字典结构（扁平 + 键集由 zh-CN 定义）支持直接加，但目前没有需求。
