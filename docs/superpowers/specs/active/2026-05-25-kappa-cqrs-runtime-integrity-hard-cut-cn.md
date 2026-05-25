# Kappa/CQRS Runtime Integrity Hard Cut Spec

Date: 2026-05-25

## Problem

Runtime workers were carrying "safety net" behavior that made correctness look
less dependent on explicit facts, but at production scale it creates broad
database scans, write amplification, and hidden coupling:

- Token Radar projection performed an idle catch-up scan over recent resolved
  intents when no dirty target was claimed.
- Resolution refresh discovered due lookup keys by scanning recent intent/event
  facts instead of claiming explicit queue rows.
- Public API read paths could call candle/quote providers directly.
- WebSocket fan-out could await a slow subscriber inline with worker publish
  paths.
- Wake waits shared the event loop default executor.

These are Kappa/CQRS violations because runtime correctness should be driven by
persisted facts, durable control-plane queues, and rebuildable read models.

## Scope

This hard cut removes compatibility and runtime fallback paths. Normal workers
must not run broad fact-table scans to compensate for missed wakes. Repair is an
explicit operator action that enqueues dirty targets from persisted facts.

## Acceptance Criteria

- `TokenRadarProjectionWorker` only claims `token_radar_dirty_targets`; idle
  loops do not scan `events`, `token_intents`, or `token_intent_resolutions`.
- Resolution refresh uses `token_discovery_dirty_lookup_keys` and never calls a
  runtime recent-facts due lookup scan.
- Fact write/reprocess paths enqueue the required dirty lookup or radar dirty
  targets in the same unit of work.
- Public HTTP/WebSocket read paths do not call market candle or stock quote
  providers.
- WebSocket publish is bounded per client; a slow client cannot stall all
  subscribers or a worker publish path.
- Wake `LISTEN` waits use a dedicated executor and are closed through worker
  lifecycle cleanup.
- Architecture tests guard the above invariants.

## Non-Goals

- No compatibility fallback for old confidence fields or provider-backed candle
  reads.
- No new read model for stock quotes or candle OHLC in this change.
- No runtime repair loop hidden inside a projection worker.
