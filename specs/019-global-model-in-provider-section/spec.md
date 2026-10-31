# 019 全局模型搬到「模型提供商」

> 状态：implemented（2026-10-18）
> 来源：用户需求（本轮 goal，m01128）——「全局模型在供应商那里被删掉了，但通用设置里『当前全局模型 / 未单独指定模型的任务使用该模型』这一项没有变化」、「**不要把这一项放在通用设置里**，改到『模型提供商』那里，在已激活（启用）的提供商里选一个全局模型」
> 关联：spec 017（Ember 重构——正是这次重构把激活入口弄丢了）；`backend/tests/013-global-active-model`（这个特性从来没有 spec，目录号与 spec 013 撞车，故本需求另起 019）

## 1. 背景

用户看到两件事，其实是两个独立缺陷：

1. **指针陈旧**：`app/services/active_model.py` 原来的 `get_active_model()` 只做「把库里两列读出来」，**不校验**。于是在供应商里把模型删掉（或把供应商停用）之后：
   - 设置页继续显示那个已经不存在的模型名；
   - 任务真的会拿这个模型名去请求网关，直到上游报错。
2. **位置不对 + 入口丢失**：通用设置里只有一个**只读** `Badge`（`GeneralSection.tsx:156-168`）。而 `src/services/general.ts` 早就写好了 `activateGlobalModel()` → `POST /general/active_model`，全仓却**没有任何 UI 调用它**；i18n 键 `settings.model.useAsGlobal` 也没有组件使用 —— 重构时把唯一入口丢了，这一项就永久只读。

## 2. 目标

- 全局模型的选择器住在「设置 → AI 模型设置（模型提供商）」页顶部，候选**只来自已启用供应商下的模型**。
- 通用设置里彻底移除这一项（不是隐藏，是删掉）。
- 失效指针自愈：模型被删 / 供应商被停用后，**读到的就是没有全局模型**，而不是一个陈旧名字。

## 3. 非目标

- 不改任务侧语义：没有全局模型时任务仍然拒绝入队并给出可读原因（现状保留）。
- 不做「每个任务单独挑模型」的新 UI（既有的 task 级 `model_name`/`provider_id` 不变）。
- 不引入多用户 / 权限概念。

## 4. 已定决策

| # | 决策 | 理由 |
| --- | --- | --- |
| 1 | 选择器放在**模型提供商页顶部**，不进通用设置 | 用户明确要求；这一项的定义就是「某个启用供应商下的某个模型」，和供应商列表放在一起才自洽 |
| 2 | 候选只含 **启用** 且 **有模型** 的供应商 | 停用供应商不会被真正调用，列进去等于给一个假选项；没有模型的供应商只是一个选不动的空分组 |
| 3 | 单个下拉，value = `providerId::modelName`，label = `供应商名 · 模型名` | 原生 select 只能存一维字符串；`::` 不会出现在 uuid 或模型名里，往返无损 |
| 4 | **选中即保存**，没有保存按钮 | 这一项只有一个值，多一次确认反而容易漏点 |
| 5 | 双入口：顶部下拉 + 展开的模型行内「设为全局模型」；命中行显示「全局」徽标 | 用户在浏览模型列表时的自然动线是「就在这一行点一下」 |
| 6 | 失效自愈分两处：`delete_model_by_id` 删除后**主动**清指针；`get_active_model()` 读时**被动**校验 | 主动清覆盖正常路径；被动校验覆盖老数据、手工改库、多进程/别的入口绕过钩子的情况 |
| 7 | 无全局模型时的消息统一为「尚未在模型提供商中激活全局模型」 | 旧文案「尚未在通用设置中激活 LLM 模型」指向已不存在的位置；`tests/013` 的 match 同步更新 |

## 5. 接口草案

`GET /api/general/active_model/options`（新增）

