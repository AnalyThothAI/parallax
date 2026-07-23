# Frontend

> **Scope.** Owns the `web/` architecture, layer responsibilities, component conventions, and the UI verification gate. Backend layer boundaries live in `ARCHITECTURE.md`; public HTTP/WebSocket contracts live in `CONTRACTS.md`; install and run commands live in `SETUP.md`.

## Source Layer Map (`web/src/`)

| Directory                | Responsibility                                                                                                                                                                                                    |
| ------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `app/`                   | Application composition: providers, router wiring, top-level error boundary, and route fallback. It may compose feature route elements, but it must not own feature data queries or business rendering.           |
| `routes/`                | Route entries and URL-state orchestration. Route modules parse/serialize shareable state and choose the owning feature view.                                                                                      |
| `features/<name>/api/`   | Feature-owned endpoint adapters, query keys, and reusable server-state hooks. Feature public hooks/controllers may own narrow server reads when they are the feature boundary consumed by routes or UI.           |
| `features/<name>/model/` | Pure feature helpers, view models, and constants. Framework-free where practical.                                                                                                                                 |
| `features/<name>/state/` | Local client state that is not shareable URL state and not server cache state. Keep it narrow and feature-owned.                                                                                                  |
| `features/<name>/ui/`    | Feature screens and components. UI reads data from props or feature hooks exposed through the feature public index, not from another feature's deep files.                                                        |
| `shared/query/`          | Cross-feature React Query primitives, query-key helpers, and cache patching utilities.                                                                                                                            |
| `shared/routing/`        | Reusable route parsing, path building, and URL search-param helpers.                                                                                                                                              |
| `shared/socket/`         | WebSocket provider, route-aware subscription registry, and socket test helpers.                                                                                                                                   |
| `shared/ui/`             | Reusable presentational primitives and cross-feature token display components. No server fetching.                                                                                                                |
| `lib/api/`               | Typed HTTP client facade and auth-token plumbing. No feature query hooks.                                                                                                                                         |
| `lib/env/`               | Runtime environment parsing.                                                                                                                                                                                      |
| `lib/types/`             | Generated OpenAPI types and frontend-owned view contracts.                                                                                                                                                        |
| `styles/`                | Global Tailwind import, design tokens, and base element styles only. Feature/page selectors belong beside their owning component or feature as side-effect CSS, or as real CSS Modules with local class bindings. |

Do not add new code under old `api/`, `store/`, or `components/` roots. Public feature imports should come from `@features/<name>`; sanctioned route-shell entrypoints may use `@features/<name>/shell`. Deep imports across feature internals are blocked by lint and grep gates; the relative-import boundary gate derives feature roots from `web/src/features`.

## Test Map (`web/tests/`)

`web/src/` contains production frontend code only. Frontend Vitest, React Testing Library, MSW, fixtures, architecture gates, and Playwright specs live under `web/tests/`. Repository-root `tests/` remains the Python/FastAPI pytest tree.

| Directory           | Responsibility                                                                                         |
| ------------------- | ------------------------------------------------------------------------------------------------------ |
| `unit/`             | Pure model, state, mapper, and library tests that mirror production source paths.                      |
| `component/`        | Focused React component, hook, and feature API hook tests.                                             |
| `routes/`           | App and route integration tests that render `App` or route shells.                                     |
| `architecture/`     | Static source gates for import boundaries, CSS ownership, test placement, and dead compatibility code. |
| `fixtures/`         | Shared frontend test fixtures.                                                                         |
| `msw/`              | MSW server, handlers, and named API scenarios.                                                         |
| `render/`           | React Testing Library render wrappers and route render harnesses.                                      |
| `socket/`           | Socket snapshot and subscription test utilities.                                                       |
| `e2e/golden-paths/` | Playwright browser golden paths.                                                                       |

## Conventions

- **Design contract and page archetypes.** Parallax has one dark, restrained
  research-workbench language. `styles/tokens.css` is the only semantic color,
  type, radius, focus, and shell token contract; production code must not add a
  parallel theme or compatibility alias. Stable routes declare one of four
  information archetypes with `data-page-archetype`: `scan` for Radar, Stocks,
  and News lists; `case` for Search, Token Case, and News Item; `decision` for
  Macro; and `monitoring` for Watchlist. The archetype
  governs hierarchy and density, never data ownership or business inference.
