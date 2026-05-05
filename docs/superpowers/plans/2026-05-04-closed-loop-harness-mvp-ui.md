# Closed Loop Harness MVP UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the current narrative-first cockpit UI with an MVP closed-loop harness UI while preserving the existing high-density trading cockpit shell.

**Architecture:** Keep `Topbar`, `SideRail`, `TokenRadarTable`, `LiveSignalTape`, search, and the right drawer shell. Replace old narrative-facing types, queries, panel, selected signal kind, and drawer tab with social event, attention seed, snapshot, outcome, and credit read models.

**Tech Stack:** React 19, TypeScript, TanStack Query, Zustand, Vitest, Testing Library, existing CSS cockpit style system.

**Related design:** `docs/superpowers/specs/2026-05-04-closed-loop-harness-mvp-ui-component-design-cn.md`

**Concrete page design:** `docs/superpowers/specs/2026-05-04-closed-loop-harness-concrete-page-design-cn.md`

**Static prototype:** `docs/prototypes/closed-loop-harness-cockpit.html`

---

## Implementation Principles

1. Do not preserve old narrative UI compatibility.
2. Do not compute harness score, outcome, or credit in the frontend.
3. Do not redesign the full cockpit shell.
4. Do not add charting libraries for MVP.
5. Preserve current token radar and token evidence workflows.
6. Show missing harness state explicitly as harness state, not as narrative fallback.

## File Structure

### Modify

- `web/src/api/types.ts`: replace product-facing narrative types with harness read models and update `TokenDetailTab`.
- `web/src/store/useTraderStore.ts`: add harness view/horizon state and remove narrative detail tab state.
- `web/src/App.tsx`: add harness queries, replace narrative query usage, replace side rail label, replace bottom panel, update selected signal union.
- `web/src/components/LiveSignalTape.tsx`: replace tape narrative kind with social event, attention seed, and snapshot kinds.
- `web/src/components/TokenDetailDrawer.tsx`: replace `Narratives` tab with `Harness` tab and pass harness props.
- `web/src/styles.css`: add harness compact rows, chips, trace, ledger, and outcome styles.
- `web/src/App.test.tsx`: rewrite old narrative UI tests to harness UI tests.

### Create

- `web/src/components/HarnessPanel.tsx`
- `web/src/components/HarnessHealthStrip.tsx`
- `web/src/components/SocialEventFeed.tsx`
- `web/src/components/AttentionSeedList.tsx`
- `web/src/components/HarnessTrace.tsx`
- `web/src/components/SnapshotLedger.tsx`
- `web/src/components/OutcomeCard.tsx`
- `web/src/components/CreditLedger.tsx`
- `web/src/components/HarnessTokenTab.tsx`
- `web/src/components/ScoreBucketPanel.tsx`
- `web/src/components/SettlementCoveragePanel.tsx`
- `web/src/components/WeightDriftPanel.tsx`

### Delete

- `web/src/components/NarrativePanel.tsx`

Deletion is intentional. Do not keep it as a wrapper around `HarnessPanel`.

## Task 1: Frontend Harness Types And Store State

**Files:**

- Modify: `web/src/api/types.ts`
- Modify: `web/src/store/useTraderStore.ts`
- Modify: `web/src/App.test.tsx`

- [ ] **Step 1: Write failing tests for removed narrative surface**

Add assertions to the existing cockpit test suite:

```tsx
it("removes narrative product surface from the cockpit shell", async () => {
  renderWithQuery(<App />);

  await screen.findByText("Token");
  expect(screen.queryByRole("button", { name: "Narratives" })).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Harness" })).toBeInTheDocument();
});
```

Expected before implementation: FAIL because the left rail and drawer still expose `Narratives`.

- [ ] **Step 2: Update `TokenDetailTab`**

Change:

```ts
export type TokenDetailTab = "timeline" | "posts" | "score" | "narratives" | "accounts";
```

