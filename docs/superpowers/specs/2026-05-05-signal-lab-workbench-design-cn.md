# Signal Lab Workbench Design Spec

**Date:** 2026-05-05  
**Status:** Ready for implementation planning  
**Scope:** Redesign Signal Lab from a compact feed into a second-level cockpit workbench.

## Goal

Signal Lab should become the place where a trader can answer one question quickly:

> This social event looked important. Did it become a token signal, did the system freeze a shadow snapshot, did the outcome settle, and who received predictive credit?

The product object is not a raw event, seed, snapshot, or credit row. The product object is a **Signal Chain**:

`Social Event -> Attention Seed -> Snapshot -> Outcome -> Credit`

The implementation must remove hidden symbol-based lineage guessing. The UI must be driven by persisted lineage ids and explicit empty states.

## Product Positioning

Signal Lab is a second-level workbench inside the existing cockpit shell.

- Primary cockpit: Token Radar and live tape, optimized for real-time opportunity scanning. It must still surface Signal Lab activity as a discovery layer.
- Signal Lab workbench: lifecycle audit, optimized for explaining why a social signal exists and whether the closed-loop harness learned from it.
- Detail inspector: right-side tabs for the selected Signal Chain. It is not a separate page.

This keeps Signal Lab close to live token context without forcing a full research-console product yet.

## Information Architecture

Left rail keeps the existing `Views` model:

- `Live`
- `Tokens`
- `Signal Lab`
- `Accounts`
- `Jobs/Ops`

When `Signal Lab` is active:

- The center column is no longer Token Radar.
- The center column becomes the Signal Lab workbench.
- The right drawer becomes the Signal Chain inspector.
- Top-level search, window, horizon, and stream scope remain shared cockpit context.

When `Live` or `Tokens` is active:

- Signal Lab data must not disappear.
- The live surface shows a compact Signal Lab Pulse sourced from the same `SignalLabChain` read model.
- The pulse is a discovery and alert surface, not a second lifecycle table.
- Selecting a pulse row opens the right inspector for that Signal Chain while preserving the current view.
- A `View in Signal Lab` action switches to the Signal Lab workbench with the same chain selected.

The old bottom-deck Signal Lab compact lifecycle panel should be replaced, not simply deleted. The replacement is a Signal Lab Pulse that shows health, stage counts, and the newest/highest-priority Signal Chains. The full lifecycle table belongs only in the Signal Lab workbench.

## Screen Layout

### Top Bar

Reuse the current cockpit top bar.

Required static fields:

- websocket status
- token/API readiness
- global search input
- current window
- current stream scope

Search behavior:

- Token-like input first selects the current unique radar token when available.
- Explicit token lookup uses `$SYMBOL`, CA, chain-prefixed CA, token id, or identity key.
- Bare words remain keyword search unless a unique current radar token exists.

### Left Rail

Required fields:

- view name
- hotkey index
- count
- active state

For Signal Lab:

- Count should be the number of visible Signal Chains, not raw events.
- The view label should be `Signal Lab`.

### Center Workbench

The center workbench has three vertical zones.

#### 1. Header

Required fields:

- title: `Signal Lab`
- subtitle: `Audit watched-account social events into snapshots, outcomes, and predictive credit.`
- context chips:
  - `window {window}`
  - `horizon {horizon}`
  - `scope {all|watched}`

#### 2. Stage Summary

Five stage cards:

- `Extracted`
- `Seeded`
- `Frozen`
- `Settled`
- `Credited`

Each stage card shows:

- count
- short description
- active filter state

Stage descriptions:

- `Extracted`: LLM social-event objects.
- `Seeded`: social events that became attention seeds.
- `Frozen`: seeds with shadow snapshots.
- `Settled`: snapshots with outcome rows.
- `Credited`: settled snapshots with credit rows.

Clicking a stage filters the Signal Chain list. The selected stage is a filter, not a navigation page.

#### 3. Signal Chain List

Each row is one Signal Chain.

Required row fields:

- `stage`: latest lifecycle stage
- `source`: author handle, for example `@cz_binance`
- `event_type`: for example `meme_phrase_seed`
- `asset`: token symbol or unresolved marker
- `horizon`: `6h` or `24h` when snapshot exists
- `summary`: one short explanation of what happened
- `evidence chips`: at most three chips
- `score`: snapshot `combined_score` when available, otherwise social event confidence
- `outcome_status`
- `credit_status`
- `received_at_ms` or `decision_time_ms`

Row information budget:

- One title line.
- One two-line summary.
- At most three chips.
- One score block.
- One status block.

Everything else belongs in the inspector.

