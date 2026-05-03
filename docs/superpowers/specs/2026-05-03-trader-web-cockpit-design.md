# Trader Web Cockpit Spec

Date: 2026-05-03

## First Principles

This project is not a generic social dashboard. Its useful product surface is a trader cockpit for converting the GMGN public Twitter stream into faster token/narrative awareness with auditable evidence.

The frontend should therefore optimize for:

- Time-to-signal: show what changed now before decorative summaries.
- Evidence-first decisions: every alert must be traceable to the source tweet/event.
- Dense scanning: one screen should carry live tape, token flow, watched-account alerts, narrative flow, search, and system state.
- No hidden taxonomy: handles, symbols, CAs, narratives, and enrichment jobs should map directly to current backend data models.
- Low operational burden: one FastAPI process can serve both `/ws` live push and static frontend assets; Docker builds the web bundle once.

## Data Chain

1. GMGN anonymous public Twitter WebSocket emits upstream frames.
2. `collector/direct_ws.py` receives raw frames.
3. `collector/normalizer.py` converts frames into stable `TwitterEvent` objects.
4. `collector/service.py` applies snapshot gating, watched-handle matching, and store-first publish.
5. `pipeline/ingest_service.py` persists evidence and derived artifacts transactionally.
6. `pipeline/entity_extractor.py` extracts CA, cashtag, hashtag, mention, URL/domain entities.
7. `pipeline/signal_builder.py` materializes watched-account alerts and token windows.
8. `pipeline/enrichment_worker.py` optionally runs LLM enrichment for watched-account events.
9. SQLite WAL stores raw frames, events, FTS, entities, token windows, alerts, enrichment jobs, model runs, token candidates, and narrative signals.
10. Public API exposes:
    - `/api/bootstrap` for same-origin frontend startup config.
    - `/ws` for replay and live event push.
    - `/api/*` for read models used by the cockpit.
    - `/healthz` and `/readyz` for operational probes.
11. React frontend loads `/api/bootstrap`, keeps the configured token in memory, then connects to protected `/api/*` snapshots and `/ws` live updates.

## Product Surface

The cockpit has no left sidebar. Navigation is a compact top control bar because the trader's primary task is scanning, not browsing sections.

Primary regions:

- Top bar: connection state, query input, replay/subscription filters, API freshness.
- Signal tape: live events and high-priority source tweets.
- Token flow board: ranked token/social windows with mention count, account count, and latest timestamp.
- Watched-account alerts: account-token intersections from configured handles.
- Narrative flow: LLM-derived narrative heat when enrichment is configured.
- Search/evidence panel: exact CA, cashtag, handle, or FTS retrieval.
- Ops strip: collector status, storage path, enrichment backlog.

## Frontend Stack

- React + TypeScript + Vite for a small SPA and fast local iteration.
- Tailwind CSS v4 with CSS variables for a compact trader visual system.
- TanStack Query for HTTP read-model refresh and cache state.
- TanStack Table/Virtual reserved for larger tables as the cockpit grows.
- Zustand for local UI/session preferences only.
- Reconnecting WebSocket for live push resilience.
- lucide-react for tool icons.

No Next.js, no SSR, no separate frontend server in production.

## Backend API Contract

The backend keeps `~/.gmgn-twitter-intel/config.yaml` as the only application configuration source. `ws_token` remains required for Web/API access, but the built-in cockpit does not ask the user to configure or type it. Instead, the same-origin frontend reads `/api/bootstrap` and uses that token automatically for protected read APIs and the WebSocket auth handshake.

Initial endpoints:

- `GET /api/bootstrap` (same-origin frontend bootstrap)
- `GET /api/status`
- `GET /api/recent`
- `GET /api/search`
- `GET /api/token-flow`
- `GET /api/account-alerts`
- `GET /api/narrative-flow`
- `GET /api/account-narratives`
- `GET /api/enrichment-jobs`

Responses use the existing CLI style:

```json
{"ok":true,"data":{}}
```

Errors use:

```json
{"ok":false,"error":"..."}
```

Protected HTTP endpoints accept `Authorization: Bearer <ws_token>` or `?token=<ws_token>`. `/ws` clients must first send `{"type":"auth","token":"..."}` before subscribing.

## Non-Goals

- Full Twitter firehose claims. Coverage remains `public_stream`.
- Trading execution, wallet connection, or portfolio management.
- User account management or browser login flows.
- Replacing the CLI. CLI remains the operational and scripting surface.
- MCP live event stream. `/ws` remains the production push API.
