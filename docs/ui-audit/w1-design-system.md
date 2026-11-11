# W1 — Design foundation (tokens, theme, motion)

Status: implemented on `flow/T-066`. Supersedes the Ember Studio palette entirely.
Light is the default theme; dark is a full second value set, not an inversion filter.

## Palette (semantic, no component-level hex)

| token | light | dark | role |
|---|---|---|---|
| `canvas` | `#f4f6f7` | `#111719` | page background |
| `surface` | `#ffffff` | `#182124` | cards, panels, inputs |
| `raised` | `#fbfcfc` | `#202b2e` | popovers, nested surfaces |
| `raised-hover` | `#f0f4f5` | `#263336` | hovered popover rows |
| `ink` | `#172126` | `#edf4f3` | primary text |
| `ink-soft` | `#526168` | `#c0cfce` | secondary text |
| `ink-mute` | `#5f6d74` | `#91a3a5` | tertiary text, metadata |
| `line` | `#cbd5d8` | `#3b4a4d` | decorative dividers |
| `line-strong` | `#7e8e94` | `#6b7f82` | control borders (must clear 3:1) |
| `primary` | `#07756f` | `#43c7b6` | interaction, current item, progress |
| `primary-hover` | `#05635e` | `#5fd8c8` | hover/pressed primary |
| `primary-soft` | `#e8f3f1` | `#14312f` | selected row / active nav tint |
| `on-primary` | `#ffffff` | `#06201d` | text on primary fills |
| `success` | `#18794e` | `#62c891` | success |
| `warning` | `#926100` | `#f1c75b` | warning |
| `danger` | `#b42318` | `#ff8c83` | error, destructive |
| `on-danger` | `#ffffff` | `#2a0b08` | text on danger fills |
| `info` | `#1769aa` | `#8dc7f0` | informational |

Every status token also has a `-soft` background value. Status is never conveyed by colour
alone: badges and callouts pair the colour with an icon and a text label.

Contrast is recorded in `evidence/w1-contrast-ratios.txt` (body text ≥4.5:1, non-text UI
boundaries ≥3:1, both themes). `warning` was darkened from `#9a6700` to `#926100` because
4.49:1 on `canvas` missed AA by 0.01.

## Type

- UI: **Inter** (`--font-sans`, `--font-display`), fallbacks SF Pro Text → Segoe UI → system-ui.
- Reading: **Source Serif 4** + **Noto Serif SC** (`--font-serif`), used only inside
  `.ember-markdown` body copy.
- Identifiers, URLs, code, error text: **IBM Plex Mono** (`--font-mono`).
- Scale: hero 32/1.15 · section 28/1.214 · subhead 20/1.3 · card 15/1.4 · body 14/1.571 ·
  small 13/1.462 · caption 12/1.333 · overline 11 uppercase +0.08em.
- Body copy column is capped at 68ch in the reader.
- Fonts are loaded non-blocking from `index.html` (`media="print"` swap); every family has a
  system fallback so a blocked font request never delays first paint.

## Themes

`src/ember/theme/theme.ts` owns the switch:

- `applyTheme(theme)` toggles `.dark` on `<html>` and sets `color-scheme`.
- `initTheme()` runs in `src/main.tsx` **before** `createRoot`, so a reload never flashes the
  wrong palette.
- `setTheme` / `useTheme` (via `useSyncExternalStore`) persist to `localStorage['bilinote-theme']`
  and update every mounted toggle at once. Storage failures are swallowed — the session still
  switches, it just will not survive a reload.
- `src/ember/shell/ThemeToggle.tsx` exposes it as an icon button with an i18n aria-label.
  It is mounted in the desktop rail footer, the mobile header and the mobile drawer.

## Motion

One ladder in `src/ember/motion.css`: press 120ms · hover 160ms · popover 180ms · menu 200ms ·
panel 260ms (dialog and drawer both alias it) · page 300ms · progress 300ms.
Easing: `--ease` (ease-out) for most transitions, `--ease-drawer` for the drawer,
`--ease-inout`. `prefers-reduced-motion` keeps the 0.01ms override already defined there.

## Naming

The `ember` namespace stays for module paths and utility classes (`src/ember/`, `.ember-markdown`,
`ember-press`): it is referenced by probe scripts, tests and class names, and renaming it would
touch files unrelated to the visual work. Only the **colour families** were renamed
`*-ember*` → `*-primary*`; no `bg-ember` / `text-ember` / `border-ember` usage remains.

## Verification (already run)

```
cd BillNote_frontend
pnpm exec tsc -b            # exit 0
pnpm build                  # exit 0
```

Built CSS contains `.bg-canvas`, `.bg-primary`, `.border-line-strong` emitted as `var(--…)`,
and grep finds zero `Playfair`, `Fira Code` or `#c2410c` remnants.

Runtime evidence (mock backend on 127.0.0.1:8483, vite on 3015):

- `evidence/w1-light.png` — workspace, light, 1384x797
- `evidence/w1-dark.png` — same page after the toggle, `document.documentElement` carries `.dark`
- `evidence/w1-responsive-light.png` — 375 and 768 CSS px side by side
- `evidence/w1-contrast-ratios.txt` — both themes, every semantic colour

## Not done yet

Page-level composition (AppShell top bar with page title and backend status, workspace three
column layout, reader serif column, settings, onboarding) and the extension surfaces are
still on their pre-redesign composition; they now inherit the new tokens.