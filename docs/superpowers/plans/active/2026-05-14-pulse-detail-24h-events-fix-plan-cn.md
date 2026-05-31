# Pulse Detail Page — 24h Source Events Fix Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop the Pulse detail UI from showing only the window-scoped (1h / 4h) slice of source events and start surfacing the full 24h target timeline that the backend already projects, while keeping the agent's `evidence_event_ids` semantics intact as the "cited" subset.

**Architecture:** `/api/target-posts?window=24h` is a pre-existing endpoint that returns the full 24h corpus for a resolved target (it routes through `TokenTargetPostsService.target_posts` → `TokenTargetRepository.timeline_rows` which already filters by `received_at_ms >= now - 24h`). Today it omits `author_followers` and `action`, which the Pulse view-model needs for author classification. We extend the SELECT + serializer to add those two fields, then change `PulseDetailRoutePage` and the inline branch of `SignalLabPage` to fetch 24h target posts as the primary event corpus and pass the agent's `source_event_ids` / `decision.evidence_event_ids` as a `citedSet`. The view-model `buildPulseDetailView` is widened to accept `(corpus, citedSet)` and the burst histogram + Evidence list re-derive from the full corpus. `research_only` pulses (no resolved target) fall back to the existing `/api/social-events/by-ids` path. Hard cut: the prior usage of `useSourceEvents` in `PulseDetailRoutePage` and `SignalLabPage` is replaced, not preserved behind a flag.

**Tech Stack:**
- Backend: Python 3, FastAPI, psycopg, pytest. Touches `src/parallax/domains/token_intel/repositories/token_target_repository.py`, `.../read_models/token_target_post_serializer.py`, `src/parallax/app/surfaces/api/schemas.py`.
- Frontend: React 18, TypeScript, Vite, vitest. Touches `web/src/features/signal-lab/{api,model,ui}` and `web/src/lib/types/frontend-contracts.ts`.
- E2E: Playwright (`web/tests/e2e/golden-paths/`).

**Root-cause one-liner**
`token_radar_projection._project_group` writes `source_event_ids_json` filtered to `[now - window_ms, now]` (line 369). `pulse_candidate_worker._asset_context` then copies that array verbatim into the pulse's `source_event_ids_json` (worker line 377). For a `window=1h` pulse on TROLL (which has 200+ events over 48h in `events`), only the 10 events from the last hour reach the UI, but the researcher needs the 24h view.

**Spec backreference**
- `docs/superpowers/specs/active/2026-05-14-pulse-detail-redesign-cn.md` §"第一性原则" — researcher view should answer "为什么这时出现" with full event timeline.
- This fix preserves the agent's window-scoped scoring decision while widening the researcher-facing event corpus. The `target_id` is a resolved asset, so we have the right primary key to fan out from the pulse to the timeline.

**Commands cheat-sheet**
- Backend test: `uv run pytest tests/unit/test_token_target_posts_service.py tests/integration/test_api_http.py -v`
- Frontend unit test: `cd web && pnpm test -- --run path/to.test.ts`
- Frontend typecheck: `cd web && pnpm typecheck`
- Frontend lint: `cd web && pnpm lint`
- Frontend e2e: `cd web && pnpm test:e2e -- pulse-detail.spec.ts`
- DB shell: `docker exec parallax-postgres-1 psql -U parallax_app -d parallax`
- Docker rebuild + restart: `GITHUB_TOKEN=$(gh auth token) docker compose build app && GITHUB_TOKEN=$(gh auth token) docker compose up -d --force-recreate app`
- Audit fixture: TROLL pulse `pulse-958846897ef70564fa1ba0de83bd05d237f7d5af` (resolved `target_id` = `asset:solana:token:5UUH9RTDiSpq6HKS6bp4NdU9PNJpXRXuiw6ShBTBhgH2`, 50+ 24h events).

**File Structure (created or modified):**

```
Backend
  src/parallax/domains/token_intel/repositories/token_target_repository.py  [MODIFY SELECT]
  src/parallax/domains/token_intel/read_models/token_target_post_serializer.py [MODIFY surface fields]
  src/parallax/app/surfaces/api/schemas.py                                  [MODIFY TargetPostsItem]
  tests/integration/test_api_http.py                                                  [MODIFY add assertion]

Frontend
  web/src/lib/types/frontend-contracts.ts                                             [MODIFY add TargetPost fields]
  web/src/features/signal-lab/api/useSignalPulseQueries.ts                            [MODIFY add useTargetPosts]
  web/src/shared/query/queryKeys.ts                                                   [MODIFY new key]
  web/src/features/signal-lab/model/pulseDetail.ts                                    [MODIFY signature + buildEvidence]
  web/src/features/signal-lab/ui/PulseDetail/PulseDetailView.tsx                      [MODIFY pass corpus + citedSet]
  web/src/features/signal-lab/ui/PulseDetailRoutePage.tsx                             [MODIFY swap data source]
  web/src/features/signal-lab/ui/SignalLabPage.tsx                                    [MODIFY swap inline data source]
  web/src/features/signal-lab/test/fixtures/titty-source-events.ts                    [MODIFY rename + add cited subset]
  web/src/features/signal-lab/test/fixtures/titty-pulse.ts                            [READ unchanged]
  web/src/features/signal-lab/test/fixtures/index.ts                                  [MODIFY re-exports]
  web/tests/unit/features/signal-lab/pulseDetail.test.ts                              [MODIFY new corpus assertions]
  web/tests/e2e/support/mockApi.ts                                                    [MODIFY mock target-posts]
```

---

## Task 1: Backend — add `author_followers`, `action`, `channel`, `author_name` to `timeline_rows`

**Files:**
- Modify: `src/parallax/domains/token_intel/repositories/token_target_repository.py`
- Test: `tests/integration/test_api_http.py`

