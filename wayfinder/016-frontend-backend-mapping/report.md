# 016 审计报告：Web 前端 ↔ 后端逐符号映射（增量）

- 执行：工人2 ag_020 · T-046 · flow/T-046 · HEAD `c011bbdf`（= master），开审时 git status 0 行
- CodeGraph（本轮 codegraph_status）：489 files / 7,174 nodes / 16,044 edges，pending=0，index complete。
- 计划：主仓库未跟踪的 wayfinder/016-frontend-backend-mapping/README.md；工作树报告遵照它的范围。
- 图例：VERIFIED_SOURCE=静态源码证据；VERIFIED_RUN=本轮命令/浏览器；PARTIAL；PENDING；NOT RUN。不得混用。
- 本次校正：spec矩阵逐项测试全部标为「单项套件 NOT RUN」，全量覆盖只能参见§6，不能推出逐spec通过。
- 本轮前端门禁：BillNote_frontend 下 pnpm exec vitest run exit 0（17 files/100 tests）；pnpm exec tsc -b exit 0；pnpm lint (eslint .) exit 0；pnpm build exit 0（3158 modules，bundle size warnings）。
- 本轮后端门禁：backend 下 .venv/bin/python -m pytest -q -p no:cacheprovider exit 0（953 passed、15 subtests、1 warning）。初试 .venv/Scripts/python.exe 于 Bash 中 exit 127；改用存在的 POSIX venv 后通过。
- 本轮 AST 计数与差异核对（T-046 worktree，基线 c011bbdf）：config18/general4/media7/model5/note16/note_group7/ocr3/provider5；§4 小节边界内逐行提取65条 method/path，unique65，AST/表 missing=0、extra=0、duplicates=0。命令 exit 0。只证明method/path行覆盖，不代表契约/service/UI双向链完整。

## 0. 进度
| 节 | 状态 |
|---|---|
| 1 计数 / 2 文件导出 / 3 UI 原语调用者 / 4 route method/path 清单 | VERIFIED_SOURCE（src路径100/100；AST method/path 65/65） |
| 4 route→service→Web 双向映射 | PARTIAL：65/65 method/path/handler 行由 AST 与表格对账；52/65 route rows 具备明确 Web service/caller 静态证据，13/65 仍需逐符号链或运行时核实；契约状态行为与 spec 链仍不完整 |
| 5 spec 矩阵 | PARTIAL |
| 6 门禁 | VERIFIED |
| 7 浏览器路径 | PARTIAL：Flow人工提供的只读复验覆盖workspace/onboarding及Settings九个子路由；生成/重试/批量pick/带真实笔记reader和写入路径仍NOT RUN |
| 8 发现分级 | PARTIAL |

## 1. 计数（VERIFIED）
| 项 | 数 | 口径 |
|---|---|---|
| src 跟踪文件 | 100（97 ts/tsx = 41+56，其中39个运行时 .ts + 56个 .tsx = 95；2个 .d.ts；3 css） | git ls-files（与报告文件表逐路径比对：100/100，无缺项、无额外） |
| 导出符号 | 278 | 正则：export 声明 + export {} + export default |
| ember/ui 原语 | 18 文件 | |
| 前端测试文件 | 17（16 个在 NNN 目录 + tests/onboardingTranscriber.test.ts） | git ls-files |
| 后端测试 .py | 111（test_*.py 107） | git ls-files；主调度给的 92 口径待对齐 |
| 对外 route | **65**：config 18 / note 16 / note_group 7 / media 7 / model 5 / provider 5 / general 4 / ocr 3 | AST；grep 得 66 是因为 provider.py:75 那条已被注释掉 |

并行代理的 44 条是子集（config 实际 18 条，note 16 条）。main.py 另有 /static、/uploads 两个 StaticFiles 挂载。

