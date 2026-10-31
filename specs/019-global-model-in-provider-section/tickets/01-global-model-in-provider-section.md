# 019-01 全局模型选择器搬到模型提供商页

> 状态：resolved（2026-10-18）
> 依赖：无（spec 017 的既有重构产物）
> 关联 spec 章节：§2 目标、§4 已定决策 1–7、§5 接口草案、§7 测试要点、§8 实现清单

## 目标

把「全局模型」从只读的通用设置行，变成一个**可操作**的选择器，落在「AI 模型设置（模型提供商）」页；并保证指针失效（模型被删 / 供应商停用）时不会继续冒充有效值。

## 改动点

### 后端

1. `app/db/general_settings_dao.py`
   - 新增 `clear_active_model() -> bool`：两列写回 `None`；本来就没有内容时返回 `False`（不白写一次库）。
2. `app/services/active_model.py`（重写，29 → 107 行）
   - `_model_still_exists(provider_id, model_name)`：供应商存在 + `enabled == 1` + 模型在该供应商的模型列表里。
   - `get_active_model()`：校验不过 → `_clear_active_model()` + `logger.warning("全局模型已失效并清除：provider=… model=…")` + 返回 `None`。
   - `clear_active_model_if_matches(provider_id, model_name) -> bool`。
   - `list_global_model_options()`：只含 `get_enabled_providers()` 里**有模型**的供应商。
   - `NO_ACTIVE_MODEL_MESSAGE = "尚未在模型提供商中激活全局模型"`。
3. `app/db/model_dao.py`：新增 `get_model_by_id(model_id)`。
4. `app/services/model.py`：`delete_model_by_id()` 先 `get_model_by_id` 记住是谁，删完 `clear_active_model_if_matches(...)`。
5. `app/routers/general.py`：新增 `GET /general/active_model/options`。
6. 测试：新增 `tests/019-global-model-in-provider-section/test_global_model_options.py`（6 例）；改 `tests/013-global-active-model/test_global_active_model.py:40` 的 match；给 `tests/009-batch-grouping-and-long-run-robustness/test_batch_grouping.py` 的 fixture 补真实 `Provider`/`Model` 行。

### 前端

1. `src/utils/globalModel.ts`（新建）：`GLOBAL_MODEL_SEPARATOR='::'`、`globalModelValue`、`parseGlobalModelValue`、`buildGlobalModelOptions`。
2. `src/services/general.ts`：新增 `getGlobalModelOptions()`、`GlobalModelOptions`/`GlobalModelProviderGroup`/`GlobalModelSelection`；从 `GeneralSettings` 删掉 `active_provider_id`/`active_model_name`。
3. `src/ember/pages/settings/sections/GlobalModelPicker.tsx`（新建）：徽标 + `Select` + hint；`data-testid="global-model-select"`；首项为「尚未激活全局模型」（value `''`）；无候选时只显示「先启用一个服务商并添加模型」。
4. `ModelSection.tsx`：`useAsync(getGlobalModelOptions)`、`savingGlobal`、`selectGlobal()`；选择器渲染在供应商列表之前；`ProviderModels` 的 `onChanged` 里加 `global.reload()`。
5. `ProviderModels.tsx`：新增 `activeModelValue` / `onActivate`；命中行显示「全局」`Badge`，否则「设为全局模型」按钮。
6. `GeneralSection.tsx`：删除 activeModel 的 `SettingRow` 与 `Badge` import。
7. `i18n/strings.ts`：删 `settings.general.activeModel/activeModelHint/noActiveModel`（中英各 3 键）；新增 `settings.model.globalTitle/globalHint/globalNone/globalEmpty/globalSaved/globalBadge`（中英各 6 键）。
8. 测试：`tests/019-global-model-in-provider-section/globalModel.test.ts`（4 例）。

## 验收

- [x] 「AI 模型设置」顶部出现全局模型选择器；候选只含启用供应商下的模型（实测 `mimo` 未启用 → 不出现）。
- [x] 通用设置页不再出现「当前全局模型」。
- [x] 选中即保存，刷新后仍在（`POST /api/general/active_model` 200）。
- [x] 删掉正被选为全局模型的模型 → 顶部立刻回到「尚未激活全局模型」（用户报的现象不再出现）。
- [x] 老数据（库里指着已删模型）在第一次读时被清理。
- [x] 后端 `pytest -q` 925 passed；前端 `tsc -b` / `vitest run`（38 passed）/ `lint` / `build` 全绿。
- [x] 浏览器实测 6 步，console 错误 0；截图逐张复核（`02-model-after.png`、`05-tmp-is-global.png`、`06-after-delete.png`、`07-restored.png`、`04-general.png`）。
