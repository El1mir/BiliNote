# 016 审计报告：Web 前端 ↔ 后端逐符号映射（增量）

- 执行：工人2 ag_020 · T-046 · flow/T-046 · HEAD `c011bbdf`（= master），开审时 git status 0 行
- CodeGraph：并行代理报告 489 files / 7,174 nodes / 16,041 edges（引用，未复核）
- 计划：主仓库未跟踪的 wayfinder/016-frontend-backend-mapping/README.md（本分支不提交它）
- 图例：VERIFIED 本轮实测 · PARTIAL · PENDING · NOT RUN

## 0. 进度
| 节 | 状态 |
|---|---|
| 1 计数 / 2 文件导出 / 3 UI 原语调用者 / 4 route 表 | VERIFIED（静态） |
| 4 双向映射 | route↔service↔Web service 函数 VERIFIED；组件行为级映射 PENDING |
| 5 spec 矩阵 | PARTIAL |
| 6 门禁 | VERIFIED |
| 7 浏览器路径 | PENDING（T-046 自起服务：前端 http://127.0.0.1:3015，后端 :8483） |
| 8 发现分级 | PARTIAL |

## 1. 计数（VERIFIED）
| 项 | 数 | 口径 |
|---|---|---|
| src 跟踪文件 | 100（97 ts/tsx = 41+56，含 2 个 .d.ts；3 css） | git ls-files |
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

## 4. 后端 route（VERIFIED，AST）
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
| GET | /api/image_proxy | note.py:2713 image_proxy | request:Request, url:str | 文件/二进制 | HTTPException(status_code=500, detail=str(e)); HTTPException(status_code=resp.status_code, detail="图片获取失败") | 内联/模块级实例 | **无 Web 调用者** |
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