## 2. 前端文件 / 导出（VERIFIED）
| 文件 (src/) | 类别 | 导出 | 静态调用者 |
|---|---|---|---|
| constant/note.ts | 常量 | noteFormats, noteScenes, noteDetails, videoPlatforms | ember/features/workspace/GenerationOptions.tsx |
| ember/EmberApp.tsx | 入口/路由 | EmberApp | main.tsx |
| ember/features/reader/MarkdownNote.tsx | 业务组件 | MarkdownNote | ember/features/reader/NotePanel.tsx |
| ember/features/reader/NotePanel.tsx | 业务组件 | NotePanel | ember/pages/WorkspacePage.tsx |
| ember/features/reader/TranscriptView.tsx | 业务组件 | TranscriptView | ember/features/reader/NotePanel.tsx |
| ember/features/reader/anchors.ts | 业务组件 | scrollToAnchor | ember/features/reader/MarkdownNote.tsx<br>ember/features/reader/NotePanel.tsx |
| ember/features/reader/outline.ts | 业务组件 | OutlineItem, slugify, extractOutline | ember/features/reader/NotePanel.tsx |
| ember/features/workspace/BatchImportPanel.tsx | 业务组件 | BatchImportPanel | ember/features/workspace/IntakePanel.tsx |
| ember/features/workspace/GenerationOptions.tsx | 业务组件 | GenerationOptions | ember/features/workspace/BatchImportPanel.tsx<br>ember/features/workspace/IntakeForm.tsx |
| ember/features/workspace/GroupPanel.tsx | 业务组件 | GroupPanel | ember/pages/WorkspacePage.tsx |
| ember/features/workspace/IntakeForm.tsx | 业务组件 | IntakeForm | ember/features/workspace/IntakePanel.tsx |
| ember/features/workspace/IntakePanel.tsx | 业务组件 | IntakePanel | ember/pages/WorkspacePage.tsx |
| ember/features/workspace/RetryFailedAction.tsx | 业务组件 | RetryFailedAction | ember/features/workspace/TaskList.tsx |
| ember/features/workspace/TaskCard.tsx | 业务组件 | TaskCard | ember/features/workspace/TaskList.tsx |
| ember/features/workspace/TaskList.tsx | 业务组件 | TaskList | ember/pages/WorkspacePage.tsx |
| ember/features/workspace/TaskProgressCard.tsx | 业务组件 | TaskProgressCard | ember/pages/WorkspacePage.tsx |
| ember/features/workspace/archive.ts | 业务组件 | sanitizeFileName, saveBlob | ember/features/workspace/useNoteGroups.ts |
| ember/features/workspace/generationSettings.ts | 业务组件 | GenerationSettings, DEFAULT_GENERATION_SETTINGS, toPayloadSettings | ember/features/workspace/BatchImportPanel.tsx<br>ember/features/workspace/BatchImportPanel.tsx<br>ember/features/workspace/GenerationOptions.tsx<br>ember/features/workspace/IntakeForm.tsx<br>ember/features/workspace/IntakeForm.tsx |
| ember/features/workspace/retryFailed.ts | 业务组件 | RetryScope, retryScopeForGroup, retryResultKind, retrySelectedFailedTasks | ember/features/workspace/TaskList.tsx<br>ember/pages/WorkspacePage.tsx |
| ember/features/workspace/taskState.ts | 业务组件 | TaskTone, statusTone, statusKey, isTaskActive, taskProgress, stageKey, detailSummary, taskTitle | ember/features/workspace/TaskCard.tsx<br>ember/features/workspace/TaskList.tsx<br>ember/features/workspace/TaskProgressCard.tsx |
| ember/features/workspace/useNoteGroups.ts | 业务组件 | GroupFilter, useNoteGroups | ember/features/workspace/GroupPanel.tsx<br>ember/pages/WorkspacePage.tsx |
| ember/i18n/context.ts | i18n | I18nValue, I18nContext, useI18n | ember/features/reader/NotePanel.tsx<br>ember/features/reader/TranscriptView.tsx<br>ember/features/workspace/BatchImportPanel.tsx<br>ember/features/workspace/GenerationOptions.tsx<br>ember/features/workspace/GroupPanel.tsx<br>ember/features/workspace/IntakeForm.tsx<br>ember/features/workspace/IntakePanel.tsx<br>ember/features/workspace/RetryFailedAction.tsx<br>ember/features/workspace/TaskCard.tsx<br>ember/features/workspace/TaskList.tsx<br>ember/features/workspace/TaskProgressCard.tsx<br>ember/features/workspace/useNoteGroups.ts<br>ember/i18n/index.tsx<br>ember/pages/NotFoundPage.tsx<br>ember/pages/OnboardingPage.tsx<br>ember/pages/WorkspacePage.tsx<br>ember/pages/settings/SettingsPage.tsx<br>ember/pages/settings/sections/AboutSection.tsx<br>ember/pages/settings/sections/DownloadSection.tsx<br>ember/pages/settings/sections/GeneralSection.tsx<br>ember/pages/settings/sections/GlobalModelPicker.tsx<br>ember/pages/settings/sections/MediaSection.tsx<br>ember/pages/settings/sections/ModelSection.tsx<br>ember/pages/settings/sections/MonitorSection.tsx<br>ember/pages/settings/sections/OcrSection.tsx<br>ember/pages/settings/sections/PromptSection.tsx<br>ember/pages/settings/sections/ProviderDialog.tsx<br>ember/pages/settings/sections/ProviderModels.tsx<br>ember/pages/settings/sections/TranscriberSection.tsx<br>ember/shell/LanguageSwitcher.tsx<br>ember/shell/useEmberNav.ts<br>ember/startup/StartupNotice.tsx<br>ember/startup/StartupScreen.tsx<br>ember/ui/Dialog.tsx<br>ember/ui/Drawer.tsx |
| ember/i18n/index.tsx | i18n | EmberI18nProvider, LOCALES | main.tsx |
| ember/i18n/locale.ts | i18n | LOCALE_STORAGE_KEY, readStoredLocale, translate | ember/i18n/index.tsx<br>hooks/useTaskPolling.ts<br>services/note.ts<br>utils/request.ts |
| ember/i18n/strings.ts | i18n | Locale, LOCALES, MessageKey, Dictionary, dictionaries, format | ember/features/workspace/GenerationOptions.tsx<br>ember/features/workspace/IntakeForm.tsx<br>ember/features/workspace/taskState.ts<br>ember/i18n/context.ts<br>ember/i18n/index.tsx<br>ember/i18n/index.tsx<br>ember/i18n/index.tsx<br>ember/i18n/locale.ts<br>ember/pages/onboardingTranscriber.ts<br>ember/pages/settings/SettingsPage.tsx<br>ember/pages/settings/sections/TranscriberSection.tsx<br>utils/request.ts |
| ember/lib/assets.ts | 工具 | ASSET_ORIGIN, resolveAssetUrl | ember/features/reader/MarkdownNote.tsx |
| ember/lib/cn.ts | 工具 | cn | ember/features/reader/MarkdownNote.tsx<br>ember/features/reader/TranscriptView.tsx<br>ember/features/workspace/GroupPanel.tsx<br>ember/features/workspace/TaskCard.tsx<br>ember/features/workspace/TaskList.tsx<br>ember/pages/settings/Section.tsx<br>ember/pages/settings/SettingsPage.tsx<br>ember/shell/AppShell.tsx<br>ember/ui/Badge.tsx<br>ember/ui/Button.tsx<br>ember/ui/Card.tsx<br>ember/ui/Checkbox.tsx<br>ember/ui/Chip.tsx<br>ember/ui/Dialog.tsx<br>ember/ui/Drawer.tsx<br>ember/ui/EmptyState.tsx<br>ember/ui/Field.tsx<br>ember/ui/Input.tsx<br>ember/ui/Progress.tsx<br>ember/ui/Select.tsx<br>ember/ui/Skeleton.tsx<br>ember/ui/Spinner.tsx<br>ember/ui/Switch.tsx<br>ember/ui/Tabs.tsx<br>ember/ui/Tooltip.tsx |
| ember/lib/useAsync.ts | 工具 | useAsync | ember/pages/settings/sections/GeneralSection.tsx<br>ember/pages/settings/sections/MediaSection.tsx<br>ember/pages/settings/sections/ModelSection.tsx<br>ember/pages/settings/sections/MonitorSection.tsx<br>ember/pages/settings/sections/OcrSection.tsx<br>ember/pages/settings/sections/PromptSection.tsx<br>ember/pages/settings/sections/ProviderModels.tsx<br>ember/pages/settings/sections/TranscriberSection.tsx |
| ember/motion.css | 样式 | — | index.css |
| ember/pages/NotFoundPage.tsx | 页面 | NotFoundPage | ember/EmberApp.tsx |
| ember/pages/OnboardingGuard.tsx | 页面 | OnboardingGuard | ember/EmberApp.tsx |
| ember/pages/OnboardingPage.tsx | 页面 | OnboardingPage | ember/EmberApp.tsx (dynamic) |
| ember/pages/WorkspacePage.tsx | 页面 | WorkspacePage | ember/EmberApp.tsx |
| ember/pages/onboardingStorage.ts | 页面 | ONBOARDING_STORAGE_KEY, hasCompletedOnboarding | ember/pages/OnboardingGuard.tsx<br>ember/pages/OnboardingPage.tsx |
| ember/pages/onboardingTranscriber.ts | 页面 | TranscriberType, DEFAULT_ONBOARDING_TRANSCRIBER, ONBOARDING_TRANSCRIBERS, OnboardingTranscriberPayload, buildOnboardingTranscriberPayload | ember/pages/OnboardingPage.tsx |
| ember/pages/settings/Section.tsx | 页面 | SettingsSection, SettingRow | ember/pages/settings/sections/AboutSection.tsx<br>ember/pages/settings/sections/DownloadSection.tsx<br>ember/pages/settings/sections/GeneralSection.tsx<br>ember/pages/settings/sections/MediaSection.tsx<br>ember/pages/settings/sections/ModelSection.tsx<br>ember/pages/settings/sections/MonitorSection.tsx<br>ember/pages/settings/sections/OcrSection.tsx<br>ember/pages/settings/sections/PromptSection.tsx<br>ember/pages/settings/sections/TranscriberSection.tsx |
| ember/pages/settings/SettingsPage.tsx | 页面 | SettingsPage | ember/EmberApp.tsx (dynamic) |
| ember/pages/settings/sections/AboutSection.tsx | 设置分区组件 | AboutSection | ember/pages/settings/SettingsPage.tsx |
| ember/pages/settings/sections/DownloadSection.tsx | 设置分区组件 | DownloadSection | ember/pages/settings/SettingsPage.tsx |
| ember/pages/settings/sections/GeneralSection.tsx | 设置分区组件 | GeneralSection | ember/pages/settings/SettingsPage.tsx |
| ember/pages/settings/sections/GlobalModelPicker.tsx | 设置分区组件 | GlobalModelPicker | ember/pages/settings/sections/ModelSection.tsx |
| ember/pages/settings/sections/MediaSection.tsx | 设置分区组件 | MediaSection | ember/pages/settings/SettingsPage.tsx |
| ember/pages/settings/sections/ModelSection.tsx | 设置分区组件 | ModelSection | ember/pages/settings/SettingsPage.tsx |
| ember/pages/settings/sections/MonitorSection.tsx | 设置分区组件 | MonitorSection | ember/pages/settings/SettingsPage.tsx |
| ember/pages/settings/sections/OcrSection.tsx | 设置分区组件 | OcrSection | ember/pages/settings/SettingsPage.tsx |
| ember/pages/settings/sections/PromptSection.tsx | 设置分区组件 | PromptSection | ember/pages/settings/SettingsPage.tsx |
| ember/pages/settings/sections/ProviderDialog.tsx | 设置分区组件 | ProviderDialog | ember/pages/settings/sections/ModelSection.tsx |
| ember/pages/settings/sections/ProviderModels.tsx | 设置分区组件 | ProviderModels | ember/pages/settings/sections/ModelSection.tsx |
| ember/pages/settings/sections/TranscriberSection.tsx | 设置分区组件 | TranscriberSection | ember/pages/settings/SettingsPage.tsx |
| ember/shell/AppShell.tsx | 壳层 | AppShell | ember/pages/NotFoundPage.tsx<br>ember/pages/WorkspacePage.tsx<br>ember/pages/settings/SettingsPage.tsx |
| ember/shell/EmberToaster.tsx | 壳层 | EmberToaster | main.tsx |
| ember/shell/LanguageSwitcher.tsx | 壳层 | LanguageSwitcher | ember/pages/OnboardingPage.tsx<br>ember/pages/WorkspacePage.tsx<br>ember/pages/settings/SettingsPage.tsx<br>ember/shell/AppShell.tsx<br>ember/startup/StartupScreen.tsx |
| ember/shell/useEmberNav.ts | 壳层 | useEmberNav | ember/shell/AppShell.tsx |
| ember/startup/StartupNotice.tsx | 启动门禁 | StartupNotice | ember/EmberApp.tsx |
| ember/startup/StartupScreen.tsx | 启动门禁 | StartupScreen | ember/EmberApp.tsx |
| ember/startup/useBackendEvents.ts | 启动门禁 | LogLevel, LogEntry, BackendProcessStatus, BackendEvents, useBackendEvents | ember/startup/StartupScreen.tsx |
| ember/tokens.css | 样式 | — | index.css |
| ember/ui/Badge.tsx | UI原语 | Badge | ember/features/workspace/TaskCard.tsx<br>ember/features/workspace/TaskProgressCard.tsx<br>ember/pages/settings/sections/AboutSection.tsx<br>ember/pages/settings/sections/DownloadSection.tsx<br>ember/pages/settings/sections/GlobalModelPicker.tsx<br>ember/pages/settings/sections/ModelSection.tsx<br>ember/pages/settings/sections/MonitorSection.tsx<br>ember/pages/settings/sections/OcrSection.tsx<br>ember/pages/settings/sections/PromptSection.tsx<br>ember/pages/settings/sections/ProviderModels.tsx<br>ember/pages/settings/sections/TranscriberSection.tsx |
| ember/ui/BilibiliMark.tsx | UI原语 | BilibiliMark | constant/note.ts |
| ember/ui/Button.tsx | UI原语 | ButtonVariant, ButtonSize, Button | ember/features/reader/NotePanel.tsx<br>ember/features/workspace/BatchImportPanel.tsx<br>ember/features/workspace/GroupPanel.tsx<br>ember/features/workspace/IntakeForm.tsx<br>ember/features/workspace/RetryFailedAction.tsx<br>ember/features/workspace/TaskList.tsx<br>ember/features/workspace/TaskProgressCard.tsx<br>ember/pages/OnboardingPage.tsx<br>ember/pages/settings/sections/DownloadSection.tsx<br>ember/pages/settings/sections/GeneralSection.tsx<br>ember/pages/settings/sections/MediaSection.tsx<br>ember/pages/settings/sections/ModelSection.tsx<br>ember/pages/settings/sections/MonitorSection.tsx<br>ember/pages/settings/sections/OcrSection.tsx<br>ember/pages/settings/sections/PromptSection.tsx<br>ember/pages/settings/sections/ProviderDialog.tsx<br>ember/pages/settings/sections/ProviderModels.tsx<br>ember/pages/settings/sections/TranscriberSection.tsx<br>ember/shell/AppShell.tsx<br>ember/shell/LanguageSwitcher.tsx<br>ember/startup/StartupScreen.tsx<br>ember/ui/Dialog.tsx<br>ember/ui/Drawer.tsx |
| ember/ui/Card.tsx | UI原语 | Card, CardHeader, CardTitle, CardBody, CardFooter | ember/features/workspace/BatchImportPanel.tsx<br>ember/features/workspace/IntakeForm.tsx<br>ember/features/workspace/TaskProgressCard.tsx<br>ember/pages/OnboardingPage.tsx<br>ember/pages/settings/sections/AboutSection.tsx<br>ember/pages/settings/sections/DownloadSection.tsx<br>ember/pages/settings/sections/GeneralSection.tsx<br>ember/pages/settings/sections/GlobalModelPicker.tsx<br>ember/pages/settings/sections/MediaSection.tsx<br>ember/pages/settings/sections/ModelSection.tsx<br>ember/pages/settings/sections/MonitorSection.tsx<br>ember/pages/settings/sections/OcrSection.tsx<br>ember/pages/settings/sections/PromptSection.tsx<br>ember/pages/settings/sections/TranscriberSection.tsx |
| ember/ui/Checkbox.tsx | UI原语 | Checkbox | ember/features/workspace/BatchImportPanel.tsx<br>ember/features/workspace/GroupPanel.tsx |
| ember/ui/Chip.tsx | UI原语 | Chip | ember/features/workspace/BatchImportPanel.tsx<br>ember/features/workspace/GenerationOptions.tsx<br>ember/features/workspace/TaskList.tsx |
| ember/ui/Dialog.tsx | UI原语 | Dialog | ember/features/workspace/GroupPanel.tsx<br>ember/features/workspace/TaskList.tsx<br>ember/pages/settings/sections/ModelSection.tsx<br>ember/pages/settings/sections/TranscriberSection.tsx |
| ember/ui/Drawer.tsx | UI原语 | Drawer | ember/shell/AppShell.tsx |
| ember/ui/EmptyState.tsx | UI原语 | EmptyState | ember/features/reader/NotePanel.tsx<br>ember/features/reader/TranscriptView.tsx<br>ember/features/workspace/TaskList.tsx<br>ember/pages/NotFoundPage.tsx<br>ember/pages/WorkspacePage.tsx<br>ember/pages/settings/sections/ModelSection.tsx |
| ember/ui/Field.tsx | UI原语 | Field | ember/features/workspace/BatchImportPanel.tsx<br>ember/features/workspace/GenerationOptions.tsx<br>ember/features/workspace/IntakeForm.tsx<br>ember/pages/OnboardingPage.tsx<br>ember/pages/settings/sections/DownloadSection.tsx<br>ember/pages/settings/sections/OcrSection.tsx<br>ember/pages/settings/sections/PromptSection.tsx<br>ember/pages/settings/sections/ProviderDialog.tsx<br>ember/pages/settings/sections/TranscriberSection.tsx |
| ember/ui/Input.tsx | UI原语 | Input, Textarea | ember/features/reader/TranscriptView.tsx<br>ember/features/workspace/BatchImportPanel.tsx<br>ember/features/workspace/GenerationOptions.tsx<br>ember/features/workspace/GroupPanel.tsx<br>ember/features/workspace/IntakeForm.tsx<br>ember/features/workspace/TaskList.tsx<br>ember/pages/OnboardingPage.tsx<br>ember/pages/settings/sections/DownloadSection.tsx<br>ember/pages/settings/sections/GeneralSection.tsx<br>ember/pages/settings/sections/MediaSection.tsx<br>ember/pages/settings/sections/OcrSection.tsx<br>ember/pages/settings/sections/PromptSection.tsx<br>ember/pages/settings/sections/ProviderDialog.tsx<br>ember/pages/settings/sections/ProviderModels.tsx<br>ember/pages/settings/sections/TranscriberSection.tsx |
| ember/ui/Progress.tsx | UI原语 | Progress | ember/features/workspace/TaskCard.tsx<br>ember/features/workspace/TaskProgressCard.tsx |
| ember/ui/Select.tsx | UI原语 | SelectOption, Select | ember/features/workspace/GenerationOptions.tsx<br>ember/pages/settings/sections/GlobalModelPicker.tsx<br>ember/pages/settings/sections/ProviderDialog.tsx<br>ember/pages/settings/sections/TranscriberSection.tsx |
| ember/ui/Skeleton.tsx | UI原语 | Skeleton | ember/features/workspace/TaskList.tsx<br>ember/pages/settings/sections/GeneralSection.tsx<br>ember/pages/settings/sections/MediaSection.tsx<br>ember/pages/settings/sections/ModelSection.tsx<br>ember/pages/settings/sections/MonitorSection.tsx<br>ember/pages/settings/sections/OcrSection.tsx<br>ember/pages/settings/sections/PromptSection.tsx<br>ember/pages/settings/sections/TranscriberSection.tsx |
| ember/ui/Spinner.tsx | UI原语 | Spinner | ember/EmberApp.tsx<br>ember/features/workspace/BatchImportPanel.tsx<br>ember/features/workspace/TaskProgressCard.tsx<br>ember/pages/OnboardingPage.tsx<br>ember/startup/StartupScreen.tsx<br>ember/ui/Button.tsx |
| ember/ui/Switch.tsx | UI原语 | Switch | ember/features/workspace/BatchImportPanel.tsx<br>ember/features/workspace/GenerationOptions.tsx<br>ember/pages/settings/sections/GeneralSection.tsx<br>ember/pages/settings/sections/OcrSection.tsx<br>ember/pages/settings/sections/TranscriberSection.tsx |
| ember/ui/Tabs.tsx | UI原语 | TabItem, Tabs | ember/features/reader/NotePanel.tsx<br>ember/features/workspace/GenerationOptions.tsx<br>ember/features/workspace/IntakePanel.tsx |
| ember/ui/Tooltip.tsx | UI原语 | Tooltip | **无静态调用者** |
| hooks/useCheckBackend.ts | hook | BootFailureCode, BootFailureReason, useCheckBackend | ember/EmberApp.tsx<br>ember/startup/StartupScreen.tsx |
| hooks/useTaskPolling.ts | hook | useTaskPolling | ember/pages/WorkspacePage.tsx |
| index.css | 样式 | — | main.tsx |
| main.tsx | 入口/路由 | — | index.html 入口 |
| services/downloader.ts | service | getDownloaderCookie, updateDownloaderCookie | ember/pages/settings/sections/DownloadSection.tsx |
| services/general.ts | service | GeneralSettings, GeneralSettingsPatch, getGeneralSettings, activateGlobalModel, GlobalModelSelection, GlobalModelProviderGroup, GlobalModelOptions, getGlobalModelOptions, updateGeneralSettings | ember/pages/settings/sections/GeneralSection.tsx<br>ember/pages/settings/sections/ModelSection.tsx<br>ember/pages/settings/sections/PromptSection.tsx<br>ember/pages/settings/sections/TranscriberSection.tsx |
| services/media.ts | service | RetentionSettings, CleanupPreview, CleanupRun, getRetentionSettings, saveRetentionSettings, getRecentCleanupRuns, previewMediaCleanup, CleanupResult, runMediaCleanup | ember/pages/settings/sections/MediaSection.tsx |
| services/model.ts | service | ProviderSummary, EnabledModelSummary, getProviderList, getProviderById, ProviderCreatePayload, ProviderUpdatePayload, ConnectionTestPayload, updateProviderById, addProvider, testConnection, RemoteModel, RemoteModelList, fetchModels, SavedModel, fetchEnableModelById, addModel, fetchEnableModels, deleteModelById | ember/pages/OnboardingPage.tsx<br>ember/pages/settings/sections/ModelSection.tsx<br>ember/pages/settings/sections/ProviderDialog.tsx<br>ember/pages/settings/sections/ProviderModels.tsx |
| services/note.ts | service | IntakeItemState, IntakeItem, IntakeResolveEnvelope, resolveIntake, downloadNoteArchive, downloadNoteArchives, GenerateNotePayload, generateNote, TaskListRow, TaskListPayload, listTasks, deleteTaskRecord, BatchDeleteResult, deleteTaskRecords, get_task_status, ExpandPart, ExpandVideo, ExpandResult, BatchGenerateItem, BatchGenerateResult, BatchGeneratePayload, expandUrl, generateNotes, TaskStatusLite, TaskStatusBatchPayload, readTaskStatusMap, getTaskStatusBatch, TaskReadStatus, TaskView, TaskReadModelSnapshot, getTaskReadModelSnapshot, subscribeTaskReadModel, RetryFailedResult, retryFailedTasks | ember/features/workspace/BatchImportPanel.tsx<br>ember/features/workspace/IntakeForm.tsx<br>ember/features/workspace/IntakeForm.tsx<br>ember/features/workspace/retryFailed.ts<br>ember/features/workspace/useNoteGroups.ts<br>ember/pages/WorkspacePage.tsx<br>hooks/useTaskPolling.ts<br>store/taskStore/index.ts<br>utils/batchPayload.ts |
| services/noteGroup.ts | service | UNGROUPED_ID, NoteGroup, NoteGroupList, listNoteGroups, createNoteGroup, renameNoteGroup, GroupDeleteResult, deleteNoteGroup, assignTaskToGroup, assignTasksToGroup, listGroupTaskIds | ember/features/workspace/GroupPanel.tsx<br>ember/features/workspace/TaskList.tsx<br>ember/features/workspace/retryFailed.ts<br>ember/features/workspace/useNoteGroups.ts |
| services/ocr.ts | service | OcrDefaults, OcrConfig, OcrConfigInput, OcrTestSuccess, OcrTestFailure, OcrTestResult, getOcrConfig, updateOcrConfig, testOcrConfig | ember/pages/settings/sections/OcrSection.tsx |
| services/proxy.ts | service | ProxyConfig, getProxyConfig, updateProxyConfig | **无静态调用者** |
| services/system.ts | service | SysHealth, getSysHealth, systemCheck, DeployStatus, getDeployStatus | ember/EmberApp.tsx<br>ember/pages/settings/sections/MonitorSection.tsx |
| services/transcriber.ts | service | OpenAIASRStyle, OpenAIASREndpoint, OpenAIASREndpointInput, TranscriberConfig, ModelStatus, ModelsStatusResponse, getTranscriberConfig, updateTranscriberConfig, addOpenaiAsr, updateOpenaiAsr, deleteOpenaiAsr, testOpenaiAsr, getModelsStatus, downloadModel, WhisperModelsResponse, listWhisperModels, addWhisperModel, deleteWhisperModel | ember/pages/OnboardingPage.tsx<br>ember/pages/settings/sections/TranscriberSection.tsx |
| services/upload.ts | service | uploadFile | **无静态调用者** |
| store/taskStore/index.ts | store | readLatestMarkdown, TaskStatus, TaskStage, TaskProgress, AudioMeta, Segment, Transcript, TaskFormData, Task, useTaskStore | ember/features/reader/NotePanel.tsx<br>ember/features/reader/TranscriptView.tsx<br>ember/features/workspace/IntakeForm.tsx<br>ember/features/workspace/TaskCard.tsx<br>ember/features/workspace/TaskList.tsx<br>ember/features/workspace/TaskProgressCard.tsx<br>ember/features/workspace/retryFailed.ts<br>ember/features/workspace/taskState.ts<br>ember/features/workspace/useNoteGroups.ts<br>ember/pages/WorkspacePage.tsx<br>hooks/useTaskPolling.ts |
| types/react-19-jsx-shim.d.ts | 类型声明 | — | tsconfig include（非 import） |
| utils/batchPayload.ts | 工具 | BatchProfile, buildBatchPayload | ember/features/workspace/BatchImportPanel.tsx |
| utils/globalModel.ts | 工具 | GLOBAL_MODEL_SEPARATOR, GlobalModelProvider, GlobalModelOption, globalModelValue, parseGlobalModelValue, buildGlobalModelOptions | ember/pages/settings/sections/GlobalModelPicker.tsx<br>ember/pages/settings/sections/ModelSection.tsx<br>ember/pages/settings/sections/ProviderModels.tsx |
| utils/markdown.ts | 工具 | normalizeMathDelimiters | ember/features/reader/MarkdownNote.tsx |
| utils/progress.ts | 工具 | toPercent | ember/features/workspace/taskState.ts |
| utils/range.ts | 工具 | parseRangeSelection | ember/features/workspace/BatchImportPanel.tsx |
| utils/request.ts | 工具 | IResponse, localizedError, default | ember/features/workspace/IntakeForm.tsx<br>services/downloader.ts<br>services/general.ts<br>services/media.ts<br>services/model.ts<br>services/note.ts<br>services/noteGroup.ts<br>services/ocr.ts<br>services/proxy.ts<br>services/system.ts<br>services/transcriber.ts<br>services/upload.ts |
| utils/taskStatus.ts | 工具 | FINISHED_TASK_STATUSES, isTaskTerminal, shouldPollTaskStatus, isTaskInFlight, TaskDetail, toDetailPayload, NormalizedTaskStatus, RawTaskStatus, normalizeTaskStatus | ember/features/workspace/taskState.ts<br>hooks/useTaskPolling.ts<br>services/note.ts<br>store/taskStore/index.ts |
| vite-env.d.ts | 类型声明 | — | tsconfig include（非 import） |

