# Frontend Architecture Hard Cut Verification

Plan: `docs/superpowers/plans/active/2026-05-13-frontend-architecture-hard-cut-plan-cn.md`

Worktree: `.worktrees/frontend-architecture-hard-cut/`

Branch: `codex/frontend-architecture-hard-cut`

## Task 0 Verification

### Worktree

- `git check-ignore -q .worktrees && echo ignored || echo not-ignored`: `ignored`
- `git worktree add .worktrees/frontend-architecture-hard-cut -b codex/frontend-architecture-hard-cut main`: passed
- `git worktree list`: includes `.worktrees/frontend-architecture-hard-cut`
- `git -C .worktrees/frontend-architecture-hard-cut branch --show-current`: `codex/frontend-architecture-hard-cut`
- `git -C .worktrees/frontend-architecture-hard-cut status --short`: initially clean except the copied untracked plan file

The plan file was untracked in the source checkout, so it was copied into the worktree before execution and committed with Task 0 bookkeeping.

### Baseline Commands

- `cd web && npm install`: passed; installed dependencies from lockfile, `0 vulnerabilities`
- `cd web && npm run typecheck`: passed
- `cd web && npm test -- --run`: failed on the first pass, then passed after baseline test-fixture alignment
- `cd web && npm run build`: passed; Vite emitted the existing `Some chunks are larger than 500 kB` warning
- `cd web && npm run lint`: passed
- `make contract-check`: passed, `2 passed in 23.37s`

Initial `npm test -- --run` failures:

- `SearchIntelPage.routing.test.tsx`: fixture still provided legacy `radar_item.live_market` / `anchor_price`; current UI reads `radar_item.market.decision_latest` / `event_anchor`.
- `App.test.tsx`: mocked `useIntelSocket` exposed `liveMarketUpdates` but did not mimic the real hook's `onLiveMarketUpdate` callback.

Baseline test-fixture fixes:

- Search fixture now uses `marketContextFixture` / `marketObservationFixture`.
- App socket mock now dispatches configured market updates through `onLiveMarketUpdate` once the matching market target is subscribed.

Targeted rechecks:

- `cd web && npm test -- --run src/components/__tests__/SearchIntelPage.routing.test.tsx -t "uses market cap"`: passed, `1 passed | 1 skipped`
- `cd web && npm test -- --run src/App.test.tsx -t "patches visible token-radar rows with websocket market updates"`: passed, `1 passed | 55 skipped`

Full recheck after fixes:

- `cd web && npm run typecheck`: passed
- `cd web && npm test -- --run`: passed, `25 passed`, `136 passed`
- `cd web && npm run build`: passed
- `cd web && npm run lint`: passed
- `make contract-check`: passed, `2 passed`

### App Test Matrix

Created `web/src/test/app-test-case-matrix.md`; every current `it(...)` entry in `web/src/App.test.tsx` is mapped to L0/L1/L2/L3 or deletion. No deletion candidates were identified for Task 0.

## Current Risks / Pauses

- Task 8 requires new dev dependencies: `msw`, `jest-axe`, `axe-core`.
- Task 9 requires new dev dependency: `@playwright/test`.
- Task 10 requires new production dependency: `clsx`.

Per the execution pause conditions, dependency installation must pause for user confirmation before those tasks proceed.