- **Data ownership.** Feature-owned API hooks, page hooks, and controller hooks own server reads/writes. Route modules and presentational UI components consume those feature hooks and must not call `useQuery`, `useMutation`, `useInfiniteQuery`, `getApi`, `postApi`, or `queryClient.set*` directly. `frontendDataOwnership.test.ts` enforces this boundary for `web/src/routes` and `web/src/features/*/ui`.
- **URL state.** Shareable filters such as `window`, `scope`, handles, search query, selected target, and radar sort live in route-state helpers. Local stores are only for interaction state that should not survive hard reloads.
- **Socket lifecycle.** `shared/socket` owns authentication, notification/event streams, and ref-counted market-target subscriptions. Routes register only the market targets they currently need; leaving Token Radar releases radar market targets while preserving global notification subscription. Stream/poll workers emit live market messages only after durable current-row persistence; those messages patch visible market response keys but are not a second source of truth.
- **Search route.** `/search` reuses the cockpit topbar but owns its
  search-local rail, filters, resolver candidates, and selected result. Topbar
  submit navigates to `/search?q=<query>`. Token search results render the
  shared Token Case panel directly from `/api/search/inspect`; they do not
  fetch `/api/token-case` again. Token, topic, and ambiguous results render
  resolver, identity, source-post, current Radar, and market facts only.
- **Token Case route.** `features/token-case` owns persistent
  `/token/:targetType/:targetId` inspection. The route parses `window`, `scope`,
  and timeline sort from the URL, fetches `/api/token-case`, seeds
  `/api/target-posts` from the dossier's first page, and subscribes only the
  active target for live market updates. The dossier renders current
  factor/market metadata and raw posts without synthesizing prose or per-post
  conclusions.
- **Token Radar drilldown.** Token Radar is the scan surface. Primary row
  clicks route to
  `/search?q=<token-or-address>&window=<current>&scope=<current>` for resolver
  context, while explicit token links may route to the Token Case dossier when
  a canonical target id is already known. Radar rows render the transparent
  factor snapshot supplied by the API; frontend code never recomputes ranking
  or introduces an additional admission state.
- **Watchlist route.** `features/watchlist/api` owns the selected-handle
  overview, summary, and timeline server state. `/watchlist` consumes the
  Evidence-owned all-activity timeline and does not recreate the removed
  `signal` scope, fixed-zero signal metrics, Account Quality state, or
  Watchlist-specific projection. It does not consume `/api/recent` or
  WebSocket replay to reconstruct selected-handle counts, resolved targets,
  candidate mentions, or evidence clusters.
- **News route.** `/news` is a canonical news-signal tape with filters,
  pagination, source-backed signal fields, and links into
  `/news/items/:newsItemId`.
  On `/news` and `/news/items/:newsItemId`, topbar search is route-local:
  submit navigates to `/news?q=<query>` and the page calls `/api/news` with
  `q`; it must not call `/api/search/inspect` or reuse token resolver state.
  `/news/items/:newsItemId` is the item evidence page rendering story
  membership, token identity lanes, fact candidates, provider observations,
  source metadata, content classification, market scope, and dedupe facts
  directly from `/api/news/items/{news_item_id}`. The list route does not keep
  an inline selected inspector or infer direction, eligibility, or thesis from
  headlines, summaries, provider ratings, or keyword heuristics.
- **Macro routes.** Macro has exactly six flat navigation destinations:
  `/macro`, `/macro/cross-asset`, `/macro/rates-inflation`,
  `/macro/growth-labor`, `/macro/liquidity-funding`, and `/macro/credit`.
  Each route owns an explicit page component and reads its matching typed API:
  `/api/macro/overview`, `/api/macro/cross-asset`,
  `/api/macro/rates-inflation`, `/api/macro/growth-labor`,
  `/api/macro/liquidity-funding`, or `/api/macro/credit`. Charts request
  persisted points from `/api/macro/series`.

  `/macro` is the fixed cross-asset risk map for the latest completed US
  session and a 1–4 week horizon. It renders the persisted Overview document
  directly: one shock state, exactly eight ordered lanes (US equities,
  long-duration Treasuries, credit, USD, gold, oil, crypto, and market
  volatility), up to three five-completed-session changes, the nearest
  trustworthy official catalyst, and one core invalidation. Direction, trend,
  categorical confidence, lane rationale, contradictions, invalidations, and
  local degradation are backend-owned deterministic results. The Overview must
  make exactly one page read and must not sort, score, infer, or fan out across
  the five domain documents.

  Normal snapshot metadata, evidence rows, rules, formulas, freshness, and
  named unavailable capabilities live in the keyboard-accessible `审计与证据`
  disclosure and are collapsed by default. Critical missing or stale evidence
  remains adjacent to the affected lane or conclusion. A normalized catalyst
  instant is displayed in browser-local time first and official date, time,
  and timezone second; unparsed official time is never converted into a
  fabricated instant.

  The five drilldowns keep explicit page components. They render current
  judgment first, then separate-unit 20/60-session small charts with source,
  unit, and as-of labels, followed by domain-specific evidence. The UI does not
  compute correlations, change windows, curve shape, shock state, Credit
  state, or conclusions. Macro never renders holdings, buy/sell instructions,
  position size, target price, allocation, probabilities, or LLM output.

  Macro uses one flat feature-owned navigation and small shared evidence
  primitives; there is no registry-driven page catalog or universal page
  renderer. At desktop widths, dense evidence may use tables and small
  multiples. At tablet/mobile widths it becomes labelled stacked rows without
  hiding units, dates, samples, provenance, or gap status. No page may require
  horizontal document scrolling or hover to reveal material evidence.