to:

```ts
export type TokenDetailTab = "timeline" | "posts" | "score" | "harness" | "accounts";
```

- [ ] **Step 3: Add harness read model types**

Add these exported types in `web/src/api/types.ts`:

```ts
export type AnchorTerm = {
  term: string;
  role: "subject" | "meme_phrase" | "product" | "asset" | "person" | "venue" | string;
  evidence: string;
};

export type SocialTokenCandidate = {
  symbol?: string | null;
  project_name?: string | null;
  chain?: string | null;
  address?: string | null;
  evidence: string;
  confidence: number;
};

export type SocialEventItem = {
  extraction_id: string;
  event_id: string;
  author_handle?: string | null;
  received_at_ms: number;
  schema_version: string;
  event_type: string;
  source_action: string;
  subject: string;
  direction_hint: string;
  attention_mechanism: string;
  impact_hint: number;
  semantic_novelty_hint: number;
  confidence: number;
  is_signal_event: boolean;
  anchor_terms: AnchorTerm[];
  token_candidates: SocialTokenCandidate[];
  semantic_risks: string[];
  summary_zh: string;
  event?: EventRecord | null;
};

export type AttentionSeedItem = {
  seed_id: string;
  extraction_id: string;
  event_id: string;
  author_handle?: string | null;
  received_at_ms: number;
  event_type: string;
  subject: string;
  anchor_terms: AnchorTerm[];
  token_uptake_count: number;
  top_linked_symbols: string[];
  seed_status: string;
  risks: string[];
};

export type HarnessClusterSummary = {
  cluster_id: string;
  event_type: string;
  source?: string | null;
  event_score: number;
};

export type HarnessVersionBlock = {
  config_version: string;
  prompt_version: string;
  schema_version: string;
  scoring_version: string;
  weight_version: string;
  policy_version: string;
  risk_version: string;
  baseline_version: string;
};

export type HarnessSnapshotItem = {
  snapshot_id: string;
  asset: string;
  decision_time_ms: number;
  horizon: string;
  combined_score: number;
  policy_signal: string;
  shadow_signal: string;
  event_clusters: HarnessClusterSummary[];
  market_state: Record<string, unknown>;
  versions: HarnessVersionBlock;
  outcome_status: string;
  credit_status: string;
  risks: string[];
};

export type HarnessOutcomeItem = {
  snapshot_id: string;
  settled_at_ms: number;
  actual_return: number;
  expected_return: number;
  abnormal_return: number;
  realized_vol: number;
  normalized_outcome: number;
  baseline_version: string;
};

export type HarnessCreditItem = {
  credit_id: string;
  snapshot_id: string;
  cluster_id: string;
  asset: string;
  event_type: string;
  source: string;
  horizon: string;
  event_score: number;
  responsibility: number;
  credit: number;
  created_at_ms: number;
};

export type HarnessHealth = {
  llm_configured: boolean;
  extractor_running: boolean;
  schema_success_rate?: number | null;
  pending_jobs: number;
  snapshots_24h: number;
  pending_outcomes: number;
  settlement_coverage?: number | null;
};

export type SocialEventsData = { items: SocialEventItem[] };
export type AttentionSeedsData = { items: AttentionSeedItem[] };
export type HarnessSnapshotsData = { items: HarnessSnapshotItem[] };
export type HarnessOutcomesData = { items: HarnessOutcomeItem[] };
export type HarnessCreditsData = { items: HarnessCreditItem[] };
export type HarnessHealthData = HarnessHealth;
```

- [ ] **Step 4: Add harness state to Zustand store**

Add:

```ts
type HarnessView = "events" | "seeds" | "snapshots" | "outcomes" | "evaluation";
type HarnessHorizon = "6h" | "24h";
```

Add store fields:

