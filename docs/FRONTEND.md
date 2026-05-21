# Frontend

> **Scope.** Owns the `web/` architecture, layer responsibilities, component conventions, and the UI verification gate. Backend layer boundaries live in `ARCHITECTURE.md`; public HTTP/WebSocket contracts live in `CONTRACTS.md`; install and run commands live in `SETUP.md`.

## Source Layer Map (`web/src/`)

| Directory | Responsibility |
|-----------|----------------|
| `app/` | Application composition: providers, router wiring, top-level error boundary, and route fallback. It may compose feature route elements, but it must not own feature data queries or business rendering. |
| `routes/` | Route entries and URL-state orchestration. Route modules parse/serialize shareable state and choose the owning feature view. |
| `features/<name>/api/` | Feature-owned React Query hooks and endpoint adapters. This is the only feature layer that calls `@lib/api/client` or owns query keys for its server data. |
| `features/<name>/model/` | Pure feature helpers, view models, and constants. Framework-free where practical. |
| `features/<name>/state/` | Local client state that is not shareable URL state and not server cache state. Keep it narrow and feature-owned. |
| `features/<name>/ui/` | Feature screens and components. UI reads data from props or feature hooks exposed through the feature public index, not from another feature's deep files. |
| `shared/query/` | Cross-feature React Query primitives, query-key helpers, and cache patching utilities. |
| `shared/routing/` | Reusable route parsing, path building, and URL search-param helpers. |
| `shared/socket/` | WebSocket provider, route-aware subscription registry, and socket test helpers. |
| `shared/ui/` | Reusable presentational primitives and cross-feature token display components. No server fetching. |
| `lib/api/` | Typed HTTP client facade and auth-token plumbing. No feature query hooks. |
| `lib/env/` | Runtime environment parsing. |
| `lib/types/` | Generated OpenAPI types and compatibility UI payload types. |
| `styles/` | Global Tailwind import, design tokens, and base element styles only. Feature/page selectors belong beside their owning component or feature as side-effect CSS, or as real CSS Modules with local class bindings. |

Do not add new code under old `api/`, `store/`, or `components/` roots. Public feature imports should come from `@features/<name>`; deep imports across feature internals are blocked by lint and grep gates.

## Test Map (`web/tests/`)

`web/src/` contains production frontend code only. Frontend Vitest, React Testing Library, MSW, fixtures, architecture gates, and Playwright specs live under `web/tests/`. Repository-root `tests/` remains the Python/FastAPI pytest tree.

| Directory | Responsibility |
|-----------|----------------|
| `unit/` | Pure model, state, mapper, and library tests that mirror production source paths. |
| `component/` | Focused React component, hook, and feature API hook tests. |
| `routes/` | App and route integration tests that render `App` or route shells. |
| `architecture/` | Static source gates for import boundaries, CSS ownership, test placement, and dead compatibility code. |
| `fixtures/` | Shared frontend test fixtures. |
| `msw/` | MSW server, handlers, and named API scenarios. |
| `render/` | React Testing Library render wrappers and route render harnesses. |
| `socket/` | Socket snapshot and subscription test utilities. |
| `e2e/golden-paths/` | Playwright browser golden paths. |

## Conventions

