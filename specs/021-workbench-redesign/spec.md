# 021 · 工作台重设计（Workbench redesign）

状态：approved · 创建：2026-11-10 · 来源：父任务 T-066

## 背景

旧的 Ember 视觉（terracotta + 暖中性 + Playfair）已不再作为约束。产品要在 Web 主应用与浏览器扩展上呈现一个耐看、可长时间操作的企业工作台：深石墨、冷白、青绿；浅色默认、深色完整；动效专业流畅。

## 目标

1. 全站唯一视觉来源：双主题语义 token、三套自托管字体、集中动效 token。
2. 18 个 UI 原语按新 token 重绘，页面层只消费，不写颜色。
3. AppShell 三档布局与 Topbar 主题三态。
4. 保留产品全部功能与后端契约不变。

## 非目标

- 不改后端 API、生成流程、数据格式。
- 不在本 spec 内新增业务功能。

## 已定决策

| 决策 | 理由 |
|---|---|
| 语义名用 `accent` / `ink-muted`，`primary` / `ink-mute` 保留为过渡别名 | 页面包并行改写会冲突；别名让 W0 可以先落地 |
| 字体自托管（@fontsource，latin 子集） | 首屏不依赖 CDN；CJK 走系统栈，避免几 MB 字库 |
| 主题三态（light / dark / system） | 用户预期的「跟随系统」；显式选择优先 |
| 主题在 React 挂载前写入 `<html>` | 否则刷新必然闪一次浅色 |
| 动效 token 集中在 motion.css | 页面不得自造时长 |

## 待确认问题

- 无。

## 拆分

| 卡 | 工作包 |
|---|---|
| T-068 | W0 地基：tokens / 字体 / 动效 / 18 原语 / AppShell / 主题（本 spec 的实现清单） |
| T-069–T-073 | W1–W5 页面与扩展 |
| T-074 | W6 Tauri 移除收尾 |
| T-075 | W7 集成验收 |

## 实现清单

- [x] `src/ember/tokens.css`：12 语义 token × 双主题 + 字号/圆角/层级 + 别名
- [x] `src/ember/motion.css`：press 120 / hover 160 / popover 180 / menu 200 / panel 260 / page 300
- [x] `src/fonts.ts` + `index.html`：@fontsource 自托管，移除 Google Fonts
- [x] `src/ember/theme/theme.ts`：三态解析 + 持久化 + 挂载前上色
- [x] `src/ember/shell/Topbar.tsx` / `AppShell.tsx`：三档布局、图标栏可访问名
- [x] `ui/**` 18 原语改用语义 token，hex 仅剩 BilibiliMark
- [x] `docs/ui-audit/021/`：对比度脚本与输出
- [x] `tests/021-workbench-redesign/`：token 与主题回归测试

## 验收证据

- `node docs/ui-audit/021/contrast-audit.mjs` → all pairs pass（双主题 26 对）
- `pnpm exec vitest run tests/021-workbench-redesign` → 2 files / 7 tests
- 全量门禁：vitest 25 files、tsc、lint、i18n contract、build 全 exit 0