**Background:** `timeline_rows` SELECT does not project these four columns from `events`. They're needed downstream by the Pulse view-model (`author_followers` for KOL/spam classification, `action` to display "回复/转推", `channel` for source identification, `author_name` for the displayName fallback we already declare in `EvidenceRow`).

- [ ] **Step 1: Write the failing integration test**

Append to `tests/integration/test_api_http.py`:

```python
def test_target_posts_returns_author_followers_and_action(setup_api_with_seeded_target_post):
    client, target = setup_api_with_seeded_target_post  # seeds 1 event with author_followers=12345 and action='reply'
    headers = {"Authorization": "Bearer secret"}

    response = client.get(
        "/api/target-posts",
        params={
            "target_type": target["target_type"],
            "target_id": target["target_id"],
            "window": "24h",
            "limit": 50,
        },
        headers=headers,
    )
    assert response.status_code == 200
    item = response.json()["data"]["items"][0]
    assert item["author_followers"] == 12345
    assert item["action"] == "reply"
    assert item["channel"] == "twitter_monitor_basic"
    assert item["author_name"] == "Test Author"
```

Define a fixture in the same file. Reuse the existing `build_test_api` / event-seeding helper that other tests in this module use (search `repos.evidence.upsert_event` or similar; mirror an existing test that inserts into `events` and `token_intent_resolutions`):

```python
@pytest.fixture
def setup_api_with_seeded_target_post(tmp_path, postgres_dsn):
    # Build API, then seed:
    #   events row with author_handle='kol_handle', author_followers=12345,
    #     author_name='Test Author', action='reply', channel='twitter_monitor_basic',
    #     received_at_ms = now,
    #   token_intent_resolutions row pointing event -> asset:solana:token:abc with EXACT status
    # Return (client, {"target_type": "Asset", "target_id": "asset:solana:token:abc"})
    ...
```

- [ ] **Step 2: Run the test and observe failure**

```bash
uv run pytest tests/integration/test_api_http.py::test_target_posts_returns_author_followers_and_action -v
```

Expected: FAIL — `KeyError: 'author_followers'` (or `assert None == 12345`).

- [ ] **Step 3: Extend the SELECT in `timeline_rows`**

In `src/parallax/domains/token_intel/repositories/token_target_repository.py`, update the `WITH matched AS (SELECT ...)` columns (lines 41-49). Replace the events-prefixed columns with this exact block (keep everything else identical):

```python
              events.event_id,
              events.tweet_id,
              events.canonical_url,
              events.author_handle,
              events.author_name,
              events.author_followers,
              events.action,
              events.channel,
              events.text,
              events.text_clean,
              events.reference_json,
              events.is_watched,
              events.received_at_ms,
```

Don't add a new JOIN — these are all columns of `events`, which is already joined in line 95 (`JOIN events ON events.event_id = tir.event_id`).

- [ ] **Step 4: Run the test to verify it passes**

```bash
uv run pytest tests/integration/test_api_http.py::test_target_posts_returns_author_followers_and_action -v
```