- **Page state.** Loading, empty, stale, and error surfaces should use `PageState.*` so skeletons, error alerts, and retry actions stay consistent.
- **CSS ownership.** `main.tsx` imports only Tailwind, tokens, and base styles. Feature and shared UI selectors are imported by the component or route that owns them. Shared primitives such as `IconButton`, `RadarControls`, `PageState`, `TokenProfileCard`, `HandleFilter`, `DecisionTag`, `CompactPanel`, and the research case-file components own their CSS under `shared/ui/`; feature CSS may lay out the containing toolbar or deck but must not redefine primitive internals. Cross-feature widgets such as notifications own their visual selectors in their feature folder; shell code may place a slot, not restyle the widget internals. Do not use `.module.css` files as global selector buckets; CSS Modules must bind local classes from TypeScript.
- **CSS architecture harness.** `web/tests/architecture/cssArchitectureHarness.test.ts` is the future-proof gate for CSS ownership. It rejects retired global buckets (`cockpit.css`, `macro.css`, `macroResponsive.css`, `shared.css`, `signalLab.css`), side-effect CSS imported from non-local owners, feature CSS that redefines shared UI classes, feature selectors outside their namespace, naked modifier classes such as `.active` or `.gap`, and side-effect class names reused across feature roots. When a new feature needs side-effect CSS, add an explicit namespace policy there rather than borrowing another feature's selectors.
- **Cascade layers.** Side-effect CSS participates in the app cascade contract declared in `styles/tokens.css`: `app.base`, `app.primitives`, `app.shell`, `app.features`, then `app.overrides`. `styles/base.css` uses `app.base`; shared primitives use `app.primitives`; cockpit shell files use `app.shell`; feature route CSS uses `app.features`. Unlayered side-effect CSS is allowed only for Tailwind's import file.
- **Responsive CSS contract.** Mobile behavior is a tested architecture surface, not a best-effort visual tweak. Shell CSS owns `.cockpit-shell`, `.cockpit-main`, `.center-column`, `.topbar`, and the shadcn sidebar composition (`SidebarProvider`, `AppSidebar`, `SidebarInset`, and `SidebarTrigger`) split by owner files (`cockpitShell.css`, `CockpitTopbar.css`, `AppSidebar.css`, and `cockpitShellContract.css`). Final shell breakpoint decisions, including the mobile topbar row height token, live in `features/cockpit/ui/cockpitShellContract.css`. Mobile and tablet route navigation uses the shadcn `Sheet` drawer opened from the topbar trigger. Live-only task visibility is feature-owned by `features/live/ui/live.css`, using `.live-task-nav` and `[data-mobile-task-panel]` only inside `.live-page`.
- **Route controls.** Shells do not render route-specific filter controls. Window/scope/venue/handle controls belong to the feature route that consumes them; `CockpitShell` and `SearchShell` own only navigation, frame layout, the main route scroll container, hotkeys, and notifications. Top-level radar routes must use owner-prefixed table selectors (`token-radar-*`, `stock-radar-*`) rather than generic historical selectors such as `.radar-row`, `.metric`, or `.phase`.
- **Shell navigation.** Desktop users navigate through the collapsible shadcn `AppSidebar`; tablet and mobile users open the same route tree through the topbar `SidebarTrigger` and shadcn drawer. The primary route tree contains exactly Radar, Stocks, News, Macro, and Watchlist in that order; Search remains reachable through the topbar submit flow. Healthy runtime state is silent. Configuration, service, or realtime anomalies appear as an accessible topbar status; operational diagnosis remains on the API/CLI surfaces and there is no browser Ops route. The live Radar/Tape/Lab task switcher is `LivePage`-owned, mobile-only, and must not render on Stocks, News, Macro, Watchlist, Search, or Token Case routes.
- **Scrolling.** `body` remains locked for the app shell. `.center-column` is the shell-managed route scroll container. On mobile, `LivePage` owns a two-row feature layout: active task content in `minmax(0, 1fr)` and `.live-task-nav` as a real bottom row, not a fixed overlay. Radar rows scroll inside `.token-radar-table` above that nav; the page must not keep the desktop `405px` bottom-deck row. Route-level nested scrollers are allowed only when they are intentionally bounded and covered by Playwright overflow/reachability assertions.
- **Breakpoint policy.** Desktop density starts at `1280px`. Tablet uses a single route column from `768px` through `1279px`. Mobile rules are `max-width: 767px` and must appear late enough in the cascade to win over base and desktop/tablet rules. Use container queries for local card/panel behavior when component width matters more than viewport width.
- **Side-effect CSS budget.** Architecture tests fail any side-effect CSS file above 500 lines. Component-specific styling should move toward CSS Modules or smaller owner files instead of growing route-wide side-effect CSS buckets.
- **Accessibility.** Icon-only controls use `IconButton` with an explicit `aria-label`; route status regions use polite live regions; form controls need visible or screen-reader labels. `jsx-a11y/recommended` is enforced as an error gate.
- **Score display.** Any displayed ranking score includes its component breakdown from the API. The UI does not recompute ranking facts locally.
- **Token images.** Token profile and radar logos render
  `profile.identity.logo_url` directly. The API contract guarantees that value
  is either `null` or a same-origin `/api/token-images/{image_id}` path; DB
  constraints reject remote provider URLs before they reach the frontend. Do
  not restore `tokenImageUrl`, `/api/token-image?url=...`, local logo filters,
  or any frontend proxy/helper that rewrites GMGN, Binance, OKX, or CEX image
  URLs.