## Live Mode Exposure

Live mode is the default operating mode for many sessions, so Signal Lab must remain visible there.

Add a compact `Signal Lab Pulse` to the Live/Tokens cockpit surface.

Required Pulse fields:

- Signal Lab health state: extractor configured/running
- stage summary: `extracted`, `seeded`, `frozen`, `settled`, `credited`
- newest or highest-priority 3-5 Signal Chains
- each row:
  - stage badge
  - source
  - event type
  - asset or unresolved marker
  - score
  - outcome/credit status
  - relative time

Pulse behavior:

- Uses `GET /api/signal-lab/chains?limit=5` with the current window, horizon, and scope.
- Does not reconstruct chains from raw arrays.
- Does not expose full Trace/Snapshot/Outcome/Credit tabs in the compact area.
- Clicking a row opens the shared right inspector on `Trace`.
- `Open Lab` switches active view to `signal_lab` and preserves selected chain.
- If there are no chains, show `No Signal Chains in this window` plus the current window/scope.

This keeps Live mode useful for discovery while keeping Signal Lab workbench responsible for deep audit.

## Right Inspector

The inspector is always about the selected Signal Chain.

Header fields:

- selected object label, for example `BNB · 6h`
- source, for example `@cz_binance`
- schema/prompt label, for example `social-event-v1`
- execution mode label, for example `shadow only`
- score box

Tabs:

- `Trace`
- `Snapshot`
- `Outcome`
- `Credit`

Tabs must be real interactive tabs with:

- `role="tablist"`
- `role="tab"`
- `aria-selected`
- one rendered tab panel at a time

### Trace Tab

Trace is the default tab.

It shows five lifecycle steps:

1. Extracted
2. Seed
3. Snapshot
4. Outcome
5. Credit

Each step must show either concrete fields or a clear empty state.

Extracted fields:

- `extraction_id`
- `event_id`
- `author_handle`
- `event_type`
- `subject`
- `source_action`
- `attention_mechanism`
- `direction_hint`
- `impact_hint`
- `semantic_novelty_hint`
- `confidence`
- first three anchor terms
- first three token candidates
- semantic risks

Seed fields:

- `seed_id`
- `extraction_id`
- `event_id`
- `seed_status`
- `token_uptake_count`
- `top_linked_symbols`
- risks

Seed empty states:

- `not seeded`: social event was not a signal event.
- `asset unresolved`: seed exists but no reliable asset was resolved.

Snapshot fields:

- `snapshot_id`
- `source_event_id`
- `seed_id`
- `asset`
- `horizon`
- `combined_score`
- `shadow_signal`
- `policy_signal`
- `decision_time_ms`
- event clusters
- versions
- risks

Snapshot empty states:

- `not frozen`: no snapshot exists for this seed and horizon.
- `unresolved asset`: seed cannot freeze because asset is unresolved.

Outcome fields:

- `settled_at_ms`
- `actual_return`
- `expected_return`
- `abnormal_return`
- `realized_vol`
- `normalized_outcome`
- `baseline_version`

Outcome empty states:

- `outcome pending`: horizon has not elapsed.
- `missing market`: market data was not sufficient.

Credit fields:

- each `credit_id`
- `cluster_id`
- `event_type`
- `source`
- `horizon`
- `event_score`
- `responsibility`
- `credit`
- `created_at_ms`

Credit empty states:

- `credit not assigned`: outcome is absent or credit worker has not run.

### Snapshot Tab

Snapshot tab shows the ledger for the selected snapshot only.

It must not show Trace content at the same time.

Required fields:

- `snapshot_id`
- `source_event_id`
- `seed_id`
- `asset`
- `horizon`
- `combined_score`
- `shadow_signal`
- `policy_signal`
- `decision_time_ms`
- `outcome_status`
- `credit_status`
- `config_version`
- `prompt_version`
- `schema_version`
- `scoring_version`
- `weight_version`
- `policy_version`
- `risk_version`
- `baseline_version`
- risks
- event clusters
- market state summary

If no snapshot exists, show:

`No snapshot for this chain and horizon.`

### Outcome Tab

Outcome tab shows outcome metrics only.

Required fields:

- `outcome_status`
- `settled_at_ms`
- `actual_return`
- `expected_return`
- `abnormal_return`
- `realized_vol`
- `normalized_outcome`
- `baseline_version`

If pending, show:

`Outcome pending. Settlement waits for decision_time + horizon.`

If missing market, show the exact status from the snapshot.

### Credit Tab

Credit tab shows predictive credit rows only.

Required copy:

`Predictive credit, not causal proof.`

Required fields per row:

- `credit_id`
- `cluster_id`
- `source`
- `event_type`
- `asset`
- `horizon`
- `event_score`
- `responsibility`
- `credit`
- `created_at_ms`

If no rows exist, show:

`Credit not assigned.`

## Data Model

Introduce a frontend type and preferably a backend read model named `SignalLabChain`.

```ts
type SignalLabStage = "extracted" | "seeded" | "frozen" | "settled" | "credited";

type SignalLabChain = {
  chain_id: string;
  stage: SignalLabStage;
  received_at_ms: number;
  updated_at_ms: number;
  asset?: string | null;
  horizon?: string | null;
  source?: string | null;
  event_type?: string | null;
  title: string;
  summary: string;
  score?: number | null;
  outcome_status?: string | null;
  credit_status?: string | null;
  risks: string[];
  lineage: {
    extraction_id?: string | null;
    event_id?: string | null;
    seed_id?: string | null;
    snapshot_id?: string | null;
    source_event_id?: string | null;
  };
  social_event?: SocialEventItem | null;
  seed?: AttentionSeedItem | null;
  snapshot?: HarnessSnapshotItem | null;
  outcome?: HarnessOutcomeItem | null;
  credits: HarnessCreditItem[];
};
```

`chain_id` should be deterministic:

- snapshot chain: `snapshot:{snapshot_id}`
- seed without snapshot: `seed:{seed_id}:{horizon}`
- social event without seed: `event:{extraction_id}`

No chain should be created by matching only `asset` or symbol.

## Backend Read Model

Current frontend reconstruction from independent arrays is insufficient because:

- each endpoint has independent window and limit behavior;
- selected details can lose upstream or downstream rows;
- symbol fallback can attach the wrong snapshot;
- the UI needs lifecycle stage counts, not raw object counts.

Add a backend read endpoint:

`GET /api/signal-lab/chains`

Query params:

- `window`: current window, default `1h`
- `horizon`: `6h` or `24h`
- `scope`: `all` or `matched`
- `stage`: optional stage filter
- `asset`: optional asset filter
- `handle`: optional handle filter
- `q`: optional text filter
- `limit`: default `50`
- `cursor`: optional pagination cursor

Response:

```ts
type SignalLabChainsData = {
  query: {
    window: WindowKey;
    horizon: string;
    scope: ScopeKey;
    stage?: SignalLabStage | null;
    asset?: string | null;
    handle?: string | null;
    q?: string | null;
  };
  summary: {
    extracted: number;
    seeded: number;
    frozen: number;
    settled: number;
    credited: number;
  };
  items: SignalLabChain[];
  returned_count: number;
  has_more: boolean;
  next_cursor?: string | null;
};
```

Backend assembly rules:

1. Start from social events in the requested window.
2. Join attention seeds by `extraction_id` or `event_id`.
3. Join snapshots by persisted `seed_id` or `source_event_id`.
4. Filter snapshots by requested `horizon`.
5. Join outcomes by `snapshot_id`.
6. Join credits by `snapshot_id`.
7. Determine stage from the deepest available lifecycle object.
8. Never join seed to snapshot by symbol alone.

The existing raw endpoints may remain for CLI/debugging, but Signal Lab UI should use the chain endpoint as its product read model.

## Frontend Component Structure

Create or refactor toward:

- `SignalLabWorkbench.tsx`
- `SignalLabStageSummary.tsx`
- `SignalLabToolbar.tsx`
- `SignalChainList.tsx`
- `SignalChainRow.tsx`
- `SignalLabInspector.tsx`
- `SignalTracePanel.tsx`
- `SignalSnapshotPanel.tsx`
- `SignalOutcomePanel.tsx`
- `SignalCreditPanel.tsx`
- `lib/signalLabChains.ts`

Responsibilities:

- `SignalLabWorkbench`: owns query state, selected chain id, and layout.
- `SignalLabStageSummary`: displays lifecycle counts and emits stage filter changes.
- `SignalLabToolbar`: filters by stage, asset, source, horizon, and search.
- `SignalChainList`: renders rows and empty/loading states.
- `SignalChainRow`: row-only display logic; no lineage reconstruction.
- `SignalLabInspector`: tab state and selected chain header.
- Panel components: render one lifecycle section each.
- `lib/signalLabChains.ts`: formatting, product labels, stage labels, and empty-state strings.

Avoid putting new Signal Lab domain logic directly into `App.tsx`.

## State Model

Add store fields:

```ts
type ActiveView = "live" | "tokens" | "signal_lab" | "accounts" | "jobs";
type SignalLabStageFilter = "all" | SignalLabStage;
type SignalLabInspectorTab = "trace" | "snapshot" | "outcome" | "credit";
```