```json
{
  "code": 0,
  "data": {
    "active": { "provider_id": "ee09e49a-…", "model_name": "deepseek-v4.1-flash" },
    "providers": [
      {
        "provider_id": "ee09e49a-…",
        "provider_name": "kouri",
        "models": [{ "id": 4, "model_name": "deepseek-v4.1-flash" }]
      }
    ]
  }
}
```

- `active` 为 `null` 表示当前没有（或原指针已失效被清除）。
- `POST /api/general/active_model` 不变（`{provider_id, model_name}`）；它本来就有校验（供应商存在且 `enabled=1`、模型属于该供应商）。

## 6. 流程

1. 打开「AI 模型设置」→ 拉 options → 顶部卡片显示当前全局模型（徽标 + 下拉）或「尚未激活全局模型」。
2. 下拉选择或点行内「设为全局模型」→ POST → toast「已切换全局模型」→ 重新拉 options。
3. 删除某个模型 → 后端 `clear_active_model_if_matches()` 清指针 → 前端 `global.reload()` → 顶部回到「尚未激活全局模型」。
4. 老数据（库里仍指着已删模型）→ 第一次读 options 时被 `get_active_model()` 判失效、清库、返回 null。

## 7. 测试要点

**后端** `backend/tests/019-global-model-in-provider-section/test_global_model_options.py`（6 例）

- 候选只来自「启用且有模型」的供应商（停用供应商 / 空供应商都不出现）；
- 停用供应商下的模型名永远不会作为候选出现；
- `ModelService.delete_model_by_id()` 删掉全局模型 → 指针立即清空（`active_provider_id` 与 `active_model_name` 都是 None）；
- 绕过删除钩子直接改库 → 读路径自愈；
- 停用供应商使指针失效；
- `resolve_active_model()` 抛新文案。

**前端** `BillNote_frontend/tests/019-global-model-in-provider-section/globalModel.test.ts`（4 例）

- value 无损往返；空串 / 无分隔符 / 任一侧为空 → `null`；
- 候选按供应商顺序展开并跳过没有模型的供应商；
- 空输入 → 空数组。

**浏览器实测**（2026-10-18，headless Chromium 1181 + Vite 3015 + 后端 8483，真实库）

| # | 操作 | 观察 |
| --- | --- | --- |
| 1 | 打开 `/settings/model` | 顶部出现「全局模型」卡片；下拉候选只有 `kouri · deepseek-v4.1-flash`（`mimo` 未启用，不出现）；当前为「尚未激活全局模型」——库里那条指向已删模型的旧指针在读取时被清理，正是本需求要的行为 |
| 2 | 选中该模型 | `POST /api/general/active_model` → 200 `{"provider_id":"ee09e49a-…","model_name":"deepseek-v4.1-flash"}`；toast「已切换全局模型」；刷新后仍是该值 |
| 3 | 展开 kouri，新增 `verify-tmp-model`，点行内「设为全局模型」 | 该行出现「全局」徽标，顶部下拉同步为 `kouri · verify-tmp-model` |
| 4 | 删除 `verify-tmp-model` | 顶部立刻回到「尚未激活全局模型」，下拉 value 为空 —— 用户报的「删了还显示」复现失败（已修） |
| 5 | 重新选回 `deepseek-v4.1-flash` | 徽标恢复，值持久化 |
| 6 | 打开 `/settings/general` | 全页已无「当前全局模型」，也读不到「尚未启用任何模型」 |

浏览器 console 错误：0。

## 8. 实现清单