```ts
harnessView: HarnessView;
harnessHorizon: HarnessHorizon;
setHarnessView: (view: HarnessView) => void;
setHarnessHorizon: (horizon: HarnessHorizon) => void;
```

Default:

```ts
harnessView: "events",
harnessHorizon: "6h",
```

- [ ] **Step 5: Run typecheck**

Run:

```bash
cd web
npm run typecheck
```

Expected after this task: type errors remain in components that still refer to `narratives`; these are resolved in later tasks.

## Task 2: Build Harness Compact Panel Components

**Files:**

- Create: `web/src/components/HarnessHealthStrip.tsx`
- Create: `web/src/components/SocialEventFeed.tsx`
- Create: `web/src/components/AttentionSeedList.tsx`
- Create: `web/src/components/HarnessPanel.tsx`
- Modify: `web/src/App.test.tsx`

- [ ] **Step 1: Add component-level render tests through `App.test.tsx`**

Add mock data to `mockApi()` for:

```text
/api/social-events
/api/attention-seeds
/api/harness-snapshots
/api/harness-health
```

Use one social event from `@cz_binance`, one seed from `@heyibinance`, and one snapshot for `BNB`.

Add test:

```tsx
it("renders harness panel with social events, seeds, and snapshots", async () => {
  renderWithQuery(<App />);

  fireEvent.click(await screen.findByRole("button", { name: "Harness" }));
  expect(await screen.findByText("@cz_binance")).toBeInTheDocument();
  expect(screen.getByText("meme_phrase_seed")).toBeInTheDocument();
  expect(screen.getByText("schema 96%")).toBeInTheDocument();
  expect(screen.getByText("shadow LONG_SMALL")).toBeInTheDocument();
});
```

Expected before implementation: FAIL because no harness panel exists.

- [ ] **Step 2: Implement `HarnessHealthStrip`**

Render exactly four compact metrics:

```text
schema
snap
pending
settled
```

Use `schema_success_rate` and `settlement_coverage` as percentage labels. If a value is null, show `-`.

- [ ] **Step 3: Implement `SocialEventFeed`**

Rows render:

```text
@handle
event_type
subject
anchor term chips
impact / novelty / confidence
```

Click calls `onSelect(item)`.

- [ ] **Step 4: Implement `AttentionSeedList`**

Rows render:

```text
@handle
event_type
seed_status
subject
top linked symbols
first two risks
```

Click calls `onSelect(item)`.

- [ ] **Step 5: Implement `HarnessPanel`**

Use a segmented local state:

```ts
type HarnessPanelMode = "events" | "seeds" | "snapshots";
```

Modes:

```text
Events -> SocialEventFeed
Seeds -> AttentionSeedList
Snapshots -> compact snapshot rows
```

Empty states:

```text
当前窗口暂无 social event
当前窗口暂无 attention seed
当前窗口暂无 harness snapshot
```

- [ ] **Step 6: Run focused tests**

Run:

```bash
cd web
npm test -- --run src/App.test.tsx
```

Expected after component creation but before wiring: tests that require App integration still fail.

## Task 3: Wire App Queries, Side Rail, And Bottom Deck

**Files:**

- Modify: `web/src/App.tsx`
- Modify: `web/src/App.test.tsx`

- [ ] **Step 1: Replace narrative queries**

Remove:

```ts
const narrativeQuery = ...
const frontierQuery = ...
const narratives = ...
const frontierItems = ...
```

Add:

```ts
const socialEventsQuery = useQuery({
  queryKey: ["social-events", windowKey, handles],
  queryFn: () => getApi<SocialEventsData>("/api/social-events", {
    token,
    params: { window: windowKey, limit: 50, handles }
  }),
  enabled: Boolean(token),
  refetchInterval: 10_000
});

const attentionSeedsQuery = useQuery({
  queryKey: ["attention-seeds", windowKey, handles],
  queryFn: () => getApi<AttentionSeedsData>("/api/attention-seeds", {
    token,
    params: { window: windowKey, limit: 50, handles }
  }),
  enabled: Boolean(token),
  refetchInterval: 10_000
});

const harnessSnapshotsQuery = useQuery({
  queryKey: ["harness-snapshots", windowKey, harnessHorizon],
  queryFn: () => getApi<HarnessSnapshotsData>("/api/harness-snapshots", {
    token,
    params: { window: windowKey, horizon: harnessHorizon, limit: 50 }
  }),
  enabled: Boolean(token),
  refetchInterval: 15_000
});

const harnessHealthQuery = useQuery({
  queryKey: ["harness-health"],
  queryFn: () => getApi<HarnessHealthData>("/api/harness-health", { token }),
  enabled: Boolean(token),
  refetchInterval: 15_000
});
```

- [ ] **Step 2: Replace selected signal narrative kind**

Remove:

```ts
| { kind: "narrative"; item: AttentionFrontierItem }
```

Add:

```ts
| { kind: "social_event"; item: SocialEventItem }
| { kind: "attention_seed"; item: AttentionSeedItem }
| { kind: "harness_snapshot"; item: HarnessSnapshotItem }
```

- [ ] **Step 3: Replace rail label**

Change the third rail button from `Narratives` to `Harness`.

Keep keyboard numbering stable:

```text
1 Live
2 Tokens
3 Harness
4 Accounts
5 Jobs/Ops
```

- [ ] **Step 4: Replace bottom deck panel**

Replace:

```tsx
<NarrativePanel ... />
```

with:

```tsx
<HarnessPanel
  health={harnessHealthQuery.data?.data ?? defaultHarnessHealth(statusQuery.data?.data)}
  isLoading={socialEventsQuery.isLoading || attentionSeedsQuery.isLoading || harnessSnapshotsQuery.isLoading}
  seeds={attentionSeedsQuery.data?.data.items ?? []}
  selectedId={selectedTapeEventId}
  snapshots={harnessSnapshotsQuery.data?.data.items ?? []}
  socialEvents={socialEventsQuery.data?.data.items ?? []}
  onSelectEvent={(item) => setSelectedSignal({ kind: "social_event", item })}
  onSelectSeed={(item) => setSelectedSignal({ kind: "attention_seed", item })}
  onSelectSnapshot={(item) => setSelectedSignal({ kind: "harness_snapshot", item })}
/>
```

Define `defaultHarnessHealth(status)` in `App.tsx` only as a display adapter for existing status fields while `/api/harness-health` is loading. It must not invent settlement coverage.

- [ ] **Step 5: Run focused tests**

Run:

```bash
cd web
npm test -- --run src/App.test.tsx
```

Expected after wiring: harness panel tests pass, old narrative tests fail until rewritten.

## Task 4: Replace Token Drawer Narrative Tab With Harness Tab

**Files:**

- Create: `web/src/components/SnapshotLedger.tsx`
- Create: `web/src/components/OutcomeCard.tsx`
- Create: `web/src/components/CreditLedger.tsx`
- Create: `web/src/components/HarnessTokenTab.tsx`
- Modify: `web/src/components/TokenDetailDrawer.tsx`
- Modify: `web/src/App.tsx`
- Modify: `web/src/App.test.tsx`

- [ ] **Step 1: Rewrite drawer tests**

Replace the old Chinese narrative display test with:

```tsx
it("opens token Harness tab and shows linked seeds, snapshots, outcomes, and credits", async () => {
  renderWithQuery(<App />);

  await screen.findByRole("button", { name: "select token $UPEG" });
  fireEvent.click(screen.getByRole("button", { name: "Harness" }));

  expect(await screen.findByText("Linked Seeds")).toBeInTheDocument();
  expect(screen.getByText("Active Snapshots")).toBeInTheDocument();
  expect(screen.getByText("Latest Outcome")).toBeInTheDocument();
  expect(screen.getByText("Credit Rows")).toBeInTheDocument();
  expect(screen.queryByText("narrative_display_missing")).not.toBeInTheDocument();
});
```