- **Data ownership.** Feature API hooks own server reads/writes. Feature UI and routes must not call `useQuery`, `useMutation`, `useInfiniteQuery`, `getApi`, `postApi`, or `queryClient.set*` directly.
- **URL state.** Shareable filters such as `window`, `scope`, handles, search query, selected target, and radar sort live in route-state helpers. Local stores are only for interaction state that should not survive hard reloads.
- **Socket lifecycle.** `shared/socket` owns authentication, notification/event streams, and ref-counted market-target subscriptions. Routes register only the market targets they currently need; leaving Token Radar releases radar market targets while preserving global notification subscription. Live market messages are cache-backed presentation updates from `LivePriceGateway`; they patch visible market response keys but are not persisted market facts.
- **Search route.** `/search` reuses the cockpit topbar but owns its search-local rail, filters, resolver candidates, and selected result. Topbar submit navigates to `/search?q=<query>`. Token search results render the shared Token Case panel directly from `/api/search/inspect`; they do not fetch `/api/token-case` again. Canonical token results read `discussion_digest`; topic and ambiguous results are the only search results that keep `agent_brief`.
- **Token Case route.** `features/token-case` owns persistent `/token/:targetType/:targetId` inspection. The route parses `window`, `scope`, and timeline sort from the URL, fetches `/api/token-case`, seeds `/api/target-posts` from the dossier's first page, and subscribes only the active target for live market updates. The dossier renders persisted narrative digest state and per-post `semantic` blocks; it does not infer stance from post quality or watched status.
- **Token Radar drilldown.** Token Radar is the scan surface. Primary row clicks route to `/search?q=<token-or-address>&window=<current>&scope=<current>` for resolver context, while explicit token links may route to the Token Case dossier when a canonical target id is already known. Radar rows may show `discussion_digest` and a secondary public Pulse overlay, but frontend code must not recompute narrative or rank from either payload.
- **Narrative states.** Token Radar and Token Case render persisted `discussion_digest.status` and `data_gaps` directly. Source insufficiency (`insufficient`), semantic backlog (`pending`), terminal provider unavailability (`semantic_unavailable`), and stale digest state (`stale`) have distinct labels; UI code must not collapse provider or backlog states into "insufficient".
- **Watchlist route.** `features/watchlist/api` owns the selected-handle
  overview, summary, and timeline server state. `/watchlist` uses
  `timeline_scope=signal|all` for its own timeline state and does not consume
  `/api/recent` or WebSocket replay to reconstruct selected-handle counts,
  resolved targets, candidate mentions, or narrative clusters.
- **News route.** `/news` renders deterministic News Intel facts plus the
  persisted `agent_brief` contract from `/api/news` and
  `/api/news/items/{news_item_id}`. Chinese summary, market read, direction,
  decision class, bull/bear theses, watch triggers, invalidations, evidence
  refs, and data gaps come from the backend brief or from an explicit
  missing/degraded brief state. Feature view-model code must not recreate
  trading narrative from headline, summary, or fact-lane keyword heuristics.
  Queue pagination is explicit; direction tabs request backend filters rather
  than client-side reclassification.
- **Macro route.** `/macro` renders deterministic Macro Intel state from
  `/api/macro`. Regime, component scores, indicators, triggers, and data
  gaps come from `macro_view_snapshots`; frontend code does not recompute macro
  scoring or infer missing values.
- **Remote state.** Loading, empty, stale, and error surfaces should use `RemoteState.*` so skeletons, error alerts, and retry actions stay consistent.
- **CSS ownership.** `main.tsx` imports only Tailwind, tokens, and base styles. Feature and shared UI selectors are imported by the component or route that owns them. Do not use `.module.css` files as global selector buckets; CSS Modules must bind local classes from TypeScript.
- **Accessibility.** Icon-only controls use `IconButton` with an explicit `aria-label`; route status regions use polite live regions; form controls need visible or screen-reader labels. `jsx-a11y/recommended` is enforced as an error gate.
- **Score display.** Any displayed ranking score includes its component breakdown from the API. The UI does not recompute ranking facts locally.
- **Token images.** Token profile and radar logos come from
  `profile.identity.logo_url` only when the value is a same-origin
  `/api/token-images/{image_id}` path. Remote provider URLs render the fallback
  mark. Do not restore `tokenImageUrl`, `/api/token-image?url=...`, or any
  frontend proxy/helper that rewrites GMGN, Binance, OKX, or CEX image URLs.

## Build And Test

Common frontend gates:

- `cd web && npm run lint`
- `cd web && npm run typecheck`
- `cd web && npm test -- --run`
- `cd web && npm run build`
- `cd web && npm run test:e2e`

Full repository completion gate:

- `make check-all`

Production bundles ship inside the same Docker image as the Python service and are served by the FastAPI static-file mount.

## UI Verification Gate

Per `WORKFLOW.md`, UI flows that tests cannot exercise must be checked manually before declaring completion. The minimum checklist for frontend architecture changes is:

1. Hard-reload `/`, `/search`, `/signal-lab`, `/stocks`, and `/token/:targetType/:targetId?window=1h&scope=all` with representative query params.
2. Submit the topbar search and confirm the URL becomes `/search?q=<submitted-query>`.
3. Verify visible loading/empty/error states are structured, labelled, and non-overlapping.
4. Confirm no failing `/api/*` requests in the browser session.
5. Confirm route-aware WebSocket subscription behavior: global notifications remain subscribed, while token-radar `market_targets` are released after leaving `/`.
6. Confirm token logos either load from `/api/token-images/{image_id}` or show
   fallback marks, with no browser requests to provider image URLs such as
   GMGN `external-res`.
