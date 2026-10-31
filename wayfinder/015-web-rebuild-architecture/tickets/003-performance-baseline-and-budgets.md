# Performance baseline and experience budgets

- Type: task
- Status: in-progress

## Baseline snapshot (2026-10-16, Asia/Shanghai)

- Environment: Windows workspace `C:/Users/Administrator/Desktop/prjs/BiliNote/BillNote_frontend`, pnpm/Vite production build.
- Command: `pnpm build`.
- Result: exit code `0`; build duration `68s` (coarse shell timer; Vite reported `1m 8s`).
- Output: `97` files, `11,772,218` bytes in `dist/`.
- Largest gzip bundles: `index` `579.95 kB`, `Model` `661.08 kB`; both exceed the current 500 kB warning threshold.
- Browser Web Vitals and route/request/network baselines remain pending because the frontend dev server/browser harness is unavailable in this environment.

## Optimization snapshot (2026-10-16, Asia/Shanghai)

- Added Rollup vendor chunks in `C:/Users/Administrator/Desktop/prjs/BiliNote/BillNote_frontend/vite.config.ts`: `ui`, `math`, and `animation`; existing `markdown`, `markmap`, and `vendor` chunks retained.
- Rebuild result: exit code `0`; `67s` coarse shell time; `95` files; `11,565,911` bytes.
- Largest gzip bundles after split: `Model` `637.10 kB`, `markdown` `281.15 kB`, `markmap` `238.54 kB`, `ui` `203.69 kB`; the former remains the main optimization target.
- Compared with baseline: output reduced by `206,307` bytes and file count reduced by `2`; the former `index` `579.95 kB` gzip is now split to `index` `288.78 kB` gzip plus vendor chunks.
- TypeScript LSP for `vite.config.ts`: confirmed clean.

## Next measurement

Run the same build command after code-splitting and capture desktop/tablet/mobile browser LCP, INP, CLS, request count, and task-progress freshness with a repeatable browser script.

- Depends on: none
- Blocks: frontend shell, backend aggregation, delivery gates

## Question

Collect a repeatable baseline for the current web app before setting budgets: cold/warm startup, route transition, JS/CSS and image weight, request count, LCP/INP/CLS, first interaction readiness, and task-progress freshness on desktop/tablet/mobile and fast/slow networks. Record commands, browser versions, environment, and variability so later claims are comparable.