| 部件 | 文件 | 改动 |
| --- | --- | --- |
| 指针存储 | `backend/app/db/general_settings_dao.py` | 新增 `clear_active_model() -> bool`（两列写 NULL；无内容时返回 False，避免无意义写库） |
| 指针服务 | `backend/app/services/active_model.py`（重写） | `_model_still_exists()`（供应商存在 + `enabled==1` + 模型在该供应商下）；`get_active_model()` 校验失败即清库 + warning；`clear_active_model_if_matches()`；`list_global_model_options()`；常量 `NO_ACTIVE_MODEL_MESSAGE` |
| 模型仓储 | `backend/app/db/model_dao.py` | 新增 `get_model_by_id()`（删之前先记住删的是谁） |
| 模型服务 | `backend/app/services/model.py` | `delete_model_by_id()` 删除后调 `clear_active_model_if_matches()` |
| 路由 | `backend/app/routers/general.py` | 新增 `GET /general/active_model/options` |
| 后端测试 | `backend/tests/019-global-model-in-provider-section/` | 6 例（见 §7）；同步修 `backend/tests/013-global-active-model/test_global_active_model.py:40` 的旧文案，并给 `backend/tests/009-…/test_batch_grouping.py` 的 fixture 补真实 Provider/Model 行（旧 fixture 只写 GeneralSettings，在新校验下等于失效指针） |
| 取值工具 | `BillNote_frontend/src/utils/globalModel.ts`（新建） | `GLOBAL_MODEL_SEPARATOR` / `globalModelValue` / `parseGlobalModelValue` / `buildGlobalModelOptions` |
| 前端测试 | `BillNote_frontend/tests/019-global-model-in-provider-section/globalModel.test.ts` | 4 例 |
| 服务层 | `BillNote_frontend/src/services/general.ts` | 新增 `getGlobalModelOptions()` + 三个类型；从 `GeneralSettings` 里删掉 `active_provider_id`/`active_model_name`（不再由通用设置渲染） |
| 选择器 | `BillNote_frontend/src/ember/pages/settings/sections/GlobalModelPicker.tsx`（新建） | 展示型组件：徽标 + `Select data-testid="global-model-select"` + 提示；无候选时只显示「先启用一个服务商并添加模型」 |
| 挂载 | `BillNote_frontend/src/ember/pages/settings/sections/ModelSection.tsx` | 拉 options、`selectGlobal()`、在供应商列表前渲染选择器；`onChanged` 里额外 `global.reload()` |
| 行内入口 | `BillNote_frontend/src/ember/pages/settings/sections/ProviderModels.tsx` | 新增 `activeModelValue`/`onActivate`；命中行显示「全局」徽标，否则显示「设为全局模型」 |
| 移除旧位置 | `BillNote_frontend/src/ember/pages/settings/sections/GeneralSection.tsx` | 删除 activeModel 的 `SettingRow` 与 `Badge` import |
| 文案 | `BillNote_frontend/src/ember/i18n/strings.ts` | 删 `settings.general.activeModel/activeModelHint/noActiveModel`（中英）；新增 `settings.model.globalTitle/globalHint/globalNone/globalEmpty/globalSaved/globalBadge`（中英） |
| 前端类型范围 | `BillNote_frontend/tsconfig.app.json` | `include` 由 `["src"]` 改为 `["src", "tests"]`：此前 `tests/` 不属于任何 tsconfig project，LSP 解析不到 `@/` 别名，每个用别名的测试文件都报假错 2307（vitest 自带别名、`tsc -b` 又不含 tests，所以一直没人发现） |

## 9. 验证记录