## Build And Test

Common frontend gates:

- `cd web && npm run lint`
- `cd web && npm run test:architecture`
- `cd web && npm run typecheck`
- `cd web && npm test -- --run`
- `cd web && npm run build`
- `cd web && npm run test:e2e`

Playwright projects are part of the frontend contract:

- `desktop-1366` (`1366x720`)
- `desktop-1920` (`1920x1080`)
- `tablet-834` (`834x1194`)
- `mobile-390` (`390x844`)

Desktop-only specs must explicitly skip non-desktop projects. Mobile-only specs must explicitly skip non-mobile projects. New `page.setViewportSize` calls are allowed only in dedicated responsive specs or explicitly marked desktop-only specs.

Repository fast gate:

- `make check`

Integration, backend E2E, golden, and browser lanes are selected explicitly
from the changed seam per `TESTING.md`; there is no monolithic repository-wide
completion target.

Production bundles ship inside the same Docker image as the Python service and are served by the FastAPI static-file mount.

## UI Verification Gate

Per `DEVELOPMENT.md`, UI flows that tests cannot exercise must be checked manually before declaring completion. The minimum checklist for frontend architecture changes is:

1. Hard-reload `/`, `/search`, `/stocks`, `/news`,
   `/news/items/:newsItemId`, all six Macro routes, `/watchlist`, and
   `/token/:targetType/:targetId?window=1h&scope=all` with representative query
   params.
2. Submit the topbar search and confirm the URL becomes `/search?q=<submitted-query>`.
3. Verify visible loading/empty/error states are structured, labelled, and non-overlapping.
4. Confirm no failing `/api/*` requests in the browser session.
5. Confirm route-aware WebSocket subscription behavior: global notifications remain subscribed, while token-radar `market_targets` are released after leaving `/`.
6. Confirm token logos either load from `/api/token-images/{image_id}` or show
   fallback marks, with no browser requests to provider image URLs such as
   GMGN `external-res`.
7. At `390px`, confirm the topbar `SidebarTrigger` opens the shadcn drawer, drawer route links are reachable, `.topbar` and `.center-column` do not overlap, topbar controls stay contained, Live-only Radar/Tape/Lab task switching works without route reload on `/`, Radar rows can scroll to the final row above the task nav without overlap, and non-Live routes do not render `.live-task-nav`.
8. At tablet width around `834px`, confirm the desktop sidebar is hidden, the topbar trigger opens the shadcn drawer, drawer route navigation and topbar search still work, and the mobile Radar/Tape/Lab task nav is hidden.
9. At `1920px`, `1366px`, `834px`, and `390px`, verify the Overview keeps
   exactly eight ordered lanes plus bounded changes/catalyst/invalidation,
   every drilldown keeps its charts and judgment band, normal audit metadata
   stays collapsed, the audit drawer is keyboard reachable, local gaps remain
   adjacent, and no Macro page has whole-page overflow.
