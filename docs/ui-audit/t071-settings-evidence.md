# T-071 设置页九分区重绘 · 验证证据

- 分支：`flow/T-066`（父卡工作单元）
- 范围：`BillNote_frontend/src/ember/pages/settings/**`、`BillNote_frontend/tests/021-workbench-redesign/settings.test.tsx`、`docs/ui-audit/evidence/t071/**`
- 隔离栈：后端 `master venv python` 运行本 worktree 的 `backend/main.py`，`DATABASE_URL=sqlite:///.../T-066/backend/.t071-tmp/t071.db`、`NOTE_OUTPUT_DIR=.../.t071-tmp/note_results`、`BACKEND_PORT=8497`；前端 `pnpm dev` → `http://127.0.0.1:3025`。**未触碰仓库主数据库**。验证结束后进程、临时库、`.env.local` 全部清理。

## 1. 门禁

| 命令 | 结果 |
| --- | --- |
| `pnpm exec vitest run tests/021-workbench-redesign/settings.test.tsx tests/005-modern-dark-ui --reporter=dot` | Test Files 14 passed，Tests 100 passed，2.00s，exit 0 |
| `pnpm exec tsc -b` | TypeScript: No errors found，exit 0 |
| `pnpm lint`（eslint .） | exit 0 |

`tests/021-workbench-redesign/settings.test.tsx` 新增 13 条用例：loadPhase 优先级、shouldBlockSave、清理口径 `scopeExpiredOnly`、`proxyUrlError`/`canSaveProxy`、草稿跨卸载与订阅通知、`SettingsLoadError` 不渲染输入控件、`SaveStatus` 四态、`sectionIdFromPath`、`sectionOptions` 草稿标记、`SettingsNav` 窄屏 select 与宽屏 nav 的静态结构。

## 2. 分区导航断点

用 `getComputedStyle` 读取窄屏容器（`#settings-section` 所属的 `div.lg:hidden`）与宽屏 `nav[aria-label="设置"]`：

| 视口 | 窄屏下拉容器 | 下拉是否可见（offsetParent） | 宽屏 nav | 横向溢出 |
| --- | --- | --- | --- | --- |
| 1440 | `display:none` | false | `display:flex` | 0 |
| 1024 | `display:none` | false | `display:flex` | 0 |
| 768 | `display:block` | true | `display:none` | 0 |
| 375 | `display:block` | true | `display:none` | 0 |

10 个分区在窄屏由一颗原生 `<select id="settings-section">` 承载（带 `sr-only` label），宽屏由竖排 `NavLink` 列表承载（`aria-current="page"`，草稿分区右侧有 `bg-warn` 圆点 + `aria-label="有未保存的修改"`）。两套导航共享同一份 `SECTIONS` 与同一个 `/settings/:section` 路由。

## 3. 截图对照（`docs/ui-audit/evidence/t071/`）

| 文件 | 证明什么 |
| --- | --- |
| `settings-general-1440-light.png` | 宽屏左侧 256px 竖排 10 项导航 + 右侧平面分组卡片，无边框嵌套卡片 |
| `settings-general-1024-light.png` | 1024 仍为竖排导航，表单标签/输入并排 |
| `settings-general-768-light.png` | 768 切成整宽下拉（当前项「通用设置」），表单转上下堆叠 |
| `settings-general-375-light.png` | 375 无横向滚动，保存按钮与全部输入可达 |
| `settings-general-1024-dark.png` | 深色下表单、开关、只读提示全部可辨（并发任务数=4 是下面保存闭环留下的值） |
| `settings-model-1024-dark.png` | 深色下分区选中态与空状态（无服务商）正常 |
| `settings-media-375-dark.png` | 深色 375：保留天数输入 + 四个清理按钮换行不重叠 |
| `settings-media-confirm-1024-dark.png` | 深色危险操作确认弹层：标题「确认清理？」、正文含数量、取消/确认 |
| `settings-ocr-load-error-1024-light.png` | 读失败态：`role="alert"` 说明 + 重试，**没有任何表单控件与保存按钮** |
| `settings-ocr-load-error-1024-dark.png` | 同上深色 |
| `settings-ocr-test-busy-1024-light.png` | 「测试连接」请求在途：`aria-busy="true"` + `disabled` |
| `settings-proxy-roundtrip-1024-light.png` | 代理开关 + 地址保存后刷新仍保持 |
| `settings-save-saved-1024-light.png` | 保存成功后内联「设置已保存」（不再是 toast） |
| `settings-transcriber-375-touch.png` | 375 触控（hasTouch）下转写分区布局 |

## 4. 行为实测

| 场景 | 操作 | 结果 |
| --- | --- | --- |
| 保存反馈 | 通用设置把并发任务数 3→4，点保存 | 分区内出现「设置已保存」（`SaveStatus`），无 toast；刷新后值仍为 4 |
| Proxy 读写闭环 | 打开开关、填 `http://127.0.0.1:7890`、保存、刷新 | `input#proxy-url` 值保持、switch `aria-checked="true"`；随后关闭并保存还原 |
| 清理确认 + 口径 | 媒体资源「刷新到期预览」→「清理已到期资源」 | 弹层「确认清理？将删除 0 项资源，此操作不可撤销。」+「只删除已超过保留期的文件」；取消后未删除 |
| 连接测试防重复 | 给 `/ocr_config/test` 加 1.5s 延迟后点「测试连接」 | 250ms 时按钮 `aria-busy="true"` 且 `disabled`（Button loading 已禁用二次点击） |
| 读失败禁用保存 | `page.route('**/ocr_config**', abort)` 后进 OCR 分区 | 出现 alert「读取设置失败，未加载到可编辑内容…」；页面内表单控件数 0，保存按钮数 0（唯一 `<select>` 是顶部导航下拉）；axios 全局错误 toast 仍会提示网络失败，属全局拦截器行为 |
| 触控 44px | 375 + `hasTouch` 下遍历分区内 `button/select/input/textarea/[role=switch]/a` | 小于 44px 的目标数 **0**；`tokens.css` 的 coarse 规则兜 button/select，设置页额外给 `main` 加 `pointer-coarse:[&_input]:min-h-11` 兜输入框 |

## 5. 本次修复的真实缺陷（不只是换皮）

1. **OCR 分区丢读错误**：原实现 `const { data, loading, reload } = useAsync(getOcrConfig)` 只判 loading，读失败时表单回落空值，保存会把服务商地址 / API Key 清空。现取 `error`，读失败渲染 `SettingsLoadError` 且 `save` 直接 return。
2. **转写分区同类问题**：`apply(patch)` 无 error 守卫，读失败时选择框为空，写配置会把引擎/模型尺寸改坏。现已加 `if (config.error) return` 与错误分支。
3. **下载 Cookie 草稿不跨分区**：原 `useState<string | null>`，切到别的分区再回来草稿就没了。改 `useSectionDraft<string>('download')`。
4. **媒体保留天数草稿不跨分区**：同上，改 `useSectionDraft<Record<string, number>>('media')`，`busy` 只留给预览/清理，保存走 `useSaveFeedback`。

## 6. 未覆盖 / 已知限制

- 保存失败态（网络 500）只在单测层面覆盖（`SaveStatus('error')` 渲染 + `run` 捕获），没有在浏览器里造一次真实 500 截图。
- Prompt「恢复默认」、Transcriber 端点删除的确认框本次未截图；两者在实现上未改动（仍为 `Dialog` 前置确认），逻辑由既有用例与源码保证。
- 移动端触控尺寸测量以 `getBoundingClientRect` 为准，未在真机验证。