Required state:

- `activeView`
- `signalLabStage`
- `signalLabHorizon`
- `signalLabAsset`
- `signalLabHandle`
- `signalLabSearch`
- `signalLabInspectorTab`

Selection behavior:

- Selecting a chain opens the inspector and defaults to `Trace`.
- Selecting a stage keeps the current selection only if it remains visible.
- Switching horizon refetches chains and clears selection if the selected chain disappears.
- Global search can route into Signal Lab search when active view is `signal_lab`.

## Visual Direction

Tone:

- restrained trader terminal;
- dense but legible;
- amber only for active state and important signal;
- cyan/green for positive status;
- red only for negative risk or failed status.

Design rules:

- No nested cards.
- No marketing hero layout.
- No decorative orbs or generic gradients.
- Use fixed row contracts to prevent compression.
- Use tabbed inspector rather than long stacked panels.
- Let long trace text wrap inside inspector, not in rows.

Typography:

- Keep the current monospace terminal language.
- Use compact headings inside panels.
- No viewport-scaled font sizes.

## Empty And Error States

Workbench empty states:

- No chains:
  `No Signal Chains in this window. Try a wider window or all-stream scope.`
- Extractor off:
  `Extractor is off. Configure llm.openai_api_key to materialize social-event-v1.`
- Chain endpoint error:
  `Signal Lab read model unavailable. Raw harness endpoints are still healthy/unhealthy: {status}.`

Row stage empty states:

- social event only: `extracted only`
- seed without snapshot: `not frozen`
- snapshot without outcome: `outcome pending`
- outcome without credit: `credit not assigned`

Inspector empty states:

- Snapshot missing:
  `No snapshot for this chain and horizon.`
- Outcome pending:
  `Outcome pending. Settlement waits for decision_time + horizon.`
- Credit missing:
  `Credit not assigned.`

## Migration Path

Phase 1: Frontend shell and backend read model

- Add `/api/signal-lab/chains`.
- Add types and tests for `SignalLabChain`.
- Build Signal Lab second-level view.
- Replace live compact lifecycle reconstruction with a Signal Lab Pulse fed by the chain endpoint.
- Keep old raw endpoints available.
- Stop using old array reconstruction for the workbench.

Phase 2: Remove compact lifecycle panel

- Remove the bottom-deck full lifecycle panel from Token Radar.
- Keep a compact Signal Lab Pulse for discovery in Live/Tokens mode.
- Left rail Signal Lab view becomes the primary entry for deep audit.
- Pulse row selection and workbench row selection share the same inspector contract.

Phase 3: Polish and quality

- Add keyboard routing for `3` to Signal Lab.
- Add stage filter keyboard support.
- Add responsive layout.
- Add visual QA screenshots.

## Acceptance Criteria

Product:

- Signal Lab is accessible as a second-level cockpit view.
- Live/Tokens mode still shows Signal Lab data through a compact Pulse when chains exist.
- Clicking a Signal Lab Pulse row opens the shared inspector without requiring a view switch.
- `Open Lab` from a Pulse row switches to the Signal Lab workbench with the same chain selected.
- The center screen shows lifecycle stage counts and Signal Chain rows.
- Rows are readable at desktop and mobile widths without text overlap.
- Right inspector tabs switch content and render one tab panel at a time.
- The selected chain clearly shows persisted lineage ids.
- Empty states explain why a chain has no snapshot, outcome, or credit.

Data:

- Signal Chain rows are linked by `extraction_id`, `event_id`, `seed_id`, `source_event_id`, and `snapshot_id`.
- No Signal Lab product path links by symbol-only matching.
- Stage counts come from the same read model as visible rows.

Tests:

- Backend tests cover chain assembly for extracted-only, seeded-only, frozen, settled, and credited chains.
- Backend tests cover same-symbol decoy snapshots and verify id-based linking.
- Frontend tests cover Signal Lab view routing.
- Frontend tests cover Live/Tokens mode Pulse visibility and row selection.
- Frontend tests cover stage filter behavior.
- Frontend tests cover inspector tab switching.
- Frontend tests cover missing snapshot/outcome/credit empty states.
- Typecheck, build, and full frontend tests pass.
- `uv run pytest`, `uv run ruff check .`, and `uv run python -m compileall src tests` pass.

## Non-Goals

- Do not build a separate full research console yet.
- Do not add graph/network visualization in this iteration.
- Do not add causal claims to credit language.
- Do not preserve the current bottom compact lifecycle UI as a parallel full-audit path.
- Do not add compatibility symbol fallback for chain linking.