### 4.1 无 Web 调用者（静态结论，不判死代码）
证据：把前端 63 处 request/fetch/EventSource 调用逐条和 route 比对，再对每条 path 做 grep。
- `GET /api/media/cache/limit`（media.py:94）
- `POST /api/media/cache/enforce`（media.py:106）
- `GET /api/image_proxy`（note.py:2713）
- media/cache/*：spec 007:158 和 009:136 把它们当后端验收接口 → 运维 API，属范围外。
- image_proxy：前端只在 store/taskStore/index.ts:78 的注释里提到。URL 是否由后端写进内容，待核实。

### 4.2 Web 模块无入口
- services/proxy.ts（/proxy_config）、services/upload.ts（/upload）、ember/ui/Tooltip.tsx：没有静态调用者 → 无入口候选，删还是接线需产品决定。

## 5. spec 矩阵（PARTIAL）
| spec | 状态 | 前端测试（数） | 后端测试（数） | 本轮 | 符号链接 |
|---|---|---|---|---|---|
| 001-bilibili-batch-import | 未标注 | BillNote_frontend/tests/001-bilibili-batch-import (11) | backend/tests/001-bilibili-batch-import (60) | 本轮执行，通过（整套 vitest/pytest exit 0） | UNVERIFIED_LINK（逐符号链接 pending） |
| 002-video-understanding-sampling | 未标注 | 无 | backend/tests/002-video-understanding-sampling (47) | 本轮执行，通过（整套 vitest/pytest exit 0） | UNVERIFIED_LINK（逐符号链接 pending） |
| 003-openai-compatible-asr | 未标注 | 无 | backend/tests/003-openai-compatible-asr (46) | 本轮执行，通过（整套 vitest/pytest exit 0） | UNVERIFIED_LINK（逐符号链接 pending） |
| 004-note-math-rendering | 未标注 | BillNote_frontend/tests/004-note-math-rendering (7) | 无同号目录 | 本轮执行，通过（整套 vitest/pytest exit 0） | UNVERIFIED_LINK（逐符号链接 pending） |
| 005-modern-dark-ui-and-task-progress | 未标注 | BillNote_frontend/tests/005-modern-dark-ui (46) | backend/tests/005-modern-dark-ui-and-task-progress (48) | 本轮执行，通过（整套 vitest/pytest exit 0） | UNVERIFIED_LINK（逐符号链接 pending） |
| 006-note-pipeline-performance | 未标注 | 无 | backend/tests/006-note-pipeline-performance (27) | 本轮执行，通过（整套 vitest/pytest exit 0） | UNVERIFIED_LINK（逐符号链接 pending） |
| 007-note-archive-and-media-cache | 未标注 | 无 | backend/tests/007-note-archive-and-media-cache (69) | 本轮执行，通过（整套 vitest/pytest exit 0） | UNVERIFIED_LINK（逐符号链接 pending） |
| 008-ocr-assist-and-legacy-cleanup | 未标注 | 无 | backend/tests/008-ocr-assist-and-legacy-cleanup (145) | 本轮执行，通过（整套 vitest/pytest exit 0） | UNVERIFIED_LINK（逐符号链接 pending） |
| 009-batch-grouping-and-long-run-robustness | 未标注 | 无 | backend/tests/009-batch-grouping-and-long-run-robustness (97) | 本轮执行，通过（整套 vitest/pytest exit 0） | UNVERIFIED_LINK（逐符号链接 pending） |
| 010-group-and-note-deletion | 未标注 | BillNote_frontend/tests/010-group-and-note-deletion (3) | backend/tests/010-group-and-note-deletion (24) | 本轮执行，通过（整套 vitest/pytest exit 0） | UNVERIFIED_LINK（逐符号链接 pending） |
| 011-failed-task-retry | 未标注 | 无 | backend/tests/011-failed-task-retry (17) | 本轮执行，通过（整套 vitest/pytest exit 0） | UNVERIFIED_LINK（逐符号链接 pending） |
| 012-rate-limit-backoff | implemented | 无 | backend/tests/012-rate-limit-backoff (29) | 本轮执行，通过（整套 vitest/pytest exit 0） | UNVERIFIED_LINK（逐符号链接 pending） |
| 013-local-transcriber-hardware-acceleration | implemented | 无 | backend/tests/013-global-active-model (4) | 本轮执行，通过（整套 vitest/pytest exit 0） | UNVERIFIED_LINK（逐符号链接 pending） |
| 014-backend-cache-optimization | implemented | 无 | backend/tests/014-backend-cache-optimization (97) | 本轮执行，通过（整套 vitest/pytest exit 0） | UNVERIFIED_LINK（逐符号链接 pending） |
| 015-note-preset-scene-and-detail | implemented | BillNote_frontend/tests/015-note-preset-scene-and-detail (6) | backend/tests/015-note-preset-scene-and-detail (54) | 本轮执行，通过（整套 vitest/pytest exit 0） | UNVERIFIED_LINK（逐符号链接 pending） |
| 016-web-startup-optimization | 未标注 | 无 | 无同号目录 | NOT RUN：无同号测试 | UNVERIFIED_LINK（逐符号链接 pending） |
| 017-web-rebuild-and-architecture | implemented | 无 | backend/tests/017-web-rebuild-and-architecture (76) | 本轮执行，通过（整套 vitest/pytest exit 0） | UNVERIFIED_LINK（逐符号链接 pending） |
| 018-single-batch-and-merged-note | implemented | BillNote_frontend/tests/018-single-batch-and-merged-note (4) | backend/tests/018-single-batch-and-merged-note (25) | 本轮执行，通过（整套 vitest/pytest exit 0） | UNVERIFIED_LINK（逐符号链接 pending） |
| 019-global-model-in-provider-section | implemented | BillNote_frontend/tests/019-global-model-in-provider-section (4) | backend/tests/019-global-model-in-provider-section (6) | 本轮执行，通过（整套 vitest/pytest exit 0） | UNVERIFIED_LINK（逐符号链接 pending） |
| 020-note-rendering-and-batch-options | implemented | BillNote_frontend/tests/020-note-rendering-and-batch-options (10) | backend/tests/020-note-rendering-and-batch-options (4) | 本轮执行，通过（整套 vitest/pytest exit 0） | UNVERIFIED_LINK（逐符号链接 pending） |

测试数来源：后端用 pytest --collect-only，前端用 vitest json。另有前端 onboardingTranscriber（9）和后端顶层 test_*.py（78）未归属任何 spec。backend/tests/013-global-active-model 与 specs/013-local-transcriber-hardware-acceleration 命名不一致，待核实。

## 6. 门禁（VERIFIED，本轮执行）
| 命令 | exit | 汇总 |
|---|---|---|
| vitest run（BillNote_frontend） | 0 | 17 个文件 / 100 个测试通过 |
| node scripts/i18n-contract.cjs | 0 | 507 个 key 对齐 |
| tsc -b | 0 | — |
| eslint . | 0 | — |
| vite build --outDir（worktree 外） | 0 | 有两个 chunk >500kB 警告 |
| backend: python -m pytest -q -p no:cacheprovider | 0 | 953 passed，15 subtests，1 个 warning |

## 7. 浏览器主路径（PENDING）

## 8. 发现分级（PARTIAL）
- 现有 spec 违规：暂无已复现
- 实现存在但验证不足：组件交互状态大多没有组件测试
- 无入口候选：proxy.ts、upload.ts、Tooltip.tsx
- 范围外：media/cache/limit、media/cache/enforce
- 待核实：image_proxy 调用方；013 测试目录命名
