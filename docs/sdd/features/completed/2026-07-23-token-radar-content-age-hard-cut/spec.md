# Spec — Token Radar Content Age and Tape Frontend Hard Cut

**Status**: Verified
**Superseded by**: N/A
**Date**: 2026-07-23
**Owner**: Codex `/root`
**Approved by**: user and GitHub Issue #7
**Approved at**: 2026-07-23
**Verified at**: 2026-07-23
**Related**: `https://github.com/AnalyThothAI/parallax/issues/7`, `docs/FRONTEND.md`, `docs/ARCHITECTURE.md`, `docs/CONTRACTS.md`

## Background

The Live page currently divides its height between Token Radar and a signal Tape.
The Tape combines `/api/recent` replay, WebSocket event buffering, and synthesized
Radar rows, while mobile adds a Radar/Tape task switcher. Those surfaces do not
answer the operator's actual question: how old is the newest source fact in the
current Radar projection, and is the ten-second Radar read still completing?
See the approved source specification in
https://github.com/AnalyThothAI/parallax/issues/7.

`/api/token-radar` already exposes the current projection identity, status, and
`projection.source_max_received_at_ms`. The frontend can therefore show content
age without changing PostgreSQL facts, the current read model, its single writer,
the API schema, or the polling cadence. See
https://github.com/AnalyThothAI/parallax/issues/7.

## Problem

The current signal Tape consumes space and frontend state without providing a
reliable Radar-currentness signal. Its relative times do not advance
continuously, a WebSocket connection state is not Radar read health, and cache
updates from live market patches cannot be treated as successful Radar HTTP
reads.

## Clarifications

| Question | Answer | Approved by | Approved at |
|----------|--------|-------------|-------------|
| What does the advancing number mean? | Current browser time minus the matching Radar projection's `source_max_received_at_ms`; it is content age, not end-to-end latency. | user / Issue #7 | 2026-07-23 |
| Does old content alone create a warning? | No. Quiet windows may have old content while HTTP reads remain healthy. | user / Issue #7 | 2026-07-23 |
| What proves Radar read health? | A real successful `/api/token-radar` HTTP completion for the current window/scope/venue identity. Generic query-cache update time is not accepted. | user / Issue #7 | 2026-07-23 |
| What happens to Tape? | It is hard-deleted from the React product, including mobile task navigation, recent reads, event buffering, merge models, selection state, CSS, and tests. | user / Issue #7 | 2026-07-23 |
| Are backend recent/event/replay contracts removed? | No. `/api/recent`, CLI recent, bootstrap replay limit, and public WebSocket event/replay remain stable backend contracts. | user / Issue #7 | 2026-07-23 |
| Is the status global or interactive? | Neither. It is page-local, non-interactive Radar header text with no popover, Ops link, or background polling on other routes. | user / Issue #7 | 2026-07-23 |
| Is implementation authorized now? | Yes. The active goal is to implement the current spec. | user | 2026-07-23 |

## Requirement Checklist

| Requirement | Quality gate |
|-------------|--------------|
| Live is one full-height Radar with no Tape or mobile task navigation. | Route integration, four-viewport browser checks, and architecture hard-cut scan. |
| Header has title/count/status on row one and venue/window/scope on row two. | Route and browser behavior at 1920, 1366, 834, and 390 widths. |
| Matching source-watermark age advances every second without requests. | Fake-clock route integration asserts 10s to 12s and unchanged request count. |
| A newer watermark resets age; the same watermark continues aging. | Controlled successive Radar responses in the route integration test. |
| Window/scope/venue identities cannot borrow placeholder freshness. | Filter transitions with identity-mismatched placeholder responses. |
| True HTTP completion is independent of live-market cache patches. | Route/query behavior and narrow socket test. |
| Healthy, no-content, delayed, unavailable, timeout, and recovery states match Issue #7. | One route-level state matrix. |
| Cached rows survive one refresh failure or usable stale projection. | Route-level row-preservation assertions. |
| Only health transitions are announced; the one-second age is not live-announced. | Accessibility assertions on rendered status semantics. |
| React sends replay zero and does not retain event items while notifications, market targets, and market patches remain. | One narrow shared-socket contract test. |
| Frontend no longer consumes `/api/recent`, positive replay, Tape, eventItems, or mobile task state. | Architecture hard-cut gate and request log. |
| Backend recent, CLI, and public WS event/replay remain unchanged. | Existing backend tests; no backend source changes. |
| Canonical frontend docs describe the new single-Radar responsive contract. | Documentation diff, SDD validation, and `git diff --check`. |

## Goals

- G1. Make the current Radar projection's content age visibly advance once per
  second and reset only when a newer source watermark arrives.
