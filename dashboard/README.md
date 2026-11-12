# FraudGuard dashboard

Analyst console for FraudGuard: live alert queue, explainable risk scores,
one-key review, and the immutable audit trail.

Next.js 16 (App Router, Cache Components) · React 19 · Tailwind CSS 4 · Motion · custom SVG charts,
built on Material Design 3 Expressive.

## Run locally

The backend must be running on `:8000` with demo data (see the root README):

```bash
npm install
npm run dev
```

Open http://localhost:3000 and sign in as `maya.chen` (analyst) or `ops.admin`
(admin). The password is `DEMO_PASSWORD` from the backend's `.env`.

## How it talks to the backend

- **REST**: the browser calls `/api/*` on the dashboard's own origin;
  `next.config.ts` rewrites those to `BACKEND_URL` (default
  `http://127.0.0.1:8000`) and adds Django's trailing slash. There's no CORS setup.
- **WebSocket**: connects straight to Django Channels at `/ws/alerts/?token=…`.
  In dev it targets `:8000` on the same host; set `NEXT_PUBLIC_WS_URL` in
  deployment.

| Variable | Used for | Example (Vercel) |
|---|---|---|
| `BACKEND_URL` | REST rewrite target (read at build time) | `https://fraudguard.onrender.com` |
| `NEXT_PUBLIC_WS_URL` | WebSocket origin | `wss://fraudguard.onrender.com` |

## Keyboard

| Key | Action |
|---|---|
| `J` / `K` or `↓` / `↑` | Next / previous alert |
| `A` | Approve as legitimate |
| `R` | Confirm fraud |
| `N` | Focus the review note |
| `/` | Search the queue |
| `Ctrl K` / `⌘K` | Command menu |

## Design system (Material 3 Expressive)

- **Dynamic color**: every color role (`--md-sys-color-*`) is generated from a seed by
  Google's `@material/material-color-utilities` (Expressive scheme, 2025 spec) in
  [src/lib/m3-theme.ts](src/lib/m3-theme.ts). Success, warning and serious are harmonized
  custom colors (`--md-ext-color-*`). The default scheme ships as static CSS
  ([src/app/m3-tokens.css](src/app/m3-tokens.css), regenerate with `npm run tokens`);
  picking another seed in the account menu regenerates it at runtime and a pre-paint
  script restores it on load.
- **Type**: Google Sans Flex (with its `ROND` axis for display/headline emphasis) and
  Google Sans Code; the full M3 scale is exposed as Tailwind `text-display-large` …
  `text-label-small`.
- **Shape, elevation, state, motion**: M3 corner scale (`rounded-xs` 4px → `rounded-2xl` 48px),
  elevation levels 1–5, state-layer opacities, and the Expressive spring motion scheme as
  CSS `linear()` easings ([globals.css](src/app/globals.css)) and Motion springs
  ([src/lib/motion.ts](src/lib/motion.ts)) from the same damping/stiffness values.
- **Layout**: M3 window size classes as breakpoints (`medium` 600, `expanded` 840,
  `large` 1200, `xlarge` 1600) with a 4/8/12-column grid. Navigation bar on compact,
  navigation rail on medium/expanded, expanded rail on large+.
- **Components** ([src/components/ui/m3.tsx](src/components/ui/m3.tsx)): ripple, buttons with
  press shape-morph, icon buttons, FAB, cards, filter chips, connected button group,
  outlined text field, switch, badge, wavy progress. Container transforms: FAB → dialog,
  alert card → detail (compact/medium).
- **Search**: a Ctrl K / ⌘K command menu ([src/components/command-menu.tsx](src/components/command-menu.tsx))
  styled as an M3 search view: jump between pages, run actions, find alerts.
- **Contrast**: text is on-role colors from the tone system; checked in the browser with
  a WCAG 2.1 contrast pass on every page in light and dark. Chart series colors are
  validated separately for ≥3:1 against the card surface.

## Layout

- `src/app/(console)/*/page.tsx`: thin server pages (`instant = false`; the
  console is auth-gated on the client)
- `src/components/views/`: page bodies
- `src/components/alert-stream.tsx`: alert store and WebSocket with reconnect backoff
- `src/components/alerts/`: detail panel, score gauge, contribution bar, factor explanations, badges
- `src/components/simulate-dialog.tsx`: demo traffic dialog (container transform from the FAB)
- `src/components/charts/`: area chart, histogram, bar list, sparkline
- `src/lib/risk.ts`: severity tiers and plain-language rule explanations