路由：/onboarding（lazy）、/（WorkspacePage + OnboardingGuard）、/settings/{general,model,transcriber,ocr,prompt,media,download,monitor,about}（lazy）、* NotFoundPage。

## 3. UI 原语调用者（VERIFIED，静态）
| 文件 | 导出 | 调用文件数 | 调用者（JSX 使用次数） |
|---|---|---|---|
| ember/ui/Badge.tsx | Badge | 11 | ember/features/workspace/TaskCard.tsx (Badge×1)<br>ember/features/workspace/TaskProgressCard.tsx (Badge×1)<br>ember/pages/settings/sections/AboutSection.tsx (Badge×2)<br>ember/pages/settings/sections/DownloadSection.tsx (Badge×1)<br>ember/pages/settings/sections/GlobalModelPicker.tsx (Badge×1)<br>ember/pages/settings/sections/ModelSection.tsx (Badge×1)<br>ember/pages/settings/sections/MonitorSection.tsx (Badge×1)<br>ember/pages/settings/sections/OcrSection.tsx (Badge×3)<br>ember/pages/settings/sections/PromptSection.tsx (Badge×4)<br>ember/pages/settings/sections/ProviderModels.tsx (Badge×1)<br>ember/pages/settings/sections/TranscriberSection.tsx (Badge×2) |
| ember/ui/BilibiliMark.tsx | BilibiliMark | 1 | constant/note.ts () |
| ember/ui/Button.tsx | ButtonVariant, ButtonSize, Button | 23 | ember/features/reader/NotePanel.tsx (Button×2)<br>ember/features/workspace/BatchImportPanel.tsx (Button×6)<br>ember/features/workspace/GroupPanel.tsx (Button×6)<br>ember/features/workspace/IntakeForm.tsx (Button×2)<br>ember/features/workspace/RetryFailedAction.tsx (Button×1)<br>ember/features/workspace/TaskList.tsx (Button×4)<br>ember/features/workspace/TaskProgressCard.tsx (Button×1)<br>ember/pages/OnboardingPage.tsx (Button×6)<br>ember/pages/settings/sections/DownloadSection.tsx (Button×1)<br>ember/pages/settings/sections/GeneralSection.tsx (Button×1)<br>ember/pages/settings/sections/MediaSection.tsx (Button×4)<br>ember/pages/settings/sections/ModelSection.tsx (Button×1)<br>ember/pages/settings/sections/MonitorSection.tsx (Button×1)<br>ember/pages/settings/sections/OcrSection.tsx (Button×2)<br>ember/pages/settings/sections/PromptSection.tsx (Button×3)<br>ember/pages/settings/sections/ProviderDialog.tsx (Button×1)<br>ember/pages/settings/sections/ProviderModels.tsx (Button×4)<br>ember/pages/settings/sections/TranscriberSection.tsx (Button×7)<br>ember/shell/AppShell.tsx (Button×1)<br>ember/shell/LanguageSwitcher.tsx (Button×1)<br>ember/startup/StartupScreen.tsx (Button×3)<br>ember/ui/Dialog.tsx (Button×1)<br>ember/ui/Drawer.tsx (Button×1) |
| ember/ui/Card.tsx | Card, CardHeader, CardTitle, CardBody, CardFooter | 14 | ember/features/workspace/BatchImportPanel.tsx (Card×1)<br>ember/features/workspace/IntakeForm.tsx (Card×1)<br>ember/features/workspace/TaskProgressCard.tsx (Card×1)<br>ember/pages/OnboardingPage.tsx (Card×1, CardBody×4)<br>ember/pages/settings/sections/AboutSection.tsx (Card×1)<br>ember/pages/settings/sections/DownloadSection.tsx (Card×1)<br>ember/pages/settings/sections/GeneralSection.tsx (Card×6)<br>ember/pages/settings/sections/GlobalModelPicker.tsx (Card×1)<br>ember/pages/settings/sections/MediaSection.tsx (Card×2)<br>ember/pages/settings/sections/ModelSection.tsx (Card×1)<br>ember/pages/settings/sections/MonitorSection.tsx (Card×3)<br>ember/pages/settings/sections/OcrSection.tsx (Card×3)<br>ember/pages/settings/sections/PromptSection.tsx (Card×2)<br>ember/pages/settings/sections/TranscriberSection.tsx (Card×2) |
| ember/ui/Checkbox.tsx | Checkbox | 2 | ember/features/workspace/BatchImportPanel.tsx (Checkbox×1)<br>ember/features/workspace/GroupPanel.tsx (Checkbox×4) |
| ember/ui/Chip.tsx | Chip | 3 | ember/features/workspace/BatchImportPanel.tsx (Chip×2)<br>ember/features/workspace/GenerationOptions.tsx (Chip×1)<br>ember/features/workspace/TaskList.tsx (Chip×1) |
| ember/ui/Dialog.tsx | Dialog | 4 | ember/features/workspace/GroupPanel.tsx (Dialog×1)<br>ember/features/workspace/TaskList.tsx (Dialog×1)<br>ember/pages/settings/sections/ModelSection.tsx (Dialog×2)<br>ember/pages/settings/sections/TranscriberSection.tsx (Dialog×2) |
| ember/ui/Drawer.tsx | Drawer | 1 | ember/shell/AppShell.tsx (Drawer×1) |
| ember/ui/EmptyState.tsx | EmptyState | 6 | ember/features/reader/NotePanel.tsx (EmptyState×1)<br>ember/features/reader/TranscriptView.tsx (EmptyState×1)<br>ember/features/workspace/TaskList.tsx (EmptyState×1)<br>ember/pages/NotFoundPage.tsx (EmptyState×1)<br>ember/pages/WorkspacePage.tsx (EmptyState×1)<br>ember/pages/settings/sections/ModelSection.tsx (EmptyState×1) |
| ember/ui/Field.tsx | Field | 9 | ember/features/workspace/BatchImportPanel.tsx (Field×4)<br>ember/features/workspace/GenerationOptions.tsx (Field×11)<br>ember/features/workspace/IntakeForm.tsx (Field×1)<br>ember/pages/OnboardingPage.tsx (Field×4)<br>ember/pages/settings/sections/DownloadSection.tsx (Field×1)<br>ember/pages/settings/sections/OcrSection.tsx (Field×6)<br>ember/pages/settings/sections/PromptSection.tsx (Field×1)<br>ember/pages/settings/sections/ProviderDialog.tsx (Field×4)<br>ember/pages/settings/sections/TranscriberSection.tsx (Field×12) |
| ember/ui/Input.tsx | Input, Textarea | 15 | ember/features/reader/TranscriptView.tsx (Input×1)<br>ember/features/workspace/BatchImportPanel.tsx (Input×3, Textarea×1)<br>ember/features/workspace/GenerationOptions.tsx (Input×6, Textarea×1)<br>ember/features/workspace/GroupPanel.tsx (Input×2)<br>ember/features/workspace/IntakeForm.tsx (Input×1)<br>ember/features/workspace/TaskList.tsx (Input×1)<br>ember/pages/OnboardingPage.tsx (Input×4)<br>ember/pages/settings/sections/DownloadSection.tsx (Textarea×1)<br>ember/pages/settings/sections/GeneralSection.tsx (Input×25)<br>ember/pages/settings/sections/MediaSection.tsx (Input×2)<br>ember/pages/settings/sections/OcrSection.tsx (Input×6)<br>ember/pages/settings/sections/PromptSection.tsx (Textarea×1)<br>ember/pages/settings/sections/ProviderDialog.tsx (Input×3)<br>ember/pages/settings/sections/ProviderModels.tsx (Input×2)<br>ember/pages/settings/sections/TranscriberSection.tsx (Input×11) |
| ember/ui/Progress.tsx | Progress | 2 | ember/features/workspace/TaskCard.tsx (Progress×1)<br>ember/features/workspace/TaskProgressCard.tsx (Progress×1) |
| ember/ui/Select.tsx | SelectOption, Select | 4 | ember/features/workspace/GenerationOptions.tsx (Select×5)<br>ember/pages/settings/sections/GlobalModelPicker.tsx (Select×1)<br>ember/pages/settings/sections/ProviderDialog.tsx (Select×1)<br>ember/pages/settings/sections/TranscriberSection.tsx (Select×3) |
| ember/ui/Skeleton.tsx | Skeleton | 8 | ember/features/workspace/TaskList.tsx (Skeleton×3)<br>ember/pages/settings/sections/GeneralSection.tsx (Skeleton×2)<br>ember/pages/settings/sections/MediaSection.tsx (Skeleton×1)<br>ember/pages/settings/sections/ModelSection.tsx (Skeleton×2)<br>ember/pages/settings/sections/MonitorSection.tsx (Skeleton×1)<br>ember/pages/settings/sections/OcrSection.tsx (Skeleton×1)<br>ember/pages/settings/sections/PromptSection.tsx (Skeleton×1)<br>ember/pages/settings/sections/TranscriberSection.tsx (Skeleton×1) |
| ember/ui/Spinner.tsx | Spinner | 6 | ember/EmberApp.tsx (Spinner×1)<br>ember/features/workspace/BatchImportPanel.tsx (Spinner×1)<br>ember/features/workspace/TaskProgressCard.tsx (Spinner×1)<br>ember/pages/OnboardingPage.tsx (Spinner×1)<br>ember/startup/StartupScreen.tsx (Spinner×1)<br>ember/ui/Button.tsx (Spinner×1) |
| ember/ui/Switch.tsx | Switch | 5 | ember/features/workspace/BatchImportPanel.tsx (Switch×2)<br>ember/features/workspace/GenerationOptions.tsx (Switch×1)<br>ember/pages/settings/sections/GeneralSection.tsx (Switch×1)<br>ember/pages/settings/sections/OcrSection.tsx (Switch×1)<br>ember/pages/settings/sections/TranscriberSection.tsx (Switch×2) |
| ember/ui/Tabs.tsx | TabItem, Tabs | 3 | ember/features/reader/NotePanel.tsx (Tabs×1)<br>ember/features/workspace/GenerationOptions.tsx (Tabs×1)<br>ember/features/workspace/IntakePanel.tsx (Tabs×1) |
| ember/ui/Tooltip.tsx | Tooltip | 0 | **无静态调用者**（未发现动态注册，待核实） |

