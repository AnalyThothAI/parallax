# Frontend

> **Scope.** Owns the `web/` architecture, layer responsibilities, component conventions, and the manual UI verification gate. Backend layer boundaries live in `ARCHITECTURE.md`. Build / install commands live in `SETUP.md`.

## Layer map (`web/src/`)

| Directory | Responsibility |
|-----------|----------------|
| `api/` | Thin clients for `/api/*` HTTP routes and the `/ws` WebSocket. Owns request/response typing aligned with `CONTRACTS.md`; never embeds business logic. |
| `domain/` | Pure TypeScript domain models, score-decomposition helpers, and time-window arithmetic. Framework-free; unit-testable in isolation. |
| `store/` | Reactive state holders that bridge `api/` push frames into UI state. Owns subscription lifecycle and replay-window plumbing. |
| `components/` | React components. Composed from `domain/` types and `store/` state; do not call `api/` directly — go through `store/`. |
| `lib/` | Cross-cutting utilities (formatting, classnames, env). No domain knowledge. |
| `test/` | Vitest suites. Mirror the layer they test (`api/`, `domain/`, `store/`, `components/`). |

## Conventions

- **Payload contract.** Component props that mirror API payloads share their type names with `api/` clients. A breaking API change updates `api/`, `domain/`, and `components/` together.
- **State discipline.** No component reads from `api/` directly; subscriptions live in `store/`. Tests for `store/` may stub the WebSocket.
- **Score display.** Any displayed ranking score includes its component breakdown (per the rule in `DESIGN_DISCIPLINE.md`); the breakdown comes from the API, not local recomputation.
- **No business logic in JSX.** Decisions move into `domain/`; `components/` only renders.

## Build & deploy

See `SETUP.md` for `npm install / dev / build / preview` commands. Production bundles ship inside the same Docker image as the Python service and are served by the `api/` static-file mount.

## UI verification gate

Per `WORKFLOW.md`, UI flows that tests cannot exercise must be checked manually before declaring completion. The minimum manual checklist for any `web/`-touching change:

1. Hard-reload the browser at the affected route.
2. Subscribe to a known handle and confirm the live event push reaches the relevant component.
3. Open the network panel; confirm no failing `/api/*` requests; confirm WebSocket frames arrive.
4. Verify any displayed ranking score still shows its component breakdown.
