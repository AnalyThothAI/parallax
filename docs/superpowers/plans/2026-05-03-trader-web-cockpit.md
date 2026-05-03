# Trader Web Cockpit Implementation Plan

Date: 2026-05-03

## Goal

Ship a production-shaped frontend cockpit inside this repo, served by the existing FastAPI app and built by Docker, without inventing a second backend or duplicating the pipeline domain model.

## Step 1: Backend Contract Tests

- Add tests for `/api/bootstrap` exposing frontend startup config without manual frontend setup.
- Add tests that protected `/api/*` reads reject missing tokens and accept `Authorization: Bearer <ws_token>`.
- Add tests that seeded events appear through `/api/recent` and `/api/search`.
- Add tests for `/api/status` exposing readiness-style operational state.
- Add tests that a temporary Vite `dist` folder can be served at `/` and `/assets/*`.

## Step 2: Backend API

- Add a small API router module.
- Reuse existing repositories and retrieval services from `app.state.service`.
- Keep `config.yaml` as the single source of truth; the built-in cockpit bootstraps its token from the backend instead of asking the user to configure it separately.
- Keep `/api/bootstrap` unauthenticated for same-origin startup, and keep `/api/*` plus `/ws` protected by `ws_token`.
- Keep endpoints read-only and JSON-only.
- Add FastAPI static mounting with an explicit frontend dist resolver.

## Step 3: Frontend Scaffold

- Add `web/` Vite React TypeScript app.
- Configure Tailwind v4, TanStack Query, Zustand, Reconnecting WebSocket, lucide-react.
- Keep production build output in `web/dist`; Docker copies it into `src/gmgn_twitter_intel/web/dist`.
- Use same-origin `/api/*` and `/ws` in production; Vite dev proxy targets `127.0.0.1:8765`.
- Load `/api/bootstrap` on startup, store the token only in memory, and attach it automatically to HTTP/WS requests.

## Step 4: Cockpit UI

- Build a no-sidebar, high-density Chinese-friendly trader cockpit.
- Include connection state, live tape, token flow, account alerts, narrative flow, evidence search, and ops status.
- Use real endpoints first; graceful empty/loading states second.
- Avoid marketing layout, oversized hero sections, and low-density cards.

## Step 5: Docker And Developer Commands

- Convert Dockerfile to multi-stage Node + Python build.
- Keep Compose runtime config mount unchanged.
- Keep Makefile focused on Python service and Docker operations; frontend build stays in Dockerfile and `web/package.json`.
- Ignore `web/node_modules` and `web/dist`.

## Step 6: Verification

- Run backend tests for new API/static behavior.
- Run full Python tests, Ruff, and compileall.
- Run `npm test`, `npm run typecheck`, and `npm run build`.
- If practical, open the served page in the in-app browser for a smoke check.