Expected before implementation: FAIL because the drawer still has `Narratives`.

- [ ] **Step 2: Implement `SnapshotLedger`**

Render:

```text
snapshot_id
asset
horizon
combined_score
shadow_signal
policy_signal
outcome_status
credit_status
config_version
prompt_version
schema_version
```

- [ ] **Step 3: Implement `OutcomeCard`**

Render pending and settled states:

```text
outcome pending · horizon not reached
actual
expected
abnormal
vol
normalized
```

- [ ] **Step 4: Implement `CreditLedger`**

Render credit rows:

```text
event_type
source
horizon
event_score
responsibility
credit
```

Add small text:

```text
Predictive credit, not causal proof.
```

- [ ] **Step 5: Implement `HarnessTokenTab`**

Render sections in this order:

```text
Linked Seeds
Active Snapshots
Latest Outcome
Credit Rows
```

Filter token-related data in `App.tsx`, not inside low-level ledger components.

- [ ] **Step 6: Update `TokenDetailDrawer` props and tabs**

Replace `Narratives` tab item:

```ts
{ tab: "narratives", label: "Narratives" }
```

with:

```ts
{ tab: "harness", label: "Harness" }
```

Remove props:

```ts
narratives
narrativeLinks
llmConfigured
```

Add props:

```ts
harnessSeeds
harnessSnapshots
harnessOutcomes
harnessCredits
isHarnessLoading
onSelectSnapshot
```

- [ ] **Step 7: Run focused tests**

Run:

```bash
cd web
npm test -- --run src/App.test.tsx
```

Expected after drawer replacement: no test should assert `Narratives` exists.

## Task 5: Update Live Signal Tape For Harness Objects

**Files:**

- Modify: `web/src/components/LiveSignalTape.tsx`
- Modify: `web/src/App.tsx`
- Modify: `web/src/App.test.tsx`

- [ ] **Step 1: Rewrite tape type**

Replace:

```ts
| (LiveSignalTapeBase & { kind: "narrative"; item: AttentionFrontierItem })
```

with:

```ts
| (LiveSignalTapeBase & { kind: "social_event"; item: SocialEventItem })
| (LiveSignalTapeBase & { kind: "attention_seed"; item: AttentionSeedItem })
| (LiveSignalTapeBase & { kind: "harness_snapshot"; item: HarnessSnapshotItem })
```

- [ ] **Step 2: Update tape title/body/time helpers**

Examples:

```text
social_event -> @cz_binance · meme_phrase_seed
attention_seed -> @heyibinance · linked · BNB
harness_snapshot -> BNB · shadow LONG_SMALL · score 42
```

- [ ] **Step 3: Update `buildLiveSignalTapeItems`**

Inputs:

```ts
liveItems
tokenItems
socialEvents
seeds
snapshots
```

Output should keep live event and token tape behavior stable, then add harness rows.

- [ ] **Step 4: Add tape tests**

Add assertion:

```tsx
expect(await screen.findByText("@cz_binance · meme_phrase_seed")).toBeInTheDocument();
expect(screen.getByText("BNB · shadow LONG_SMALL")).toBeInTheDocument();
```

- [ ] **Step 5: Run tests**

Run:

```bash
cd web
npm test -- --run src/App.test.tsx
```

Expected: tape dedupe and token click tests still pass.

## Task 6: Add Evaluation Components Without Promoting Them To Main Screen

**Files:**

- Create: `web/src/components/ScoreBucketPanel.tsx`
- Create: `web/src/components/SettlementCoveragePanel.tsx`
- Create: `web/src/components/WeightDriftPanel.tsx`
- Modify: `web/src/api/types.ts`
- Modify: `web/src/App.test.tsx`

- [ ] **Step 1: Add evaluation types**

