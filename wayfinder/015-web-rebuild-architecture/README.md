# 015-web-rebuild-architecture

## Destination

Produce an approved, implementation-ready specification and ordered tickets for a web-only redesign of BiliNote that preserves the existing product workflow, supports Chinese and English throughout, targets desktop/tablet/mobile, and coordinates frontend/backend changes around measurably faster loading and smoother task progress.

## Notes

- Domain: BiliNote video-to-notes workflow.
- Design source: ember-studio-DESIGN.md (Ember Studio, warm craft-oriented visual system).
- Keep browser extension behavior out of this web-app rebuild unless a shared backend contract requires compatibility; do not build Tauri artifacts.
- Keep only Bilibili as an implemented note-generation source. Preserve platform-neutral single-URL and batch-URL recognition interfaces so future source adapters can be added without changing page contracts.
- Frontend and backend contracts may evolve together. Plan explicit migration/versioning and regression coverage before implementation.
- Performance is experience-budget driven: measure current and target baselines before fixing numeric budgets; include cold/warm load, route transition, interaction responsiveness, request count, and task progress freshness.
- Architecture vocabulary: module, interface, depth, seam, adapter, leverage, locality, deletion test.

## Decisions so far

- [Web-only destination and performance-budget acceptance](tickets/001-destination-and-performance.md): This map reaches an approved build specification and sequenced delivery tickets; performance must have measured budgets rather than unverified speed claims.
- [Coordinated API redesign and channel scope](tickets/002-api-and-source-scope.md): Frontend/backend contracts can be redesigned together; Bilibili is the sole implemented generation source while URL recognition stays extensible.
- [Task read model and update transport](tickets/002-task-read-model-and-update-transport.md): A versioned task/group read model owns normalized status, actions, revisions, SSE-first updates, and cursor-based polling fallback.
- [Source Intake module](tickets/007-source-intake-module.md): A platform-neutral single/batch intake contract owns normalization, Bilibili short links, parts, collections, deduplication, limits, and stable localized errors.
- [Pipeline deduplication and cache seams](tickets/004-pipeline-deduplication-and-cache-seams.md): One cache seam owns audio/transcript artifacts, where a corrupt cache is a miss rather than a task failure; cross-task transcript reuse, OCR stage parallelism, single-read stage entrances and the merged audio write are all implemented.
- [Frontend Workspace Data Module](tickets/008-frontend-workspace-data-module.md): One frontend facade owns queries, commands, transport adaptation, resource loading, i18n boundaries, and Ember Studio shell seams.
- [Chinese and English i18n contract](tickets/005-i18n-contract-and-migration.md): One flat prefixed dictionary with zh-CN defining the key set, locale persisted under bilinote-locale, `translate()` for non-React modules, backend errors localized by structured `data.reason` rather than message text, and a contract gate (`pnpm test:i18n`) that catches placeholder drift, untranslated values and empty strings.
- [Migration and regression gates](tickets/006-migration-and-regression-gates.md): Versioned `/api/v1/...` contracts with schemaVersion/contractVersion, read-time normalization instead of disk migration scripts, one-line entry cutover with no feature flag, four automatic gates plus a human screenshot gate, and an evidence checklist covering three viewports in both locales.

## Not yet specified

- The exact responsive route/panel composition and implementation order within the boundaries recorded by tickets/001-capability-inventory-and-information-architecture.md and tickets/008-frontend-workspace-data-module.md.
- The implementation details of the task-state adapter and endpoint migration; the read model and transport decision is recorded in tickets/002-task-read-model-and-update-transport.md.
- Numeric initial-load and interaction budgets, bundle-splitting strategy, caching policy, and device/network test matrix; set after collecting a reproducible baseline.
- Whether existing persisted task/config data requires schema migration or only client-side normalization; inspect stores and DB contracts before deciding.
- Final migration window for legacy locale keys, backend error adapters, and extension-only surfaces; the web facade boundary is recorded in tickets/008-frontend-workspace-data-module.md.
- Which repeated backend work is safe to cache/coalesce across tasks (metadata, subtitles, transcript, frames/OCR) without changing note quality or privacy expectations.

## Out of scope

- Tauri build and desktop packaging.
- Implementing YouTube, Douyin, or Kuaishou generation adapters in this effort.
- Rebuilding the browser extension UI; keep its existing shared backend usage working unless a separately scoped extension change is approved.
- Changing note-generation semantics or prompt quality solely for visual redesign; behavior changes require explicit evidence and regression tests.