- 后端：`.venv/Scripts/python.exe -m pytest -q` → **925 passed**（含 019 的 6 例；013 的 4 例文案同步后仍全绿）。
- 前端：`pnpm exec tsc -b` exit 0；`pnpm vitest run` → 8 files / **38 passed**；`pnpm lint` exit 0；`pnpm build` ✓ built in 32.88s。
- 浏览器：见 §7 表（6 步，逐张截图人工复核：`02-model-after.png`、`05-tmp-is-global.png`、`06-after-delete.png`、`07-restored.png`、`04-general.png`；截图是本次会话的临时产物，未入库）。
- 线上接口：`GET /api/general/active_model/options` → `{"active":{"provider_id":"ee09e49a-3d3e-417b-8b30-30f34dbf0818","model_name":"deepseek-v4.1-flash"},"providers":[{"provider_name":"kouri",…}]}`。
- 收尾复核（2026-10-18，全量重跑）：后端 `pytest -q` → 925 passed（85.37s）；前端 `pnpm exec tsc -b` exit 0、`pnpm vitest run` → 38 passed、`pnpm lint` exit 0。改完 `tsconfig.app.json` 后 `tsc -b` 仍然 exit 0（tests 纳入类型检查后没有新错）。
- 后端已重启到当前代码（端口 8483，监听 PID 64732，由 `Start-Process` 的 63076 拉起）；重启后 `GET /api/general/active_model/options` 200 且 `active.model_name = deepseek-v4.1-flash`。
- 重启后再次截图人工复核「AI 模型设置」页（`verify-019-final.png`）：全局模型卡片在供应商列表之前，徽标与下拉同值 `kouri · deepseek-v4.1-flash`，提示行「未单独指定模型的任务使用该模型；候选只列已启用服务商下的模型」，下方 kouri 已启用 / mimo 未启用 —— 与改动前设计的版式一致。
- 最后一次收尾把「假阻塞项」清零了：前端 4 个测试文件（005/010/018/019）的 `@/utils/*` 改成相对导入 `../../src/utils/*`（与 `tests/001-…/range.test.ts` 的既有写法一致，不依赖 tsconfig 才能被 LSP 解析）；`backend/tests/009-…/test_batch_grouping.py` 的 `_task_rows` 由 `session.query(VideoTask).all()` 改为 `session.execute(select(VideoTask)).scalars().all()`（语义等同，躲开静态规则对 ORM `.query()` 的 SQL 注入误判）。改完复跑：后端 `pytest -q` → 925 passed（84.24s），前端 `vitest run` → 38 passed、`tsc -b` exit 0，`lens_diagnostics mode=all` → **0 阻塞项**（55 个文件）。
- 类型层告警（非运行期缺陷）的处置：SQLAlchemy 声明式列在 Pyright 眼里是 `Column[str]/Column[int]`，直接属性读写会被判成类型错误，而 ruff 的 B009/B010 又禁止对常量属性名用 `getattr/setattr`。最终写法是 `cast(int, provider.enabled)` / `cast(str, provider.id)` + 只有确实需要绕开 `Column` 赋值时才用 `setattr` 并附 `# noqa: B009/B010` 与理由注释。顺手修掉 `backend/app/services/model.py` 里三处既有的同类报错（`get_model_list` 的 `provider_id: int | str`、`result: dict[str, Any]`、`model=str(model or "")`）。

## 10. 已知取舍 / 后续

- 后端**没有 `--reload`**：改后端代码必须杀端口监听进程再重启（`main.py` 会 fork 出 uv 托管的 cpython-3.11.11 子进程，**子进程才是监听者**）。本次验证中因为残留进程没杀干净，一度看到「import 已修但接口仍 500」的假象。
- 该仓库保存 Python 文件后会自动跑 ruff（含未用导入清理）：**先写使用方，再补 import**，否则新增的 import 会被删掉，运行期才炸 NameError。
- 选择器目前是「供应商 → 模型」拍平的一层下拉。供应商/模型数量再上一个量级（比如 >30 家）时值得换成两段式（先选供应商再选模型）或可搜索的 Combobox。
- 读路径自愈是**懒**的：只有 `get_active_model()` 被调用时才发现指针失效并清库。删模型这条路径已经同步清（`delete_model_by_id`），但「绕过服务层直接改库」只能等下一次读。要更实时就得在供应商停用/删除处逐个挂钩子，代价是每个写路径都要记住这件事。
- `backend/pyrightconfig.json` 没有为 SQLAlchemy 模型放宽 `reportAttributeAccessIssue/reportArgumentType`，所以每碰一个 DAO 都要 `cast` 或 `# noqa`。彻底解法是给 `app/db/models/*` 装 `Mapped[...]` 注解（SQLAlchemy 2.0 风格），但那要动全部模型定义与查询，超出本次范围。