Add:

```ts
export type ScoreBucketItem = {
  bucket: string;
  sample_count: number;
  avg_normalized_outcome: number;
  avg_abnormal_return: number;
  hit_rate: number;
  settled_count: number;
  pending_count: number;
};

export type HarnessWeightItem = {
  key: string;
  weight_type: string;
  asset?: string | null;
  horizon: string;
  n: number;
  mean_credit: number;
  weight: number;
  status: "report_only" | "candidate" | "active" | string;
};
```

- [ ] **Step 2: Implement `ScoreBucketPanel`**

Use an HTML table and CSS bars. Do not import a chart library.

- [ ] **Step 3: Implement `SettlementCoveragePanel`**

Show:

```text
settled
pending
missing_market
insufficient
```

- [ ] **Step 4: Implement `WeightDriftPanel`**

Show `report_only` status for MVP. Do not imply active live scoring influence.

- [ ] **Step 5: Add tests**

Add a component render test in `App.test.tsx` or a new focused component test file:

```tsx
expect(screen.getByText(">=0.8")).toBeInTheDocument();
expect(screen.getByText("report_only")).toBeInTheDocument();
```

Only wire these components into an evaluation view after backend `/api/harness-score-buckets` exists.

## Task 7: CSS And Responsive QA

**Files:**

- Modify: `web/src/styles.css`

- [ ] **Step 1: Add harness classes**

Add styles for:

```text
harness-panel
harness-health-strip
harness-feed
harness-row
harness-row.selected
harness-anchor-chip
harness-risk-chip
harness-trace
harness-trace-step
snapshot-ledger
outcome-card
credit-ledger
score-bucket-panel
score-bucket-row
weight-drift-row
```

- [ ] **Step 2: Enforce stable row density**

Rows must use fixed min/max heights:

```css
.harness-row {
  min-height: 56px;
  max-height: 76px;
  overflow: hidden;
}
```

- [ ] **Step 3: Prevent chip overflow**

Use:

```css
.harness-anchor-chip,
.harness-risk-chip {
  max-width: 140px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
```

- [ ] **Step 4: Run visual smoke check in browser**

Start the web dev server if it is not already running:

```bash
cd web
npm run dev -- --host 127.0.0.1 --port 5173
```

Open:

```text
http://localhost:8765/
```

Verify:

```text
left rail shows Harness
bottom panel shows Harness rows
drawer tab shows Harness
no visible Narratives tab
no row text overlap at desktop width
```

## Task 8: Final Verification

**Files:**

- All files touched by previous tasks.

- [ ] **Step 1: Run web verification**

Run:

```bash
cd web
npm run typecheck
npm test -- --run
npm run build
```

- [ ] **Step 2: Run repository verification if backend files changed in same branch**

Run:

```bash
uv run pytest
uv run ruff check .
uv run python -m compileall src tests
```

- [ ] **Step 3: Search for forbidden narrative UI surface**

Run:

```bash
rg -n "NarrativePanel|kind: \"narrative\"|tab: \"narratives\"|narrative_display_missing|Narratives" web/src
```

Expected: no matches in active frontend code. Test fixtures may contain historical comments only if they assert removal.

## Rollout Order

1. Merge backend read models first.
2. Merge `HarnessPanel` and side rail replacement.
3. Merge token drawer `Harness` tab.
4. Merge tape harness kinds.
5. Add evaluation panels after score bucket data exists.
6. Only polish density after real data is visible for at least one session.

## Success Criteria

The UI implementation is complete when:

- `Narratives` no longer appears as a live cockpit entry point;
- old narrative selected signal kind is gone;
- `HarnessPanel` shows social events, attention seeds, and snapshots;
- token drawer has a `Harness` tab;
- outcome and credit states are visible but not phrased as causal proof;
- no frontend code derives harness display from old `narrative_label`;
- web typecheck, tests, and build pass.