## 4. 后端 route（65条method/path源码枚举完整；调用链映射 PARTIAL）

覆盖口径：65/65 条 route 的 method/path/handler 已逐行列出并与 AST 对账；其中 52/65 条有明确的 BillNote_frontend service 与调用入口静态证据。其余 13/65 条仅有部分证据、人工核对项或待运行时确认，不能标记为完整双向映射。
| Method | Path | 位置 | 参数 | 响应 | 显式错误 | service | Web 调用者 |
|---|---|---|---|---|---|---|---|
| GET | /api/get_downloader_cookie/{platform} | config.py:31 get_cookie | platform:str | R.success | — | 内联/模块级实例 | services/downloader.ts:4 getDownloaderCookie |
| POST | /api/update_downloader_cookie | config.py:41 update_cookie | data:CookieUpdateRequest | R.success | — | 内联/模块级实例 | services/downloader.ts:8 updateDownloaderCookie |
| GET | /api/transcriber_config | config.py:90 get_transcriber_config | — | R.success | — | 内联/模块级实例 | services/transcriber.ts:105 getTranscriberConfig |
| GET | /api/whisper_models | config.py:175 list_whisper_models | — | R.success | — | 内联/模块级实例 | services/transcriber.ts:158 listWhisperModels |
| POST | /api/whisper_models | config.py:183 add_whisper_model | data:WhisperCustomModelRequest | R.success | R.error(msg=str(e)) | 内联/模块级实例 | services/transcriber.ts:163 addWhisperModel |
| DELETE | /api/whisper_models/{name} | config.py:194 delete_whisper_model | name:str | R.success | — | 内联/模块级实例 | services/transcriber.ts:168 deleteWhisperModel |
| POST | /api/transcriber_config | config.py:202 update_transcriber_config | data:TranscriberConfigRequest | R.success | R.error(msg=str(e)) | 内联/模块级实例 | services/transcriber.ts:117 updateTranscriberConfig |
| POST | /api/openai_asr | config.py:221 add_openai_asr | data:OpenAISREndpointRequest | R.success | R.error(msg=str(e)) | 内联/模块级实例 | services/transcriber.ts:123 addOpenaiAsr |
| POST | /api/openai_asr/{endpoint_id} | config.py:248 update_openai_asr | endpoint_id:str, data:OpenAISREndpointRequest | R.success | R.error(msg=str(e)) | 内联/模块级实例 | services/transcriber.ts:127 updateOpenaiAsr |
| DELETE | /api/openai_asr/{endpoint_id} | config.py:263 delete_openai_asr | endpoint_id:str | R.success | R.error(msg="端点不存在") | 内联/模块级实例 | services/transcriber.ts:131 deleteOpenaiAsr |
| POST | /api/openai_asr/{endpoint_id}/test | config.py:270 test_openai_asr | endpoint_id:str | R.success | R.error(msg="端点不存在"); R.error(msg=f"连接失败：{e}", data={"ok": False}) | 内联/模块级实例 | services/transcriber.ts:137（正则未命中，人工核对） |
| GET | /api/proxy_config | config.py:323 get_proxy_config | — | R.success | — | 内联/模块级实例 | services/proxy.ts:11 getProxyConfig |
| POST | /api/proxy_config | config.py:335 update_proxy_config | data:ProxyConfigRequest | R.success | — | 内联/模块级实例 | services/proxy.ts:18 updateProxyConfig |
| GET | /api/transcriber_models_status | config.py:435 get_transcriber_models_status | — | R.success | — | dl_state(transcriber) | services/transcriber.ts:144 getModelsStatus |
| POST | /api/transcriber_download | config.py:546 download_transcriber_model | data:ModelDownloadRequest, background_tasks:BackgroundTasks | R.success | R.error(msg=f"不支持的模型: {data.model_size}（请先在自定义模型中登记）") | dl_state(transcriber) | services/transcriber.ts:148 downloadModel |
| GET | /api/sys_health | config.py:560 sys_health | — | R.success | — | 内联/模块级实例 | services/system.ts:21 getSysHealth |
| GET | /api/sys_check | config.py:606 sys_check | — | R.success | — | 内联/模块级实例 | ember/pages/OnboardingPage.tsx:44 ?<br>hooks/useCheckBackend.ts:46 ?<br>hooks/useCheckBackend.ts:52 ?<br>hooks/useCheckBackend.ts:146 useCheckBackend |
| GET | /api/deploy_status | config.py:615 deploy_status | — | R.success | — | 内联/模块级实例 | services/system.ts:51 getDeployStatus |
| GET | /api/general/settings | general.py:74 read_general_settings | — | R.success | R.error(f"读取通用设置失败：{exc}", code=500) | get_active_model(services.active_model), get_general_settings(db.general_settings_dao) | services/general.ts:190 getGeneralSettings |
| POST | /api/general/settings | general.py:85 write_general_settings | data:GeneralSettingsRequest | R.success | R.error(f"保存通用设置失败：{exc}", code=500) | update_general_settings(db.general_settings_dao) | services/general.ts:218 updateGeneralSettings |
| POST | /api/general/active_model | general.py:124 activate_model | data:ActiveModelRequest | R.success | R.error(f"激活 LLM 模型失败：{exc}", code=500); R.error(str(exc), code=400) | set_active_model(services.active_model) | services/general.ts:194 activateGlobalModel |
| GET | /api/general/active_model/options | general.py:135 read_active_model_options | — | R.success | R.error(f"读取全局模型候选失败：{exc}", code=500) | list_global_model_options(services.active_model) | services/general.ts:212 getGlobalModelOptions |
| GET | /api/media/settings | media.py:43 read_retention_settings | — | R.success | — | get_retention_settings(services.media_resource_service) | services/media.ts:27 getRetentionSettings |
| PUT | /api/media/settings | media.py:48 write_retention_settings | data:RetentionRequest | R.success | — | set_retention_settings(services.media_resource_service) | services/media.ts:29 saveRetentionSettings |
| GET | /api/media/cleanup/recent | media.py:57 read_recent_cleanup_runs | — | R.success | — | get_recent_cleanup_runs(services.media_resource_service) | services/media.ts:31 getRecentCleanupRuns |
| GET | /api/media/cleanup/preview | media.py:62 read_cleanup_preview | resource_types:str, expired_only:bool | R.success | R.error("资源类别无效", code=400) | preview_cleanup(services.media_resource_service) | services/media.ts:36 previewMediaCleanup |
| POST | /api/media/cleanup | media.py:72 run_cleanup | data:CleanupRequest | R.success | R.error("资源类别无效", code=400) | cleanup_resources(services.media_resource_service), preview_cleanup(services.media_resource_service) | services/media.ts:49 runMediaCleanup |
| GET | /api/media/cache/limit | media.py:94 read_cache_limit | — | R.success | — | get_cache_settings(services.media_resource_service), preview_cache_limit(services.media_resource_service) | **无 Web 调用者** |
| POST | /api/media/cache/enforce | media.py:106 run_cache_enforce | — | R.success | — | enforce_cache_limit(services.media_resource_service) | **无 Web 调用者** |
| GET | /api/model_list | model.py:17 model_list | — | R.success | R.error(e) | 内联/模块级实例 | services/model.ts:85 fetchModels<br>services/model.ts:103 fetchEnableModels |
| GET | /api/models/delete/{model_id} | model.py:23 delete_model | model_id:int | R.success | R.error("模型不存在或删除失败"); R.error(f"删除模型失败: {e}") | 内联/模块级实例 | services/model.ts:107 deleteModelById |
| GET | /api/model_list/{provider_id} | model.py:33 model_list | provider_id | R.success | — | 内联/模块级实例 | services/model.ts:85 fetchModels<br>services/model.ts:103 fetchEnableModels |
| POST | /api/models | model.py:39 create_model | data:CreateModelRequest | R.success | R.error("供应商不存在", code=400, data={"reason": "provider_not_found"}); R.error("模型已存在", code=400, data={"reason": "model_name_exists"}); R.error("模型添加失败") | ModelService(services.model) | services/model.ts:99 addModel |
| GET | /api/model_enable/{provider_id} | model.py:50 get_enabled_models_by_provider | provider_id:str | R.success | R.error(f"获取启用模型失败: {e}") | 内联/模块级实例 | services/model.ts:95 fetchEnableModelById |
| POST | /api/v1/intake/resolve | note.py:88 resolve_intake | data:IntakeResolveRequest | R.success | R.error("mode must be single or batch", code=400); R.error("single mode accepts one URL", code=400) | resolve_bilibili_inputs(services.source_intake) | services/note.ts:48 (resolveIntake)（正则未命中，人工核对） |
| POST | /api/upload | note.py:1593 upload | file:UploadFile | R.success | — | 内联/模块级实例 | services/upload.ts:5 uploadFile |
| POST | /api/generate_note | note.py:1605 generate_note | data:VideoRequest, background_tasks:BackgroundTasks | R.success | HTTPException(status_code=500, detail=str(e)); R.error(                     msg=readiness["reason"],                     code=300102,    ; R.error(                 msg="该视频正在生成中，请稍候",                 code=300103,                 ; R.error(                 msg=disk_error,                 code=300104,                 data; R.error(msg="无法识别视频标识", code=400) | NoteGenerator(services.note), TaskStatus(enmus.task_status_enums), extract_video_id(utils.url_parser), resolve_active_model(services.active_model) | services/note.ts:154 generateNote |
| POST | /api/expand | note.py:1745 expand | data:ExpandRequest | R.success | R.error(msg="无法从链接中解析 BV 号", code=400); R.error(msg="链接不能为空", code=400); R.error(msg=f"展开失败: {e}") | extract_video_id(utils.url_parser), fetch_collection(downloaders.bilibili_expand), parse_bilibili_collection_url(utils.url_parser) | services/note.ts:341 expandUrl |
| POST | /api/generate_notes | note.py:1790 generate_notes | data:BatchGenerateRequest, background_tasks:BackgroundTasks | R.success | R.error(                 msg=disk_error,                 code=300104,                 data; R.error(                 msg=readiness["reason"],                 code=300102,            ; R.error(             msg=f"新建分组失败：{e}",             code=300105,             data={"reason; R.error(msg=f"批量生成失败: {e}"); R.error(msg=str(exc), code=400) | NoteGenerator(services.note), TaskStatus(enmus.task_status_enums), resolve_active_model(services.active_model) | services/note.ts:359 generateNotes |
| POST | /api/task_archives | note.py:1919 download_task_archives | data:BatchArchiveRequest | 文件/二进制 | R.error("请选择至少一篇已完成笔记", code=400); R.error(f"一次最多归档 {MAX_BATCH_ARCHIVE_TASKS} 篇笔记", code=400); R.error(f"批量笔记归档导出失败：{exc}", code=500); R.error(str(exc), code=400) | NoteArchiveError(utils.note_archive) | services/note.ts:99 downloadNoteArchives |
| GET | /api/task_archive/{task_id} | note.py:2066 download_task_archive | task_id:str | 文件/二进制 | R.error("任务标识无效", code=400); R.error("笔记不存在或尚未生成", code=404); R.error("笔记内容为空，无法导出", code=404); R.error(f"笔记归档导出失败：{exc}", code=500); R.error(str(exc), code=400) | NoteArchiveError(utils.note_archive) | services/note.ts:79 downloadNoteArchive |
| GET | /api/v1/task-groups/events | note.py:2268 get_task_groups_events | request:Request, task_ids:list[str], source:str, since:int | SSE | R.error("一次最多订阅 1000 个任务", code=400) | 内联/模块级实例 | services/note.ts:462 subscribeTaskReadModel |
| GET | /api/v1/task-groups/snapshot | note.py:2326 get_task_groups_snapshot | task_ids:list[str], source:str | R.success | — | 内联/模块级实例 | services/note.ts:449（正则未命中，人工核对） |
| POST | /api/task_status/batch | note.py:2352 get_task_status_batch | data:BatchStatusRequest | R.success | R.error("一次最多查询 1000 个任务状态", code=400); R.error(f"批量查询任务状态失败：{exc}", code=500) | 内联/模块级实例 | services/note.ts:411 getTaskStatusBatch |
| GET | /api/task_status/{task_id} | note.py:2385 get_task_status | task_id:str | R.success | R.error(                 message or "任务失败",                 code=500,                 data | TaskStatus(enmus.task_status_enums) | services/note.ts:248 get_task_status |
| GET | /api/task_list | note.py:2571 list_tasks | — | R.success | R.error(f"列出任务失败：{exc}", code=500) | 内联/模块级实例 | services/note.ts:210 listTasks |
| POST | /api/delete_task_record | note.py:2630 delete_task_record | data:TaskIdRequest | R.success | R.error("任务标识无效", code=400); R.error("缺少 task_id", code=400); R.error(f"删除任务记录失败：{exc}", code=500); R.error(str(exc), code=CODE_TASK_IN_FLIGHT) | TaskInFlightError(services.task_cleanup) | services/note.ts:221 deleteTaskRecord |
| POST | /api/delete_task_records | note.py:2663 delete_task_records | data:BatchDeleteRequest | R.success | R.error("缺少 task_ids", code=400); R.error(f"一次最多删除 {MAX_BATCH_DELETE} 条", code=400) | TaskInFlightError(services.task_cleanup) | services/note.ts:241 deleteTaskRecords |
| GET | /api/image_proxy | note.py:2713 image_proxy | request:Request, url:str | 文件/二进制 | HTTPException(status_code=500, detail=str(e)); HTTPException(status_code=resp.status_code, detail="图片获取失败") | 内联/模块级实例 | 浏览器扩展 BillNote_extension/src/logic/api.ts:195–204 resolveImageUrl（扩展逐项映射范围外）；BillNote_frontend 无运行时 URL caller |
| POST | /api/retry_failed_tasks | note.py:2751 retry_failed_tasks_endpoint | data:RetryFailedRequest | R.success | R.error(                 msg=disk_error,                 code=300104,                 data; R.error(                 msg=readiness["reason"],                 code=300102,            ; R.error("scope 只能是 all 或 group", code=400); R.error(f"重试失败任务失败：{exc}", code=500) | 内联/模块级实例 | services/note.ts:507 retryFailedTasks |
| GET | /api/note_group | note_group.py:82 get_groups | — | R.success | R.error(f"列出笔记分组失败：{exc}", code=500) | MAX_GROUPS(db.note_group_dao), MAX_GROUP_NAME_LENGTH(db.note_group_dao), list_groups(db.note_group_dao) | services/noteGroup.ts:29 listNoteGroups |
| POST | /api/note_group | note_group.py:105 post_group | data:GroupRequest | R.success | R.error(f"新建笔记分组失败：{exc}", code=500); R.error(str(exc), code=400) | NoteGroupError(db.note_group_dao), create_group(db.note_group_dao) | services/noteGroup.ts:34 createNoteGroup |
| POST | /api/note_group/rename | note_group.py:118 post_rename | data:GroupRenameRequest | R.success | R.error(f"重命名笔记分组失败：{exc}", code=500); R.error(str(exc), code=400) | NoteGroupError(db.note_group_dao), rename_group(db.note_group_dao) | services/noteGroup.ts:42 renameNoteGroup |
| POST | /api/note_group/delete | note_group.py:131 post_delete | data:GroupDeleteRequest | R.success | R.error(f"删除笔记分组失败：{exc}", code=500); R.error(str(exc), code=400) | NoteGroupError(db.note_group_dao), delete_group(db.note_group_dao) | services/noteGroup.ts:67 deleteNoteGroup |
| POST | /api/note_group/assign | note_group.py:181 post_assign | data:TaskGroupRequest | R.success | R.error(f"移动任务到分组失败：{exc}", code=500); R.error(str(exc), code=400) | NoteGroupError(db.note_group_dao), assign_task_to_group(db.note_group_dao) | services/noteGroup.ts:78 assignTaskToGroup |
| POST | /api/note_group/assign_batch | note_group.py:196 post_assign_batch | data:TasksGroupRequest | R.success | R.error(f"批量移动任务到分组失败：{exc}", code=500); R.error(str(exc), code=400) | NoteGroupError(db.note_group_dao), assign_tasks_to_group(db.note_group_dao) | services/noteGroup.ts:86 assignTasksToGroup |
| GET | /api/note_group/tasks | note_group.py:211 get_group_tasks | group_id:Optional[str] | R.success | R.error(f"列出分组内任务失败：{exc}", code=500) | 内联/模块级实例 | services/noteGroup.ts:96 listGroupTaskIds |
| GET | /api/ocr_config | ocr.py:56 get_ocr_config | — | R.success | — | 内联/模块级实例 | services/ocr.ts:57 getOcrConfig |
| POST | /api/ocr_config | ocr.py:62 update_ocr_config | data:OcrConfigRequest | R.success | R.error(msg=f"保存 OCR 配置失败：{exc}", code=500); R.error(msg=str(exc), code=400) | 内联/模块级实例 | services/ocr.ts:61 updateOcrConfig |
| POST | /api/ocr_config/test | ocr.py:80 test_ocr_config | data:Optional[OcrConfigRequest] | R.success | R.error(msg=result.get("message") or "连接失败", code=400, data=result) | build_ocr_client(services.ocr_client) | services/ocr.ts:66 testOcrConfig |
| POST | /api/add_provider | provider.py:41 add_provider | data:ProviderRequest | R.success | R.error(msg=e); R.error(msg=str(e), code=400, data={'reason': 'provider_name_exists'}) | ProviderNameExistsError(exceptions.provider), ProviderService(services.provider) | services/model.ts:66 addProvider |
| GET | /api/get_all_providers | provider.py:60 get_all_providers | — | R.success | R.error(msg=e) | ProviderService(services.provider) | services/model.ts:30 getProviderList |
| GET | /api/get_provider_by_id/{id} | provider.py:68 get_provider_by_id | id:str | R.success | R.error(msg=e) | ProviderService(services.provider) | services/model.ts:33 getProviderById |
| POST | /api/update_provider | provider.py:85 update_provider | data:ProviderUpdateRequest | R.success | R.error(msg='更新模型供应商失败'); R.error(msg='请至少填写一个参数'); R.error(msg=str(e)) | ProviderService(services.provider) | services/model.ts:62 updateProviderById |
| POST | /api/connect_test | provider.py:107 gpt_connect_test | data:TestRequest | R.success | — | ModelService(services.model) | services/model.ts:70 testConnection |

### 4.1 静态 caller 反查（不以静态无引用判断死代码）
证据：本轮在 BillNote_frontend/src 对 request.get/post/put/delete/patch、fetch、EventSource 进行静态搜索，并逐route path比对；BillNote_extension另独立搜索image_proxy。静态结果不代表页面运行验证；image_proxy Web caller维持UNVERIFIED，见§4.1及§9。
- 当前 Web (`BillNote_frontend`) 未发现调用的 backend routes：`GET /api/media/cache/limit`（media.py:94）、`POST /api/media/cache/enforce`（media.py:106）。spec 007:158 与 009:136 将 media/cache 能力列为后端验收接口；归类为无 Web caller 的运维/后端 API，非死代码结论。
- `/api/image_proxy` 的 extension caller 已确认（BillNote_extension/src/logic/api.ts:195–204），但扩展逐组件映射属范围外。Web 本地截图由 backend 写为根相对 `/static/screenshots/...`；MarkdownNote→resolveAssetUrl 将根路径映射到 ASSET_ORIGIN，不经过image_proxy。没有真实外链Markdown笔记验证模型输出图片是否进入Web reader，因此Web image_proxy caller状态为UNVERIFIED，非已确认无caller。



### 4.3 当前 13-route 声明复核（逐项证据校正）

复核方法：在 T-046 worktree 根目录以 Python `ast` 遍历 `backend/app/routers/*.py` 中 `.get/.post/.put/.delete/.patch` 装饰器，得到 65 个 `(method,path)` rows；另将 §4 表逐行与 AST 对照（65/65 rows）。对前端先检查服务包装，再继续追 JSX、hook、store、路由或动态注册，不能仅凭包装函数存在判为有用户入口。

| Route | Web 调用/用户入口及证据 | 结论 |
|---|---|---|
| `POST /api/openai_asr/{endpoint_id}/test` | `services/transcriber.ts:testOpenaiAsr:134–141` → `TranscriberSection.tsx` 的端点测试动作；backend `config.py:test_openai_asr:270–312` 以临时 WAV 探测 endpoint。原 §4 仅因正则未命中标疑；本轮 CodeGraph/source 核实了静态调用链。未实际执行外部 ASR 请求。 | 静态 caller 已证；运行验证未做 |
| `GET /api/sys_check` | `hooks/useCheckBackend.ts:51–76` 请求 health probe，`useCheckBackend:141–159` 轮询和更新启动状态；`EmberApp.tsx:24–41` 用 hook 决定启动屏/重试。 | 静态 caller 已证 |
| `GET /api/media/cache/limit` | 前端全 `src` URL/callsite 搜索未发现；backend `media.py:94` 是运维 API，底层 cache service 另由内部清理流程使用。 | 无 Web caller 证据；保留为 backend 运维能力，非死代码结论 |
| `POST /api/media/cache/enforce` | 同上，`media.py:106`；前端无 route URL/callsite，底层 `enforce_cache_limit` 有内部调度/调用。 | 无 Web caller 证据；backend-only/运维边界待 spec 确认 |
| `POST /api/v1/intake/resolve` | `services/note.ts:43–52 resolveIntake` → `BatchImportPanel.tsx:209–238` 的解析/提交步骤；backend `note.py:88–93` 调 `resolve_bilibili_inputs`。 | 静态 caller 已证（旧正则漏报）；真实浏览器批量路径待跑 |
| `GET /api/v1/task-groups/snapshot` | `services/note.ts:445–452 getTaskReadModelSnapshot` → `hooks/useTaskPolling.ts:97–117` 的 SSE 断开 fallback / 轮询 → taskStore 状态更新；backend `note.py:2326` 构造快照。 | 静态 caller 已证（旧正则漏报） |
| `GET /api/image_proxy` | BillNote Web reader 本地截图路径是 `MarkdownNote.tsx` → `resolveAssetUrl` (`assets.ts:25–29`) → `/static/screenshots`；Web `src` 未找到 `/api/image_proxy` URL 构造。扩展 caller 已核实但扩展组件映射范围外。尚无真实 external-image Markdown 样本。 | Web 静态 caller 未发现；运行时外链样本待核，不能断言无动态 caller |
| `GET /api/proxy_config` | `services/proxy.ts:getProxyConfig` 有包装，但整个 `BillNote_frontend/src` 无 importer/组件调用者；backend handler读 `ProxyConfigManager`。 | 包装无 UI 入口；静态未引用候选，动态/外部消费待核 |
| `POST /api/proxy_config` | `services/proxy.ts:updateProxyConfig` 有包装，但整个 `src` 无 importer/用户入口；backend handler写 `config/proxy.json`。 | 包装无 UI 入口；静态未引用候选，动态/外部消费待核 |
| `POST /api/upload` | `services/upload.ts:uploadFile` 有包装，但 `BillNote_frontend/src` 无 importer/调用者；backend `note.py:1593` 写上传文件。 | 包装无 UI 入口；动态/外部消费待核 |
| `POST /api/task_status/batch` | `services/note.ts:410–412 getTaskStatusBatch` 包装存在，但当前 `useTaskPolling.ts` 的 SSE 断开 fallback 实际调用 `getTaskReadModelSnapshot`，不是此包装；未找到当前 Web runtime importer。旧 report §9 将它按 service 包装列入端到端 polling 链，证据过强。 | 当前用户流程调用未证；不能计作明确 caller，需继续查 legacy/runtime consumer |
| `GET /api/task_status/{task_id}` | `services/note.ts:244–252 get_task_status` → `store/taskStore/index.ts` 的 `rehydrateTask` 详情内容加载路径；用于成功状态后读取完整 markdown/transcript，而当前进度轮询由 SSE/snapshot 承担。 | 静态 caller 已证（详情 rehydrate，不是主轮询） |
| `POST /api/task_archives` | `services/note.ts:99` 的批量归档下载包装 → `useNoteGroups.ts:167–188 downloadCheckedGroups` → `GroupPanel/Workspace` 分组选中已完成任务后下载。 | 静态 caller 已证；真实下载路径待浏览器验证 |

计数处理：原 §0/§4 将“52/65明确 caller、13/65待核”作为汇总，但没有列出 13 条确切 route 集合，不能将其当作可复现 row set。本轮发现此前 caller 证据评级有误：至少 `/task_status/batch` 虽有包装函数，当前无 importer；另有数条旧 regex miss 实际有明确 caller。因而本表把明确链、无 Web caller、包装未消费和运行时待核分别列出；全 65 条 route 的逐行 UI 行为仍须完成后，才可给新的完整分母。此 13-row 复核表不是声称其余 52 条已完成逐符号验收。

### 4.2 Web 模块无入口
- `services/proxy.ts`（/proxy_config）、`services/upload.ts`（/upload）、`ember/ui/Tooltip.tsx`：整个 BillNote_frontend/src 中未找到静态导入/组件caller，标记静态未引用候选；动态导入/外部使用待核。此处不推断删除或新增接线。

## 5. spec 矩阵（PARTIAL）
| spec | 状态 | 前端测试（数） | 后端测试（数） | 本轮 | 符号链接 |
|---|---|---|---|---|---|
| 001-bilibili-batch-import | 未标注 | BillNote_frontend/tests/001-bilibili-batch-import (11) | backend/tests/001-bilibili-batch-import (60) | 单项套件 NOT RUN；仅由全量套件覆盖，见 §6（逐 spec 通过未证明） | UNVERIFIED_LINK（逐符号链接 pending） |
| 002-video-understanding-sampling | 未标注 | 无 | backend/tests/002-video-understanding-sampling (47) | 单项套件 NOT RUN；仅由全量套件覆盖，见 §6（逐 spec 通过未证明） | UNVERIFIED_LINK（逐符号链接 pending） |
| 003-openai-compatible-asr | 未标注 | 无 | backend/tests/003-openai-compatible-asr (46) | 单项套件 NOT RUN；仅由全量套件覆盖，见 §6（逐 spec 通过未证明） | UNVERIFIED_LINK（逐符号链接 pending） |
| 004-note-math-rendering | 未标注 | BillNote_frontend/tests/004-note-math-rendering (7) | 无同号目录 | 单项套件 NOT RUN；仅由全量套件覆盖，见 §6（逐 spec 通过未证明） | UNVERIFIED_LINK（逐符号链接 pending） |
| 005-modern-dark-ui-and-task-progress | 未标注 | BillNote_frontend/tests/005-modern-dark-ui (46) | backend/tests/005-modern-dark-ui-and-task-progress (48) | 单项套件 NOT RUN；仅由全量套件覆盖，见 §6（逐 spec 通过未证明） | UNVERIFIED_LINK（逐符号链接 pending） |
| 006-note-pipeline-performance | 未标注 | 无 | backend/tests/006-note-pipeline-performance (27) | 单项套件 NOT RUN；仅由全量套件覆盖，见 §6（逐 spec 通过未证明） | UNVERIFIED_LINK（逐符号链接 pending） |
| 007-note-archive-and-media-cache | 未标注 | 无 | backend/tests/007-note-archive-and-media-cache (69) | 单项套件 NOT RUN；仅由全量套件覆盖，见 §6（逐 spec 通过未证明） | UNVERIFIED_LINK（逐符号链接 pending） |
| 008-ocr-assist-and-legacy-cleanup | 未标注 | 无 | backend/tests/008-ocr-assist-and-legacy-cleanup (145) | 单项套件 NOT RUN；仅由全量套件覆盖，见 §6（逐 spec 通过未证明） | UNVERIFIED_LINK（逐符号链接 pending） |
| 009-batch-grouping-and-long-run-robustness | 未标注 | 无 | backend/tests/009-batch-grouping-and-long-run-robustness (97) | 单项套件 NOT RUN；仅由全量套件覆盖，见 §6（逐 spec 通过未证明） | UNVERIFIED_LINK（逐符号链接 pending） |
| 010-group-and-note-deletion | 未标注 | BillNote_frontend/tests/010-group-and-note-deletion (3) | backend/tests/010-group-and-note-deletion (24) | 单项套件 NOT RUN；仅由全量套件覆盖，见 §6（逐 spec 通过未证明） | UNVERIFIED_LINK（逐符号链接 pending） |
| 011-failed-task-retry | 未标注 | 无 | backend/tests/011-failed-task-retry (17) | 单项套件 NOT RUN；仅由全量套件覆盖，见 §6（逐 spec 通过未证明） | UNVERIFIED_LINK（逐符号链接 pending） |
| 012-rate-limit-backoff | implemented | 无 | backend/tests/012-rate-limit-backoff (29) | 单项套件 NOT RUN；仅由全量套件覆盖，见 §6（逐 spec 通过未证明） | UNVERIFIED_LINK（逐符号链接 pending） |
| 013-local-transcriber-hardware-acceleration | implemented | 无 | backend/tests/013-global-active-model (4) | 单项套件 NOT RUN；仅由全量套件覆盖，见 §6（逐 spec 通过未证明） | UNVERIFIED_LINK（逐符号链接 pending） |
| 014-backend-cache-optimization | implemented | 无 | backend/tests/014-backend-cache-optimization (97) | 单项套件 NOT RUN；仅由全量套件覆盖，见 §6（逐 spec 通过未证明） | UNVERIFIED_LINK（逐符号链接 pending） |
| 015-note-preset-scene-and-detail | implemented | BillNote_frontend/tests/015-note-preset-scene-and-detail (6) | backend/tests/015-note-preset-scene-and-detail (54) | 单项套件 NOT RUN；仅由全量套件覆盖，见 §6（逐 spec 通过未证明） | UNVERIFIED_LINK（逐符号链接 pending） |
| 016-web-startup-optimization | 未标注 | 无 | 无同号目录 | NOT RUN：无同号测试 | UNVERIFIED_LINK（逐符号链接 pending） |
| 017-web-rebuild-and-architecture | implemented | 无 | backend/tests/017-web-rebuild-and-architecture (76) | 单项套件 NOT RUN；仅由全量套件覆盖，见 §6（逐 spec 通过未证明） | UNVERIFIED_LINK（逐符号链接 pending） |
| 018-single-batch-and-merged-note | implemented | BillNote_frontend/tests/018-single-batch-and-merged-note (4) | backend/tests/018-single-batch-and-merged-note (25) | 单项套件 NOT RUN；仅由全量套件覆盖，见 §6（逐 spec 通过未证明） | UNVERIFIED_LINK（逐符号链接 pending） |
| 019-global-model-in-provider-section | implemented | BillNote_frontend/tests/019-global-model-in-provider-section (4) | backend/tests/019-global-model-in-provider-section (6) | 单项套件 NOT RUN；仅由全量套件覆盖，见 §6（逐 spec 通过未证明） | UNVERIFIED_LINK（逐符号链接 pending） |
| 020-note-rendering-and-batch-options | implemented | BillNote_frontend/tests/020-note-rendering-and-batch-options (10) | backend/tests/020-note-rendering-and-batch-options (4) | 单项套件 NOT RUN；仅由全量套件覆盖，见 §6（逐 spec 通过未证明） | UNVERIFIED_LINK（逐符号链接 pending） |

测试数来源：后端用 pytest --collect-only，前端用 vitest json。当前表格只记录每个 spec 的测试目录与收集数量，不是逐测试文件的 spec→符号证据；逐项具体测试文件、符号和契约链接仍待补齐，因此每行保持 UNVERIFIED_LINK / NOT RUN。另有前端 onboardingTranscriber（9）和后端顶层 test_*.py（78）未归属任何 spec。backend/tests/013-global-active-model 与 specs/013-local-transcriber-hardware-acceleration 命名不一致，待核实。

## 6. 门禁（VERIFIED_RUN，本轮执行）
工作目录均为 T-046 专属 worktree。
| 命令（相对目录） | exit | 汇总 |
|---|---|---|
| BillNote_frontend: pnpm exec vitest run | 0 | 17 个文件 / 100 个测试通过 |
| BillNote_frontend: pnpm exec tsc -b | 0 | 类型检查完成，无输出 |
| BillNote_frontend: pnpm lint（脚本实际 eslint .） | 0 | 无 lint 错误 |
| BillNote_frontend: pnpm build | 0 | 3158 modules；两个 chunk >500kB 警告 |
| backend: .venv/bin/python -m pytest -q -p no:cacheprovider | 0 | 953 passed，15 subtests，1 个 pkg_resources warning |
| backend 首次尝试 .venv/Scripts/python.exe -m pytest --collect-only -q -p no:cacheprovider（Bash） | 127 | 路径不存在；后续改用POSIX虚拟环境并运行全套，见上 |

## 7. 浏览器主路径（PARTIAL）
实际操作：通过 dsh_browser_open 打开 http://127.0.0.1:3015/；页面标题 BiliNote - 强大的AI视频笔记神器，文本含工作区、单集/批量入口、空任务列表、分组空态；确认后端通过前端状态可响应。点击「设置」时当前浏览器状态先因首次启动 guard 重定向至 /onboarding；直接打开该路径看到「首次启动 / 欢迎使用 BiliNote / 后端连通性 / 后端已就绪，可以继续」。该路由页面 DOM 内容可见，但 dsh_browser_snapshot 在部分路由未稳定时曾返回零节点；dsh_browser_execute 确认 onboarding 按钮存在。重新直接打开 /settings/general 后读取页面：设置导航含通用、模型、转写、OCR、提示词、媒体、下载、部署、关于；通用设置字段可见、保存按钮因无改动 disabled。
浏览器证据分来源：本worker在本轮通过dsh_browser实际读取workspace空态、/settings/general通用设置和/onboarding后端就绪状态；2026-11-07 11:14 Flow dispatcher c_mw6b5...提供只读复验记录：从Settings导航逐页读取九个子路由（general/model/transcriber/ocr/prompt/media/download/monitor/about），另含首页/onboarding，主体内容/控件被记录。该消息提供静态结果摘要，非本worker本轮重新执行的dsh历史。生成提交、失败任务选择/重试、批量展开选择、实际笔记reader、配置写入均NOT RUN：空DB，缺少安全测试种子/清理流程；设置保存、下载模型和清理操作会写持久数据，因此未执行。验收第6条仍不满足。


## 9. Route→service→Web UI 静态交叉索引（PARTIAL，source-only）
证据等级：method/path集合与handler由Python AST核验；第4节有65条静态route行并记录请求参数/响应错误摘要及可观察的直接调用。直接调用不一定是完整业务service链。TS/TSX caller链仅为下表列出的静态部分路径；spec矩阵存在UNVERIFIED_LINK，故不能据此声称65条均已端到端映射。此索引不代表真实用户流程测试。

| 业务链 | API route | 前端调用/用户入口 | 状态/呈现证据与当前边界 |
|---|---|---|---|
| 单条 intake/generate | POST /api/v1/intake/resolve; POST /api/generate_note | services/note.ts:resolveIntake/generateNote → ember/features/workspace/IntakeForm.tsx → IntakePanel.tsx → WorkspacePage.tsx → EmberApp.tsx / | IntakeForm 本地 react-hook-form 状态、URL 校验、提交/loading 与 toast；成功先 addPendingTask 并进入 taskStore。无本轮真实提交；错误状态依 service/global request interceptor 与 catch/toast。 |
| 批量展开/提交 | POST /api/expand; POST /api/generate_notes | services/note.ts:expandUrl/generateNotes → BatchImportPanel.tsx → IntakePanel.tsx → WorkspacePage.tsx → / | BatchImportPanel local stage input/picking、resolving、videos/selected/groupName/merge/submitting；全 URL 失败 toast、逐 URL null 部分失败、提交成功回调由 store刷新。无浏览器主路径运行；静态链证据。 |
| 任务列表/详情状态 | GET /api/task_list; GET /api/task_status/{task_id}; POST /api/task_status/batch; GET /api/v1/task-groups/snapshot; GET /api/v1/task-groups/events | services/note.ts:listTasks/get_task_status/getTaskStatusBatch/getTaskReadModelSnapshot/subscribeTaskReadModel → taskStore/index.ts → WorkspacePage/TaskList/TaskCard/TaskProgressCard/NotePanel → EmberApp:/ | WorkspacePage listLoading 初始 true，loadTasks.finally 关闭；TaskList loading Skeleton / 空态 EmptyState / 筛选与搜索；poll hook 当前使用 SSE 与 snapshot fallback。getTaskStatusBatch 有 service wrapper，但未找到当前 Web runtime importer，不计作明确 caller。reader 以 task.markdown 状态显示 empty/markdown/transcript。无带真实task的浏览器运行。 |
| 单条删除/批量删除/归档 | POST /api/delete_task_record; POST /api/delete_task_records; GET /api/task_archive/{task_id}; POST /api/task_archives | services/note.ts:deleteTaskRecord/deleteTaskRecords/downloadNoteArchive(s) → TaskList/useNoteGroups/NotePanel 调用链 | delete busy/选择与服务错误由调用UI处理；archive 判断 HTTP及Content-Type，JSON错误转可读异常。没有本轮实际删除/下载验证。 |
| 失败重试 | POST /api/retry_failed_tasks | services/note.ts:retryFailedTasks → retryFailed.ts:retrySelectedFailedTasks → WorkspacePage.retryFailedInScope → TaskList/RetryFailedAction | 空选择 helper 不调用；none/partial/done toast；catch错误 toast；成功 reload。当前 DB 空，没有失败任务，未实际选中或执行。 |
| 任务分组 | GET/POST /api/note_group; POST /api/note_group/rename,/delete,/assign,/assign_batch; GET /api/note_group/tasks | services/noteGroup.ts → useNoteGroups.ts → WorkspacePage → GroupPanel/TaskList | useNoteGroups loading/busy/downloading 状态、refresh catch console.warn、create/rename mutation catch toast、assignment 后 reload；GroupPanel空组与TaskList空态可达。浏览器本轮只见空组/空任务；CRUD及drag未运行。 |
| Provider/model | GET /api/get_all_providers; GET /api/get_provider_by_id/{id}; POST /api/add_provider,/update_provider,/connect_test; GET /api/model_list[/ {provider_id}], /api/model_enable/{provider_id}; POST /api/models; GET /api/models/delete/{model_id} | services/model.ts → OnboardingPage/ModelSection/ProviderDialog/ProviderModels/GlobalModelPicker；general active_model routes 另见下一链 | useAsync/section local loading/error与空态组件存在；ProviderDialog submit saving、字段缺值 disabled、catch toast、成功 toast/onDone（已从符号源码核验）。未写入或连接真实provider。 |
| 通用/全局模型设置 | GET/POST /api/general/settings; POST /api/general/active_model; GET /api/general/active_model/options | services/general.ts → GeneralSection/GlobalModelPicker/ModelSection/PromptSection/TranscriberSection → SettingsPage /settings/* | 通用设置页面本轮读取并显示现有字段；无更改时保存 disabled。写入/切换模型未执行；具体错误反馈由 useAsync/调用组件定义。 |
| OCR | GET/POST /api/ocr_config; POST /api/ocr_config/test | services/ocr.ts → OcrSection → SettingsPage:/settings/ocr | OcrSection通过useAsync呈现loading/error，save/test调用分别有返回与toast逻辑；本轮未点击测试或提交。 |
| 媒体保留/清理 | GET/PUT /api/media/settings; GET /api/media/cleanup/recent,/preview; POST /api/media/cleanup | services/media.ts → MediaSection → SettingsPage:/settings/media | settings读取/保存、cleanup preview/run分别走此页；run会删除过期媒体，未触发。 |
| 下载cookie | GET /api/get_downloader_cookie/{platform}; POST /api/update_downloader_cookie | services/downloader.ts → DownloadSection → SettingsPage:/settings/download | 页面只读加载已浏览器覆盖；cookie内容与写入没有操作/记录。 |
| 转写器配置/模型 | GET/POST /api/transcriber_config; GET/POST/DELETE /api/whisper_models[/{name}]; POST /api/openai_asr[/{endpoint_id}[/test]]; GET /api/transcriber_models_status; POST /api/transcriber_download | services/transcriber.ts → TranscriberSection/OnboardingPage → SettingsPage:/settings/transcriber 或 /onboarding | 本地config/model status、skeleton、saving/download状态及错误处理有静态调用链；创建/改写端点或模型下载均未执行。 |
| 启动/health/deploy | GET /api/sys_check,/sys_health,/deploy_status | services/system.ts → EmberApp/systemCheck/MonitorSection；useCheckBackend + OnboardingPage 直接 fetch sys_check | onboarding显示backend ready；system health与deploy页面读取链静态核实；详情运行状态未逐页执行。 |
| 上传 | POST /api/upload | services/upload.ts:uploadFile 有调用定义但 src 中无 importer | UI入口待核实；响应空url返回 {url:''}。不可据静态无入口断言死代码。 |
| 代理 | GET/POST /api/proxy_config | services/proxy.ts:getProxyConfig/updateProxyConfig 有调用定义但 src 中无 importer | UI入口待核实；Web service无静态导入者。 |
| 媒体缓存运维 | GET /api/media/cache/limit; POST /api/media/cache/enforce | BillNote_frontend/src 搜索没有 route URL/callsite；spec 007/009 后端测试覆盖其运维API | Web无caller；明确标为 backend-only/out-of-Web operation，扩展也未发现对应 URL。 |
| 图片代理（Web caller 条件待核） | GET /api/image_proxy | extension 的 BillNote_extension/src/logic/api.ts:195–204 resolveImageUrl 已确认构造URL（扩展范围外）；Web reader 链对本地截图走 /static → resolveAssetUrl | 后端 `_insert_screenshots` 和 `_insert_approved_screenshots` 将生成的截图URL写为 IMAGE_BASE_URL（默认 /static/screenshots）；静态搜索未发现模型原始 Markdown 外部图片被改写成 /api/image_proxy。Web runtime URL caller NOT FOUND (static)，外链笔记样本可达性 PENDING。 |

## 8. 发现分级（PARTIAL）
- 现有 spec 违规：暂无已复现
- 实现存在但验证不足：组件交互状态大多没有组件测试
- 无 UI 入口候选（不判死代码）：`services/proxy.ts` 的 getProxyConfig/updateProxyConfig 与 `/proxy_config` routes 有服务封装但全 src 无 importer；`services/upload.ts` 的 uploadFile 与 `/upload` route 无 importer；`ember/ui/Tooltip.tsx` 无组件 caller。动态注册/外部调用仍待核实。
- 范围外：media/cache/limit、media/cache/enforce
- 待核实：proxy/upload 是否由运行时动态导入或未来入口消费；013 测试目录命名。

## 10. README §6 逐项验收状态（当前：PARTIAL，不代表审计完成）

证据口径：静态源码/清单证据与真实本轮命令或浏览器运行证据分列。下表“PASS”只表示该具体子项有完整证据，不表示整卡通过。README §6 实际包含 10 项（第 1–10 条）；另有任务卡验收标准，未以此表替代。写路径隔离 SQLite 获授权 hi_mw6cc3rl5pom9z，但本轮没有 seed 或写入；不得把授权当作验证结果。

| README §6 | 状态 | 静态/文件证据 | 实际运行/浏览器证据 | 剩余差距 |
|---|---|---|---|---|
| 1. 全量枚举与组件/导出符号 | PARTIAL | §1–2：master 基线 c011bbdf 的 src 清单 100/100 与 git ls-files 对账；97 TS/TSX（95 runtime + 2 declaration）、3 CSS；导出符号计数 278。 | 这轮未重新枚举磁盘树；此前报告记录命令 exit 0、清单与基线对账。 | 逐运行时模块及符号仍未逐条补齐业务域、入口、状态、API/无 API、行为、测试和浏览器证据。 |
| 2. 每个 UI 原语静态调用者 | PARTIAL | §3 按 18 个 ember/ui 文件分别列 caller；Tooltip 标静态零 caller/动态待核。 | 本轮未运行页面以核实动态消费。 | caller 清单有，但多数行没有逐 caller 的具体使用用途及对应状态/测试证据。 |
| 3. 页面/业务组件/service/store/hook 功能映射 | PARTIAL | §2、§9 列出若干符号和业务链；§4.3 更正 route caller 证据等级。 | 当前报告记录的浏览器只读路径仅覆盖若干页面，见 §11；本轮没有新增浏览器操作。 | 仍非每一页面、业务组件和模块逐符号的完整矩阵；组件状态与所有错误/空/加载/禁用/成功行为未全覆盖。 |
| 4. 每条对外 route 契约、service 与 Web caller | PARTIAL | §4 的 65 条 method/path/handler 行与 AST 65/65 对账；请求、响应、错误和 service 摘要已列。§4.3 新增 13 条逐项复核；52/65 原 caller 统计不再代表逐链完成。 | 本轮静态核查补明旧正则漏报和过度评级；没有对 route 做运行请求。 | 13-route 表仍有包装未消费、无 caller 和 runtime 待核；65 条完整 service→Web 入口→行为链未完成。task_status/batch 当前 importer 未找到；image_proxy Web 外链 Markdown runtime 未验证。 |
| 5. Specs 001–020 矩阵 | PARTIAL | §5 有 20 个独立 spec 行及测试路径/链接状态。 | 报告将单项 spec 套件标 NOT RUN；此前全套测试记录不能推出每个 spec 通过。本轮未运行测试。 | 各行的实现符号→契约→具体测试关联仍有 UNVERIFIED_LINK，且没有逐 spec 本轮结果。 |
| 6. 每个用户可达页面浏览器主路径 | PARTIAL | §7、§9 列出当前入口和部分页面链。 | 历史本轮证据：报告记载 worker 曾读取 / 空工作区、/onboarding backend ready、/settings/general。另有 dispatcher 评论 c_mw6b3gen1nvuje / c_mw6b5js11okyoi 记录 Settings 九个子路由和 onboarding 的只读复验；不是当前 resumed run 重做。详见 §11。 | 单/批提交、批量选择、失败重试、真实 reader、分组 mutation、设置保存/清理等未完成；仅“页面打开”也不能证明该页面的主动作已验证。 |
| 7. 运行可用专项测试与静态门禁 | PARTIAL | §6 原测试表保存精确命令与汇总。 | **此前报告记录，不是本轮重跑**：前端 pnpm exec vitest run exit 0（17 files/100 tests）、pnpm exec tsc -b exit 0、pnpm lint exit 0、pnpm build exit 0（3158 modules，bundle warnings）；backend .venv/bin/python -m pytest -q -p no:cacheprovider exit 0（953 passed、15 subtests、1 warning）。**本轮**实际命令只有 git diff --check（exit 0，提交前）；另一次 shell 检查因把 cmd.exe if exist 语法用于 Bash 而 exit 2，未改变文件。 | 本轮未重跑前后端测试、tsc、lint 或 build；专项测试本轮 NOT RUN。 |
| 8. 每个缺陷复现步骤及 spec 依据 | PARTIAL | §8 暂无已复现 spec 违规；明确列实现验证不足、未引用候选、范围外与待确认。 | 本轮没有复现产品缺陷。 | 没有可复现违规就不伪造修复票；候选项缺少复现/spec 冲突证据，不能定为缺陷。后续核实发现违规时需另建票。 |
| 9. worktree clean、只读审计、修复另卡 | PARTIAL | 本轮改动限于此报告；未编辑产品源。 | git diff --check exit 0；当前待提交报告差异尚未 clean。此前提交有 clean 记录，但不能替代本次最终提交后检查。 | 提交后再核验 clean 与分支提交；本轮无业务修复，也未创建修复卡。 |
| 10. 报告、评论和计数一致 | PARTIAL | 报告包含 100 个 src 路径、18 个 UI 原语、65 条 route 和 20 个 spec 行；本表逐条映射 README §6。 | 本轮 Flow 检查点已记录评论 c_mw6czc947xxnnc；本轮提交与 clean 检查待完成。 | 全量逐符号、逐 route 链和逐 spec 关联尚不足以宣称计数/映射验收；PR pr_006 不合并。 |

## 11. 浏览器用户路径清单（操作与结果状态）

下表区别页面加载证据与主路径动作证据。页面访问记录来自本报告已有记录或明确注明的 Flow dispatcher 评论；不是本次恢复运行的新操作。没有记录的页面操作保持 NOT RUN。

| 用户路径 | URL / 操作 | 已记录结果 | 状态与未执行原因 |
|---|---|---|---|
| 工作台/单集 intake | http://127.0.0.1:3015/；打开首页并查看单集入口、空任务态 | 旧报告记载 UI/空态可见 | 页面只读访问；未输入/提交 URL，生成路径 NOT RUN。 |
| 批量 intake | / → 批量入口 | 可见入口；POST /api/v1/intake/resolve caller 静态链在 §4.3 | 未实际解析、选择视频或提交；NOT RUN。 |
| 任务选择/失败重试 | / → 任务列表选择失败项并重试 | 静态链在 §9；隔离 DB 先前记为无任务，且本轮未 seed | 无失败任务样本，选择/重试动作 NOT RUN。 |
| 笔记/转录阅读 | / → 选择已完成任务 → reader tabs | reader 静态链在 §9；无真实任务样本证据 | 带真实 Markdown/transcript 的主路径 NOT RUN。 |
| 分组动作 | / → GroupPanel 创建/重命名/删除/分配/归档 | 旧报告只读观察分组空态；静态链 §9 | 所有 mutation/下载 NOT RUN；隔离 DB 未 seed/写入。 |
| Settings: general | /settings/general | 旧报告记录字段可见、未改值时 Save disabled | 加载可见；保存成功/失败未执行。 |
| Settings: model | /settings/model | dispatcher 评论 c_mw6b3gen1nvuje 记录只读复验 | 保存 provider/model、连接测试等 NOT RUN。 |
| Settings: transcriber | /settings/transcriber | 同上：只读页面复验 | 保存端点/模型和下载/测试 NOT RUN。 |
| Settings: OCR | /settings/ocr | 同上：只读页面复验 | 保存与连接测试 NOT RUN。 |
| Settings: prompt | /settings/prompt | 同上：只读页面复验 | 保存/恢复动作 NOT RUN。 |
| Settings: media | /settings/media | 同上：只读页面复验 | 保存保留策略与运行 cleanup（删除资源）NOT RUN。 |
| Settings: download | /settings/download | 同上：只读页面复验 | cookie 写入 NOT RUN。 |
| Settings: monitor | /settings/monitor | 同上：只读页面复验 | 当前 resumed run 未重复加载；历史记录不作本轮通过。 |
| Settings: about | /settings/about | 同上：只读页面复验 | 当前 resumed run 未重复加载；历史记录不作本轮通过。 |
| Onboarding | /onboarding | 旧报告记录 backend ready；dispatcher 评论 c_mw6b5js11okyoi 记载页面及连接状态可见 | 检测/继续配置/写入动作 NOT RUN。 |
| NotFound | 任意未知路径 → fallback | 静态路由 EmberApp.tsx 与 NotFoundPage | 本轮无真实浏览器访问，NOT RUN。 |

隔离写入授权只限定 T-046 worktree 的临时 SQLite/隔离服务。服务启动已确认 DATABASE_URL 指向 `C:/Users/Administrator/Desktop/prjs/.flow-worktrees/BiliNote/T-046/backend/bili_note.db`，`BACKEND_HOST=127.0.0.1`、`BACKEND_PORT=8484`；数据库为 worktree 独立文件。启动 lifespan 的内置 media cleanup loop 自动新增 `media_cleanup_runs.id=3`（类型 screenshot,video,audio；expired_only=1；requested/deleted/missing/failed/bytes_freed 全 0），基线该表原有 2 行；`video_tasks/note_groups/providers/models/media_resources` 前后均为 0。该自动产生的审计行予以保留，不删改数据库记录。前端在 3016 启动，但 Vite 客户端未读取环境变量注入，浏览器 `/sys_check` 请求落到 Vite 本地并 404，最终显示后端启动失败；虽由代理直请求 `http://127.0.0.1:3016/api/sys_check` 和 `/api/note_group` 均返回隔离后端 200，页面应用未进入工作区。已停止 8484 后端及 3016 Vite。没有执行 seed、业务写入或任何浏览器 mutation。故本轮未完成授权的分组 CRUD、设置保存、batch、retry、reader 路径；这些全部保持 NOT RUN。