- G2. Express Radar read health separately as neutral, healthy, delayed, or
  unavailable for the exact current query identity.
- G3. Preserve last-good rows through recoverable refresh/projection
  degradation and recover immediately on a matching fresh HTTP success.
- G4. Hard-delete the frontend Tape product and let Radar use all available
  Live-page height.
- G5. Preserve the backend evidence contracts, Token Radar business semantics,
  ten-second polling, notifications, market updates, and market-target
  subscriptions.

## Non-goals

- N1. No global health indicator, Ops panel, popover, provider heartbeat,
  WebSocket RTT, database probe, or end-to-end latency measurement.
- N2. No age-based warning threshold and no inference that quiet content means
  a broken provider.
- N3. No backend endpoint/schema, database, worker, queue, provider, ranking,
  factor, admission, row-identity, or window-semantics change.
- N4. No deletion or rename of backend `/api/recent`, CLI recent, bootstrap
  replay limit, or public WebSocket event/replay.
- N5. No guarantee that the server stops sending live events; React only stops
  requesting replay, retaining events, and rendering them.
- N6. No production deployment or unrelated route redesign.

## Interface contracts

- `/` renders one full-height Token Radar and keeps route-aware
  `market_targets`.
- Radar header row one contains `Token Radar`, current case count, and a
  non-interactive page-local status. Row two contains venue, window, and scope.
- Content age is `max(0, now - source_max_received_at_ms)` for a response whose
  window, scope, and venue match the current query. Missing or nonpositive
  watermark displays `暂无内容`.
- The display clock ticks once per second and performs no refetch, invalidation,
  subscription change, or write. It stops on unmount.
- A true matching fresh HTTP success is green. One background refresh failure
  with last-good rows, or a usable stale/pending projection with last-good rows,
  is yellow. Initial failure, no usable cache, failed projection without
  last-good rows, or more than 30 seconds since the current identity's last true
  HTTP success is red.
- Switching identity is neutral until that identity receives a matching
  response. A live-market query-cache patch is never a Radar HTTP success.
- The visible age is not an aria-live region. Only health-state transitions use
  a polite announcement.
- The React WebSocket subscription sends `replay: 0`, exposes no `eventItems`,
  and preserves notification buffering, connection state, market-target
  registration, and live-market query-cache patches.

## Acceptance criteria

- AC1. WHEN Live renders THEN Radar SHALL occupy the available page height and no Tape, Tape task navigation, Tape selection, or `/api/recent` request SHALL exist in the frontend path.
- AC2. WHEN a matching fresh response has a watermark ten seconds behind the browser clock THEN the header SHALL show healthy content age at 10s, advance to 12s after two local seconds without an extra request, and reset when a newer watermark arrives.
- AC3. WHEN the current venue, window, or scope changes THEN the old response SHALL NOT provide the new view's age or healthy claim before a fully matching response completes.
- AC4. WHEN matching HTTP reads continue succeeding with a fresh projection THEN refresh health SHALL remain green regardless of content age, and a response without a valid watermark SHALL display `暂无内容`.
- AC5. WHEN one background refresh fails or a usable projection is stale or pending and current-view last-good rows exist THEN those rows SHALL remain and status SHALL be yellow.
- AC6. WHEN initial read fails, no usable cache exists, projection fails without last-good rows, or current-view true HTTP success is older than 30 seconds THEN status SHALL be red and the next matching fresh success SHALL recover green.
- AC7. WHEN the status clock runs THEN it SHALL make no extra network or cache invalidation work and SHALL stop after unmount.
- AC8. WHEN assistive technology observes the header THEN health transitions SHALL be politely announced, one-second age changes SHALL NOT be live announced, and the status SHALL not enter the focus order.
- AC9. WHEN the React socket subscribes THEN replay SHALL be zero and event messages SHALL not be retained, while notifications, connection lifecycle, live-market patches, and route-aware market targets SHALL continue working.
- AC10. WHEN the frontend source and tests are scanned THEN retired Tape UI, model, query, selection, mobile-task, CSS, eventItems, and positive-replay paths SHALL be absent without rejecting preserved backend public contracts.
- AC11. WHEN Live renders at 1920, 1366, 834, and 390 widths THEN its two-row header and explicit status SHALL be visible, the page SHALL have no horizontal overflow, and the final Radar row SHALL remain reachable without a mobile bottom task bar.
- AC12. WHEN completion is claimed THEN focused and full frontend gates, selected existing backend contract tests, canonical docs, residual scans, and SDD verify gates SHALL all have direct successful evidence.

## Verification

Verification evidence will be recorded in
`docs/sdd/features/completed/2026-07-23-token-radar-content-age-hard-cut/verification.md`.
No passing claim is recorded until its cited command exits zero.