Expected: PASS (assuming Task 2 also runs — wait, no, Task 2 is the serializer change that wires these into the payload. So this step will still fail until Task 2 lands. Promote this step's expectation to "fails because payload doesn't carry author_followers yet" and complete Task 2 before the assertion can flip green).

- [ ] **Step 5: Commit**

```bash
git add src/parallax/domains/token_intel/repositories/token_target_repository.py
git commit -m "Include author_followers / action / channel / author_name in target timeline rows"
```

---

## Task 2: Backend — surface new fields in `token_target_post_payload`

**Files:**
- Modify: `src/parallax/domains/token_intel/read_models/token_target_post_serializer.py`

**Background:** The serializer ignores the four newly-projected columns. We add them to the payload `dict` so `/api/target-posts` returns them.

- [ ] **Step 1: Patch the serializer**

In `src/parallax/domains/token_intel/read_models/token_target_post_serializer.py`, locate the `payload = { ... }` dict (lines 30-58) and insert the four fields directly after the existing `"author_handle"` key:

```python
        "handle": row.get("author_handle"),
        "author_handle": row.get("author_handle"),
        "author_name": row.get("author_name"),
        "author_followers": (
            int(row["author_followers"]) if row.get("author_followers") is not None else None
        ),
        "action": row.get("action"),
        "channel": row.get("channel"),
        "text": text,
```

- [ ] **Step 2: Run the integration test from Task 1 to verify it now passes**

```bash
uv run pytest tests/integration/test_api_http.py::test_target_posts_returns_author_followers_and_action -v
```

Expected: PASS.

- [ ] **Step 3: Run the full target-posts test suite to catch regressions**

```bash
uv run pytest tests/unit/test_token_target_posts_service.py tests/integration/test_api_http.py -v -k target_posts
```

Expected: all pass.

- [ ] **Step 4: Commit**

```bash
git add src/parallax/domains/token_intel/read_models/token_target_post_serializer.py
git commit -m "Expose author_followers / action / channel / author_name on target-posts"
```

---

## Task 3: Backend — extend `TargetPostsItem` schema

**Files:**
- Modify: `src/parallax/app/surfaces/api/schemas.py`

**Background:** The response model needs to declare the new fields so OpenAPI typing reflects them. If the schema is `dict[str, Any]` / `LooseData`, no change is required and you can skip this task. Verify first.

- [ ] **Step 1: Inspect the current schema**

```bash
grep -n "TargetPostsItem\|TargetPostsData\|class TargetPosts" src/parallax/app/surfaces/api/schemas.py | head -10
```

If the response is typed as a structured Pydantic model with explicit fields, continue to Step 2. If it is `LooseData` or `dict[str, Any]`, mark this task complete and move on.

- [ ] **Step 2: Add the four optional fields to the item model**

Inside the relevant `class TargetPostsItem(BaseModel):` block, append:

```python
    author_name: str | None = None
    author_followers: int | None = None
    action: str | None = None
    channel: str | None = None
```

- [ ] **Step 3: Run integration tests**

```bash
uv run pytest tests/integration/test_api_http.py -v -k target_posts
```

Expected: all pass.

- [ ] **Step 4: Commit**

```bash
git add src/parallax/app/surfaces/api/schemas.py
git commit -m "Type new author_followers / action / channel fields on TargetPostsItem"
```

---

## Task 4: Frontend types — declare `TargetPostsItem` for the consumer

**Files:**
- Modify: `web/src/lib/types/frontend-contracts.ts`

**Background:** The frontend already has `TargetPostsData` somewhere (used by `useSearchInspect` or the existing target page). We extend / replace it with a stricter type covering the fields the Pulse view needs.

- [ ] **Step 1: Locate the existing type**

```bash
grep -n "TargetPostsItem\|TargetPostsData\|target-posts" web/src/lib/types/frontend-contracts.ts
```

- [ ] **Step 2: Add the type definition**

If the existing type is `Record<string, unknown>` / loose, replace it with this strict shape. Otherwise extend it:

```typescript
export type TargetPostsItem = {
  event_id: string;
  tweet_id: string | null;
  target_type: string;
  target_id: string;
  symbol: string | null;
  handle: string | null;
  author_handle: string | null;
  author_name: string | null;
  author_followers: number | null;
  action: string | null;
  channel: string | null;
  text: string | null;
  url: string | null;
  received_at_ms: number;
  is_watched: boolean;
};

export type TargetPostsData = {
  query: { target_type: string; target_id: string; window: string; scope: string };
  total_count: number;
  returned_count: number;
  has_more: boolean;
  next_cursor: string | null;
  items: TargetPostsItem[];
};
```

- [ ] **Step 3: Typecheck**

```bash
cd web && pnpm typecheck
```

Expected: clean (will surface any other consumer that was reading the old shape — fix those by referencing the new fields as optional or updating that consumer).

- [ ] **Step 4: Commit**

```bash
git add web/src/lib/types/frontend-contracts.ts
git commit -m "Type TargetPostsItem with author_followers / action / channel"
```

---

## Task 5: Frontend — `useTargetPosts` hook

**Files:**
- Modify: `web/src/features/signal-lab/api/useSignalPulseQueries.ts`
- Modify: `web/src/shared/query/queryKeys.ts`

**Background:** A new react-query hook that mirrors `useSourceEvents` but hits `/api/target-posts` with `window=24h&limit=200` for a given `(target_type, target_id)`. Disabled when target identifiers are missing (e.g., `research_only` route).

- [ ] **Step 1: Add the queryKey factory entry**

In `web/src/shared/query/queryKeys.ts`:

```typescript
pulseTargetPosts: (targetType: string | null, targetId: string | null, window: string) =>
  ["signal-lab", "pulse", "target-posts", targetType ?? "", targetId ?? "", window] as const,
```

- [ ] **Step 2: Implement the hook**

Append to `web/src/features/signal-lab/api/useSignalPulseQueries.ts`:

```typescript
import type { TargetPostsData, TargetPostsItem } from "@lib/types";

type TargetPostsArgs = {
  token: string;
  targetType: string | null;
  targetId: string | null;
  window?: string;
  limit?: number;
};

export function useTargetPosts({
  token,
  targetType,
  targetId,
  window = "24h",
  limit = 200,
}: TargetPostsArgs) {
  return useQuery({
    queryKey: queryKeys.pulseTargetPosts(targetType, targetId, window),
    enabled: Boolean(token && targetType && targetId),
    staleTime: 30_000,
    queryFn: async (): Promise<TargetPostsItem[]> => {
      const response = await getApi<TargetPostsData>("/api/target-posts", {
        token,
        params: {
          target_type: targetType ?? "",
          target_id: targetId ?? "",
          window,
          limit,
        },
      });
      return response.data.items;
    },
  });
}
```

- [ ] **Step 3: Write a unit test**

Append to `web/tests/unit/features/signal-lab/useSignalPulseQueries.test.tsx` (or co-locate; mirror the existing `useSourceEvents` test):

```typescript
describe("useTargetPosts", () => {
  it("calls /api/target-posts with window=24h", async () => {
    const spy = vi.spyOn(apiClient, "getApi").mockResolvedValue({
      ok: true,
      data: { query: {}, total_count: 0, returned_count: 0, has_more: false, next_cursor: null, items: [] },
    } as any);
    const { result } = renderHook(
      () =>
        useTargetPosts({
          token: "secret",
          targetType: "Asset",
          targetId: "asset:solana:token:abc",
        }),
      { wrapper: wrapper() },
    );
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(spy).toHaveBeenCalledWith(
      "/api/target-posts",
      expect.objectContaining({
        token: "secret",
        params: expect.objectContaining({
          target_type: "Asset",
          target_id: "asset:solana:token:abc",
          window: "24h",
          limit: 200,
        }),
      }),
    );
  });

  it("is disabled without target", () => {
    const spy = vi.spyOn(apiClient, "getApi");
    renderHook(
      () => useTargetPosts({ token: "secret", targetType: null, targetId: null }),
      { wrapper: wrapper() },
    );
    expect(spy).not.toHaveBeenCalled();
  });
});
```

- [ ] **Step 4: Run the test**

```bash
cd web && pnpm test -- --run tests/unit/features/signal-lab/useSignalPulseQueries.test.tsx
```

Expected: 4 tests passed (old 2 + new 2).

- [ ] **Step 5: Commit**

```bash
git add web/src/features/signal-lab/api/useSignalPulseQueries.ts web/src/shared/query/queryKeys.ts web/tests/unit/features/signal-lab/useSignalPulseQueries.test.tsx
git commit -m "Add useTargetPosts hook for 24h target-scoped event corpus"
```

---

## Task 6: Frontend — view-model accepts `(corpus, citedSet)`, refactor `buildEvidence`

**Files:**
- Modify: `web/src/features/signal-lab/model/pulseDetail.ts`
- Modify: `web/src/features/signal-lab/test/fixtures/titty-source-events.ts`
- Modify: `web/src/features/signal-lab/test/fixtures/index.ts`
- Modify: `web/tests/unit/features/signal-lab/pulseDetail.test.ts`

**Background:** Today `buildPulseDetailView` accepts `sourceEvents: SocialEventDetail[]` and treats anything in `item.decision.evidence_event_ids` as cited. We change the signature so the caller is explicit about which events are agent-cited:

```typescript
buildPulseDetailView({ item, events, citedIds, now })
```

`events` is the **full 24h corpus** (target-posts items adapted to `SocialEventDetail`), `citedIds` is `item.decision.evidence_event_ids ?? item.evidence_event_ids` (the existing source_event_ids array). All burst histogram / timeline / Evidence calculations now use `events`. The Evidence list uses `citedIds` only for the ★ marker + `★ Cited M` count.

Hard cut: the old `sourceEvents` prop name is replaced. No alias.

- [ ] **Step 1: Update the fixture**

Rename `titty-source-events.ts` exports for clarity. In `web/src/features/signal-lab/test/fixtures/titty-source-events.ts`, replace the current contents with:

```typescript
import type { SocialEventDetail } from "@lib/types";

// $TITTY 24h corpus (5 events captured in DB; in production this would be 50+).
// All five were also agent-cited; for tests that want a cited subset, use
// TITTY_CITED_EVENT_IDS.
export const tittyEventsCorpusFixture: SocialEventDetail[] = [
  { event_id: "gmgn:twitter_monitor_basic:aac4a193-4d22-44e9-be67-34f18f57c907",
    timestamp_ms: 1778723098000, source_provider: "gmgn", channel: "twitter_monitor_basic",
    action: "tweet", author_handle: "moontoklisting", author_name: "Moontok Listing Alert",
    author_followers: 48771, author_watched: false,
    text_clean: "月兔雷霆 - Moontok Xpress Troll Kitty ( $TITTY ) gTi4ZMMM2M7vQqZeetyQpWpjFr57zFZ7MCu4krypump LIQ: $27,373 | MC: $94,539 #altcoin #memecoins",
    canonical_url: "https://x.com/MoontokListing/status/2054739716084470106" },
  // ... (preserve existing 4 entries verbatim)
];

export const TITTY_CITED_EVENT_IDS: string[] = [
  "gmgn:twitter_monitor_basic:616d49c8-8186-4200-8c04-682d15c9d565",
  "gmgn:twitter_monitor_basic:6adbc0a4-3001-4d68-a1d5-7b942fe07214",
  "gmgn:twitter_monitor_basic:aac4a193-4d22-44e9-be67-34f18f57c907",
  "gmgn:twitter_monitor_basic:e85fe52a-048e-4539-b262-539a8ed43016",
  "gmgn:twitter_monitor_basic:ee31804e-92ba-4ba2-b38e-9d898d8b3a5a",
];

export const TITTY_NOW_MS = 1778726642689;
```

Update `web/src/features/signal-lab/test/fixtures/index.ts` to re-export the new names:

```typescript
export { tittyPulseFixture } from "./titty-pulse";
export {
  tittyEventsCorpusFixture,
  TITTY_CITED_EVENT_IDS,
  TITTY_NOW_MS,
} from "./titty-source-events";
```

Hard cut: do NOT keep the old `tittySourceEventsFixture` export.

- [ ] **Step 2: Update the view-model test to reflect the new signature**

In `web/tests/unit/features/signal-lab/pulseDetail.test.ts`, find the existing `buildPulseDetailView({ item, sourceEvents: ... })` call. Replace each invocation with:

```typescript
const view = buildPulseDetailView({
  item: tittyPulseFixture,
  events: tittyEventsCorpusFixture,
  citedIds: TITTY_CITED_EVENT_IDS,
  now: TITTY_NOW_MS,
});
```

Add a new test block right below the existing ones:

```typescript
describe("buildPulseDetailView · corpus larger than cited", () => {
  it("treats events outside citedIds as uncited rows but keeps them in the histogram", () => {
    const partial: typeof TITTY_CITED_EVENT_IDS = TITTY_CITED_EVENT_IDS.slice(0, 2);
    const view = buildPulseDetailView({
      item: tittyPulseFixture,
      events: tittyEventsCorpusFixture,
      citedIds: partial,
      now: TITTY_NOW_MS,
    });
    expect(view.evidence.totalCount).toBe(tittyEventsCorpusFixture.length);
    expect(view.evidence.citedCount).toBe(partial.length);
    const allRows = view.evidence.groups.flatMap((group) => group.rows);
    expect(allRows.filter((row) => row.cited)).toHaveLength(partial.length);
    expect(view.hero.burstHistogram.bins.reduce((sum, bin) => sum + bin.count, 0)).toBe(
      tittyEventsCorpusFixture.length,
    );
  });
});
```

- [ ] **Step 3: Run the tests to confirm they fail**

```bash
cd web && pnpm test -- --run tests/unit/features/signal-lab/pulseDetail.test.ts
```

Expected: FAIL — `sourceEvents` no longer recognised, or `citedIds` not consumed.

- [ ] **Step 4: Refactor `buildPulseDetailView` to the new signature**

In `web/src/features/signal-lab/model/pulseDetail.ts`, change `BuildPulseDetailViewInput` and `buildPulseDetailView`:

```typescript
export type BuildPulseDetailViewInput = {
  item: SignalPulseItem;
  events: SocialEventDetail[];
  citedIds: string[];
  now: number;
};

export function buildPulseDetailView({
  item,
  events,
  citedIds,
  now,
}: BuildPulseDetailViewInput): PulseDetailViewModel {
  const ordered = [...events].sort((a, b) => a.timestamp_ms - b.timestamp_ms);
  const citedSet = new Set(citedIds);
  const burst = buildBurst(ordered, now);
  const evidence = buildEvidence(item, ordered, citedSet, burst);
  const agent = buildAgent(item);
  const topAuthorHandle =
    evidence.concentration.segments[0]?.share && evidence.concentration.segments[0].share >= 0.3
      ? evidence.concentration.segments[0].handle
      : null;
  return {
    candidateId: item.candidate_id,
    hero: buildHero(item, burst, agent, now),
    timeline: { nodes: buildTimeline(item, burst, now) },
    families: buildFamilies(item, topAuthorHandle),
    market: buildMarket(item),
    evidence,
    agent,
  };
}
```

Update `buildEvidence`'s signature to receive the `citedSet` directly (today it derives it from `item.decision.evidence_event_ids`):

```typescript
function buildEvidence(
  item: SignalPulseItem,
  events: SocialEventDetail[],
  citedSet: Set<string>,
  burst: BurstHistogram,
): EvidenceView {
  // remove the existing citedSet computation block; reuse the passed-in Set.
  const authorCounts = new Map<string, number>();
  // ... (rest of the existing logic, unchanged)
}
```

Delete the inline `const citedSet = new Set(item.decision.evidence_event_ids?.length ? ... )` line — the caller is now authoritative.

- [ ] **Step 5: Run the tests to confirm they pass**

```bash
cd web && pnpm test -- --run tests/unit/features/signal-lab/pulseDetail.test.ts
```

Expected: all pass (including the new corpus-larger-than-cited test).

- [ ] **Step 6: Typecheck — surfaces the call sites we still need to migrate**

```bash
cd web && pnpm typecheck
```

Expected output: errors in `PulseDetailRoutePage.tsx`, `SignalLabPage.tsx`, and `PulseDetailView.tsx` because they still pass the old `sourceEvents` prop. **These errors are expected** — leave them for the next tasks to fix. Do not roll back.

- [ ] **Step 7: Commit**

```bash
git add web/src/features/signal-lab/model/pulseDetail.ts web/src/features/signal-lab/test/fixtures/titty-source-events.ts web/src/features/signal-lab/test/fixtures/index.ts web/tests/unit/features/signal-lab/pulseDetail.test.ts
git commit -m "Make buildPulseDetailView accept full corpus + explicit citedIds"
```

---

## Task 7: Frontend — `PulseDetailView` forwards `events` + `citedIds`

**Files:**
- Modify: `web/src/features/signal-lab/ui/PulseDetail/PulseDetailView.tsx`

**Background:** The orchestrator component currently accepts `sourceEvents: SocialEventDetail[]`. Rename the prop to `events`, add `citedIds: string[]`. Pure pass-through.

- [ ] **Step 1: Update the Props type and body**

In `web/src/features/signal-lab/ui/PulseDetail/PulseDetailView.tsx`, replace the `Props` declaration and the inside of the component:

```tsx
type Props = {
  item: SignalPulseItem;
  events: SocialEventDetail[];
  citedIds: string[];
  density?: DetailDensity;
  actions?: ReactNode;
  now?: number;
};

export function PulseDetailView({
  actions,
  citedIds,
  density = "full",
  events,
  item,
  now = Date.now(),
}: Props) {
  const view = useMemo(
    () => buildPulseDetailView({ item, events, citedIds, now }),
    [item, now, events, citedIds],
  );
  return <PulseDetailFrame actions={actions} density={density} view={view} />;
}
```

- [ ] **Step 2: Typecheck**

```bash
cd web && pnpm typecheck
```

Expected output: errors in `PulseDetailRoutePage.tsx` and `SignalLabPage.tsx` only. Other call sites (storybook / tests) should be clean.

- [ ] **Step 3: Commit**

```bash
git add web/src/features/signal-lab/ui/PulseDetail/PulseDetailView.tsx
git commit -m "Rename PulseDetailView props to events + citedIds"
```

---

## Task 8: Frontend — `PulseDetailRoutePage` switches to `useTargetPosts`

**Files:**
- Modify: `web/src/features/signal-lab/ui/PulseDetailRoutePage.tsx`

**Background:** The dedicated route page now fetches the 24h corpus when the pulse has a resolved target, and falls back to the existing `useSourceEvents` path when `decision.route === "research_only"` (no target). The cited subset is `item.decision.evidence_event_ids` (Judge's curated subset) when present, else `item.evidence_event_ids` (the candidate's seed set).

- [ ] **Step 1: Rewrite the route page**

Replace the body of `web/src/features/signal-lab/ui/PulseDetailRoutePage.tsx`:

```tsx
import { getAuthToken } from "@lib/api/client";
import type { SignalPulseItem, SocialEventDetail, TargetPostsItem } from "@lib/types";
import { signalPulseVenueActions } from "@lib/venue";
import { searchPath } from "@shared/routing/paths";
import { PanelSkeleton, RouteStatePanel } from "@shared/ui/RemoteState";
import { Link, useParams } from "react-router-dom";

import {
  useSignalPulseCandidate,
  useSourceEvents,
  useTargetPosts,
} from "../api/useSignalPulseQueries";

import { PulseDetailView } from "./PulseDetail";

export function PulseDetailRoutePage() {
  const { candidateId } = useParams<{ candidateId: string }>();
  const token = getAuthToken() ?? "";
  const pulse = useSignalPulseCandidate({ token, candidateId: candidateId ?? null });
  const item = pulse.data?.data ?? null;
  const targetType = item?.target_type ?? null;
  const targetId = item?.target_id ?? null;
  const hasTarget =
    Boolean(targetType && targetId) && item?.decision.route !== "research_only";
  const targetPosts = useTargetPosts({
    token,
    targetType: hasTarget ? targetType : null,
    targetId: hasTarget ? targetId : null,
    window: "24h",
    limit: 200,
  });
  const sourceEvents = useSourceEvents({
    token,
    ids: hasTarget ? [] : item?.source_event_ids ?? [],
  });

  if (pulse.isLoading) {
    return <PanelSkeleton label="loading pulse detail" />;
  }
  if (pulse.isError || !item) {
    return (
      <RouteStatePanel title="Pulse 不存在或已被屏蔽">
        检查链接，或回到 Signal Pulse 队列选择其他候选。
      </RouteStatePanel>
    );
  }

  const events = hasTarget
    ? (targetPosts.data ?? []).map(adaptTargetPost)
    : (sourceEvents.data ?? []);
  const citedIds = item.decision.evidence_event_ids?.length
    ? item.decision.evidence_event_ids
    : item.evidence_event_ids;

  return (
    <PulseDetailView
      actions={<PulseDetailActions item={item} />}
      density="full"
      events={events}
      citedIds={citedIds}
      item={item}
    />
  );
}

function adaptTargetPost(post: TargetPostsItem): SocialEventDetail {
  return {
    event_id: post.event_id,
    timestamp_ms: post.received_at_ms,
    source_provider: post.channel ?? "gmgn",
    channel: post.channel ?? "twitter_monitor_basic",
    action: post.action ?? "tweet",
    author_handle: post.author_handle ?? post.handle ?? null,
    author_name: post.author_name,
    author_followers: post.author_followers,
    author_watched: post.is_watched,
    text_clean: post.text,
    canonical_url: post.url,
  };
}

function PulseDetailActions({ item }: { item: SignalPulseItem }) {
  const subject = item.factor_snapshot.subject.symbol ?? item.symbol ?? item.subject_key;
  return (
    <>
      <Link to="/signal-lab">← 返回队列</Link>
      <Link to={searchPath({ q: subject ? `$${subject.replace(/^\$+/, "")}` : item.subject_key })}>
        搜索情报
      </Link>
      {signalPulseVenueActions(item).map((action) => (
        <a href={action.url} key={`${action.label}:${action.url}`} rel="noreferrer" target="_blank">
          {action.label}
        </a>
      ))}
    </>
  );
}
```

- [ ] **Step 2: Typecheck**

```bash
cd web && pnpm typecheck
```

Expected output: only `SignalLabPage.tsx` errors remain.

- [ ] **Step 3: Commit**

```bash
git add web/src/features/signal-lab/ui/PulseDetailRoutePage.tsx
git commit -m "Fetch 24h target corpus on dedicated pulse route"
```

---

## Task 9: Frontend — `SignalLabPage` inline switches to `useTargetPosts`

**Files:**
- Modify: `web/src/features/signal-lab/ui/SignalLabPage.tsx`

**Background:** Same switch as Task 8 for the queue-inline (compact) inspector. Inline density still uses full corpus + citedIds — the researcher's expectation doesn't change between layouts.

- [ ] **Step 1: Update the imports and inspector wiring**

In `web/src/features/signal-lab/ui/SignalLabPage.tsx`:

```tsx
import { useSourceEvents, useTargetPosts } from "../api/useSignalPulseQueries";
import type { SignalPulseItem, SocialEventDetail, TargetPostsItem } from "@lib/types";
```

Replace the existing `useSourceEvents` call and inspector render block:

```tsx
  const targetType = inlinePulseItem?.target_type ?? null;
  const targetId = inlinePulseItem?.target_id ?? null;
  const hasTarget =
    Boolean(targetType && targetId) &&
    inlinePulseItem?.decision.route !== "research_only";
  const targetPosts = useTargetPosts({
    token,
    targetType: hasTarget ? targetType : null,
    targetId: hasTarget ? targetId : null,
    window: "24h",
    limit: 200,
  });
  const sourceEvents = useSourceEvents({
    token,
    ids: hasTarget ? [] : inlinePulseItem?.source_event_ids ?? [],
  });
```

And the JSX:

```tsx
  const inlineEvents = hasTarget
    ? (targetPosts.data ?? []).map(adaptTargetPost)
    : (sourceEvents.data ?? []);
  const inlineCitedIds = inlinePulseItem
    ? inlinePulseItem.decision.evidence_event_ids?.length
      ? inlinePulseItem.decision.evidence_event_ids
      : inlinePulseItem.evidence_event_ids
    : [];
  // ...
  {inlinePulseItem ? (
    <PulseDetailView
      actions={<InlinePulseActions item={inlinePulseItem} />}
      density="compact"
      events={inlineEvents}
      citedIds={inlineCitedIds}
      item={inlinePulseItem}
    />
  ) : (
    <RemoteState.Empty title="No selected Signal Pulse case." />
  )}
```

Add the same `adaptTargetPost` helper as in Task 8. To avoid duplication, factor it into `web/src/features/signal-lab/api/useSignalPulseQueries.ts` once both call sites need it:

```typescript
export function adaptTargetPostToEvent(post: TargetPostsItem): SocialEventDetail {
  return { /* ... same body as Task 8 ... */ };
}
```

Update Task 8's helper to import this shared adapter rather than redeclaring locally.

- [ ] **Step 2: Typecheck**

```bash
cd web && pnpm typecheck
```

Expected: clean.

- [ ] **Step 3: Run all signal-lab tests**

```bash
cd web && pnpm test -- --run tests/unit/features/signal-lab tests/component/features/signal-lab
```

Expected: all pass.

- [ ] **Step 4: Commit**

```bash
git add web/src/features/signal-lab/ui/SignalLabPage.tsx web/src/features/signal-lab/api/useSignalPulseQueries.ts
git commit -m "Fetch 24h target corpus for inline pulse inspector"
```

---

## Task 10: E2E + mock — `pulse-detail.spec.ts` and `mockApi.ts` cover 24h corpus

**Files:**
- Modify: `web/tests/e2e/support/mockApi.ts`
- Verify: `web/tests/e2e/golden-paths/signal-lab-filters.spec.ts` (do not regress)

**Background:** Existing e2e mocks intercept `/api/signal-lab/pulse/...` and `/api/social-events/by-ids`. We add a `/api/target-posts` mock returning 15 fake TROLL-style events spanning 24h with 5 of them in the `citedIds` subset, plus extend the existing pulse mock so its `source_event_ids` matches exactly those 5.

- [ ] **Step 1: Inspect the existing mock for target-posts**

```bash
grep -n "target-posts\|signal-lab/pulse\|social-events" web/tests/e2e/support/mockApi.ts
```

- [ ] **Step 2: Add a target-posts mock**

Inside `installMockApi`, after the existing pulse / by-ids handlers, add:

```typescript
await page.route("**/api/target-posts*", async (route, request) => {
  const url = new URL(request.url());
  const targetId = url.searchParams.get("target_id");
  const fifteenEvents = buildMockTrollCorpus(15, targetId ?? "asset:solana:token:troll");
  await route.fulfill({
    contentType: "application/json",
    body: JSON.stringify({
      ok: true,
      data: {
        query: {
          target_type: url.searchParams.get("target_type"),
          target_id: targetId,
          window: url.searchParams.get("window"),
          scope: "all",
        },
        total_count: fifteenEvents.length,
        returned_count: fifteenEvents.length,
        has_more: false,
        next_cursor: null,
        items: fifteenEvents,
      },
    }),
  });
});
```

Add the helper at module scope:

```typescript
function buildMockTrollCorpus(n: number, targetId: string) {
  const nowMs = 1778726642689;
  return Array.from({ length: n }, (_, i) => ({
    event_id: `mock-event-${i}`,
    tweet_id: `${1000 + i}`,
    target_type: "Asset",
    target_id: targetId,
    symbol: "TROLL",
    handle: i % 3 === 0 ? "watched_kol" : `random${i}`,
    author_handle: i % 3 === 0 ? "watched_kol" : `random${i}`,
    author_name: i % 3 === 0 ? "Watched KOL" : `Random ${i}`,
    author_followers: i % 3 === 0 ? 50_000 : 500,
    action: "tweet",
    channel: "twitter_monitor_basic",
    text: `mock tweet ${i} about $TROLL`,
    url: `https://x.com/u/${1000 + i}`,
    received_at_ms: nowMs - ((n - 1 - i) * 90 * 60_000),  // 90-minute stride across 24h
    is_watched: i % 3 === 0,
  }));
}
```

In the existing pulse-by-id mock, set `source_event_ids` and `decision.evidence_event_ids` both to `["mock-event-2", "mock-event-5", "mock-event-8", "mock-event-11", "mock-event-14"]` so the e2e can assert "5 cited, 15 total".

- [ ] **Step 3: Update or add the e2e spec to assert the new shape**

Create `web/tests/e2e/golden-paths/pulse-detail.spec.ts` (if absent) with at least:

```typescript
test("pulse detail surfaces 24h corpus with cited subset", async ({ page }) => {
  await installMockApi(page);
  await page.goto("/signal-lab/pulse/pulse-mock-id");

  await expect(page.locator("section[aria-label='source events'] article")).toHaveCount(15);
  await expect(page.getByText(/全部 15/)).toBeVisible();
  await expect(page.getByText(/★ 已引用 5/)).toBeVisible();

  await page.getByRole("button", { name: /★ 已引用 5/ }).click();
  await expect(page.locator("section[aria-label='source events'] article")).toHaveCount(5);
});
```

- [ ] **Step 4: Run the e2e**

```bash
cd web && pnpm test:e2e -- pulse-detail.spec.ts
```

Expected: pass. If old tests reference the now-removed `5 source / 5 cited` numbers, they need updating in the same task.

- [ ] **Step 5: Commit**

```bash
git add web/tests/e2e/support/mockApi.ts web/tests/e2e/golden-paths/pulse-detail.spec.ts
git commit -m "E2E covers 24h pulse corpus vs cited subset"
```

---

## Task 11: Verification — Docker rebuild + Playwright against real $TROLL

**Files:**
- Verify only.

**Background:** Confirm the production bundle returns the expected corpus on the real DB. Use the TROLL pulse referenced in the spec.

- [ ] **Step 1: Backend full sweep**

```bash
uv run pytest tests/unit/test_signal_pulse_service.py tests/unit/test_token_target_posts_service.py tests/integration/test_api_http.py -v
```

Expected: all green.

- [ ] **Step 2: Frontend full sweep**

```bash
cd web && pnpm test -- --run && pnpm typecheck && pnpm lint
```

Expected: all green, 0 lint warnings.

- [ ] **Step 3: Rebuild Docker image and recreate the app container**

```bash
GITHUB_TOKEN=$(gh auth token) docker compose build app
GITHUB_TOKEN=$(gh auth token) docker compose up -d --force-recreate app
until curl -s -o /dev/null -w "%{http_code}" http://localhost:8765/api/bootstrap | grep -q 200; do sleep 1; done
echo "ready"
```

- [ ] **Step 4: Live Playwright audit on $TROLL pulse**

Save the following as `/tmp/audit-troll.mjs` (run via `node /Users/qinghuan/Documents/code/parallax/web/audit-troll.mjs` after copying it inside `web/` because that's where Playwright is installed):

```javascript
import { chromium } from "playwright";
const PULSE = "pulse-958846897ef70564fa1ba0de83bd05d237f7d5af";
const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ viewport: { width: 1440, height: 1024 } });
await page.goto(`http://localhost:8765/signal-lab/pulse/${PULSE}`);
await page.waitForSelector("article[data-density]", { timeout: 12000 });
await page.waitForTimeout(2500);
await page.screenshot({ path: "/tmp/troll-prod.png", fullPage: true });
const dump = await page.evaluate(() => {
  const norm = (s) => (s ?? "").replace(/\s+/g, " ").trim();
  return {
    title: document.querySelector("h1")?.textContent,
    tabs: Array.from(document.querySelectorAll("section[aria-label='source events'] [class*='tabs'] button")).map((b) => norm(b.textContent)),
    rowCount: document.querySelectorAll("section[aria-label='source events'] article").length,
    citedRowCount: document.querySelectorAll("section[aria-label='source events'] article[data-cited='true']").length,
    distinctHandles: [...new Set(Array.from(document.querySelectorAll("section[aria-label='source events'] article strong, section[aria-label='source events'] article a[class*='authorLink']")).map((el) => norm(el.textContent)))],
    burstHasCount: document.querySelectorAll("[data-bar][data-has='true']").length,
    burstPeakCount: document.querySelectorAll("[data-bar][data-peak='true']").length,
  };
});
console.log(JSON.stringify(dump, null, 2));
await browser.close();
```

Run it:

```bash
cp /tmp/audit-troll.mjs /Users/qinghuan/Documents/code/parallax/web/audit-troll.mjs
cd /Users/qinghuan/Documents/code/parallax/web && node audit-troll.mjs
rm /Users/qinghuan/Documents/code/parallax/web/audit-troll.mjs
```

Expected dump (the numbers may differ as the DB grows but the shape must match):
- `rowCount` ≥ 30 (was 10)
- `citedRowCount` between 5–15 (was 10)
- `tabs` contains `全部 NN` and `★ 已引用 MM` where NN > MM
- `burstHasCount` ≥ 10 (was 1) — bars distributed across the 24h grid
- `distinctHandles.length` ≥ 10 (was 8)

Compare `/tmp/troll-prod.png` against `/tmp/pulse-prod-dedicated.png` from the prior audit. The Hero burst histogram should now show bars distributed across the 24h grid, not clustered at the right edge.

- [ ] **Step 5: Spec follow-up**

Update `docs/superpowers/specs/active/2026-05-14-pulse-detail-redesign-cn.md` §"公共契约要求" to add a paragraph documenting the dual source: `/api/social-events/by-ids` for research_only pulses, `/api/target-posts?window=24h` for resolved-target pulses.

```bash
git add docs/superpowers/specs/active/2026-05-14-pulse-detail-redesign-cn.md
git commit -m "Spec: dual evidence source for research_only vs resolved-target pulses"
```

- [ ] **Step 6: Final commit + handoff**

```bash
git log --oneline -10
```

Confirm the 9 task commits are present. Report back: rowCount before / after, citedCount before / after, burstHasCount before / after, plus the side-by-side screenshot diff.

---

## Self-Review

**Spec coverage:**
- Spec G6 ("Evidence list = 完整推文，分组规则按 timeline period") — ✅ now respects the 24h corpus, not the 1h window.
- Spec §"使用场景与 density" — ✅ both dedicated route (Task 8) and inline (Task 9) use the same data source.
- Spec G8 (abstain / research_only) — ✅ research_only branch still uses `useSourceEvents` (Task 8 step 1 explicit fallback).
- Spec §"公共契约要求" — ✅ Task 11 step 5 documents the dual source.

**Placeholder scan:** No `TBD`, `TODO`, or "add appropriate error handling" markers. The fixture body in Task 6 includes the first event verbatim and explicitly defers the other four to "preserve existing 4 entries verbatim" — the implementer must copy them from the prior fixture file. No other hand-waving.

**Type consistency:** `events: SocialEventDetail[]` and `citedIds: string[]` introduced in Task 6 are threaded through Task 7 (`PulseDetailView`), Task 8 (`PulseDetailRoutePage`), Task 9 (`SignalLabPage`). `TargetPostsItem` introduced in Task 4 is consumed only via `adaptTargetPostToEvent` (Task 9) and `useTargetPosts` (Task 5). No drift.

**Hard-cut discipline:**
- Renamed `tittySourceEventsFixture` → `tittyEventsCorpusFixture` (no alias).
- Renamed `sourceEvents` prop → `events` on `PulseDetailView` (no alias, no deprecation warning).
- `buildPulseDetailView` signature breaks in one commit (Task 6 ends typecheck-red; Tasks 7–9 close it). Acceptable because the surface area is small (3 call sites) and we do not ship between commits.

**Non-coupling guarantees still hold:**
- `PulseDetail/` components do not import `@tanstack/react-query` or `react-router-dom`. Only `PulseDetailRoutePage` and `SignalLabPage` (which already own data fetching) call the new hook.
- `buildPulseDetailView` remains a pure function with no side effects.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/active/2026-05-14-pulse-detail-24h-events-fix-plan-cn.md`.

Two execution options:

1. **Subagent-Driven (recommended)** — Fresh subagent per task with review between tasks. Use `superpowers:subagent-driven-development`.
2. **Inline Execution** — Sequential in current session with checkpoints. Use `superpowers:executing-plans`.

Which approach?
