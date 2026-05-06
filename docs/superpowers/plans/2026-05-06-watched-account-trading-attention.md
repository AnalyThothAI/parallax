# Watched Account Trading Attention Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace Signal Lab's harness lifecycle UI with a simpler watched-account trading attention surface.

**Architecture:** Add an on-demand `TradingAttentionService` that reads `events`, `social_event_extractions`, and token attribution facts directly, then exposes `/api/signal-lab/pulse`. Frontend Signal Lab consumes this new read model and removes lifecycle stage/horizon/snapshot/outcome/credit concepts from the product path.

**Tech Stack:** Python 3.13, FastAPI, PostgreSQL/Psycopg, React, TypeScript, TanStack Query, Vitest, pytest.

---

## File Structure

- Create `src/gmgn_twitter_intel/retrieval/trading_attention_service.py`  
  Builds `TradingAttentionItem` rows from watched-account events, semantic extraction rows, direct token attributions, and topic terms.

- Modify `src/gmgn_twitter_intel/api/http.py`  
  Adds `/api/signal-lab/pulse`; leaves harness endpoints for backend research but no longer treats them as Signal Lab product APIs.

- Create `tests/test_trading_attention_service.py`  
  Covers direct token, topic heat, market structure, risk alert, and low-signal classification.

- Modify `tests/test_api_http.py`  
  Covers the new authenticated pulse endpoint.

- Modify `web/src/api/types.ts`  
  Adds `TradingAttentionItem`, `TradingAttentionData`, summary and filter types.

- Rewrite `web/src/components/SignalLabPulse.tsx`  
  Renders trading attention rows instead of signal chains.

- Rewrite `web/src/components/SignalLabWorkbench.tsx`  
  Replaces lifecycle cards with Direct token / Topic heat / Ecosystem / Structure / Risk summary and filters.

- Rewrite `web/src/components/SignalLabInspector.tsx`  
  Replaces Trace/Snapshot/Outcome/Credit tabs with a single attention detail drawer.

- Modify `web/src/App.tsx`  
  Removes `/api/signal-lab/chains` queries from the Signal Lab product path and uses `/api/signal-lab/pulse` for Pulse and Workbench.

- Modify `web/src/store/useTraderStore.ts`  
  Replaces stage/horizon state with kind/source/search filters for trading attention.

- Create/modify frontend tests around `SignalLabPulse` and `App`.

---

## Task 1: Backend TradingAttentionService

**Files:**
- Create: `src/gmgn_twitter_intel/retrieval/trading_attention_service.py`
- Test: `tests/test_trading_attention_service.py`

- [ ] **Step 1: Write failing tests**

Add tests that create events, optional social extraction rows, token attributions, then assert item kind:

```python
def test_trading_attention_classifies_direct_token_event(tmp_path):
    service = TradingAttentionService(evidence=evidence, signals=signals, tokens=tokens)
    data = service.pulse(window="1h", scope="all", limit=10, now_ms=11_000)
    assert data["items"][0]["kind"] == "direct_token"
    assert data["items"][0]["linked_tokens"][0]["token_id"].startswith("token:")
```

Also include:

```python
def test_trading_attention_keeps_keyword_as_topic_without_tokenizing(tmp_path):
    assert data["items"][0]["kind"] == "topic_heat"
    assert data["items"][0]["linked_tokens"] == []
    assert data["items"][0]["linked_topics"][0]["label"] == "Grok"
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```bash
uv run pytest tests/test_trading_attention_service.py -q
```

Expected: import error for `TradingAttentionService`.

- [ ] **Step 3: Implement service**

Implement:

```python
WINDOW_MS = {"5m": 300_000, "1h": 3_600_000, "4h": 14_400_000, "24h": 86_400_000}

class TradingAttentionService:
    def __init__(self, *, evidence, signals, tokens):
        self.evidence = evidence
        self.signals = signals
        self.tokens = tokens

    def pulse(...):
        events = self._events(...)
        social = self._social_by_event(...)
        tokens = self._token_links_by_event(...)
        alerts = self._alerts_by_event(...)
        items = [self._item(event, social.get(event_id), tokens.get(event_id, []), alerts.get(event_id, [])) ...]
        items = filter/sort/paginate
        return {"query": ..., "summary": ..., "items": ..., "returned_count": ..., "has_more": ..., "next_cursor": ...}
```

Classification:

```python
if token_links: "direct_token"
elif event_type == "market_structure_comment": "market_structure"
elif event_type in {"exchange_risk", "regulation_comment"} or direction_hint == "risk_negative": "risk_alert"
elif event_type in {"ecosystem_boost", "product_mention"}: "ecosystem_signal"
elif topics: "topic_heat"
else: "low_signal"
```

- [ ] **Step 4: Run tests and verify pass**

Run:

```bash
uv run pytest tests/test_trading_attention_service.py -q
```

Expected: all pass.

---

## Task 2: API Endpoint

**Files:**
- Modify: `src/gmgn_twitter_intel/api/http.py`
- Modify: `tests/test_api_http.py`

- [ ] **Step 1: Write failing API test**

Add:

```python
def test_api_exposes_trading_attention_pulse_without_harness_chains(tmp_path):
    response = client.get("/api/signal-lab/pulse?window=1h&scope=all&limit=10", headers=headers)
    assert response.status_code == 200
    assert response.json()["data"]["items"][0]["kind"] == "direct_token"
```

- [ ] **Step 2: Run and verify failure**

Run:

```bash
uv run pytest tests/test_api_http.py::test_api_exposes_trading_attention_pulse_without_harness_chains -q
```

Expected: 404.

- [ ] **Step 3: Add route**

In `api/http.py`, import and call:

```python
from ..retrieval.trading_attention_service import TradingAttentionService

@router.get("/signal-lab/pulse")
async def signal_lab_pulse(...):
    runtime = _authenticated_runtime(request)
    with runtime.repositories() as repos:
        data = TradingAttentionService(
            evidence=repos.evidence,
            signals=repos.signals,
            tokens=repos.tokens,
        ).pulse(...)
    return _json({"ok": True, "data": data})
```

- [ ] **Step 4: Run API test**

Run:

```bash
uv run pytest tests/test_api_http.py::test_api_exposes_trading_attention_pulse_without_harness_chains -q
```

Expected: pass.

---

## Task 3: Frontend Types And Components

**Files:**
- Modify: `web/src/api/types.ts`
- Rewrite: `web/src/components/SignalLabPulse.tsx`
- Rewrite: `web/src/components/SignalLabWorkbench.tsx`
- Rewrite: `web/src/components/SignalLabInspector.tsx`
- Modify: `web/src/components/SignalLabPulse.test.tsx`

- [ ] **Step 1: Write failing component test**

Assert Pulse renders kind labels and never lifecycle labels:

```tsx
expect(screen.getByText("Direct token")).toBeInTheDocument();
expect(screen.queryByText("FROZEN")).not.toBeInTheDocument();
expect(screen.queryByText("NO TRADE")).not.toBeInTheDocument();
```

- [ ] **Step 2: Run and verify failure**

Run:

```bash
npm test -- --run src/components/SignalLabPulse.test.tsx
```

Expected: type/component failures.

- [ ] **Step 3: Add types**

Add:

```ts
export type TradingAttentionKind = "direct_token" | "topic_heat" | "ecosystem_signal" | "market_structure" | "risk_alert" | "low_signal";
export type TradingAttentionPriority = "hot" | "watch" | "context" | "muted";
export type TradingAttentionItem = { ... };
export type TradingAttentionData = { query: ..., summary: ..., items: TradingAttentionItem[], ... };
```

- [ ] **Step 4: Rewrite components**

`SignalLabPulse` and `SignalLabWorkbench` take `TradingAttentionData`. `SignalLabInspector` takes `TradingAttentionItem`.

- [ ] **Step 5: Run component tests**

Run:

```bash
npm test -- --run src/components/SignalLabPulse.test.tsx
```

Expected: pass.

---

## Task 4: App Integration

**Files:**
- Modify: `web/src/App.tsx`
- Modify: `web/src/store/useTraderStore.ts`
- Modify: `web/src/App.test.tsx`

- [ ] **Step 1: Write failing App test**

Replace old expectation:

```tsx
expect(mockedGetApi.mock.calls.some(([path]) => path === "/api/signal-lab/pulse")).toBe(true);
expect(mockedGetApi.mock.calls.some(([path]) => path === "/api/signal-lab/chains")).toBe(false);
```

- [ ] **Step 2: Run and verify failure**

Run:

```bash
npm test -- --run src/App.test.tsx
```

Expected: App still calls chains.

- [ ] **Step 3: Replace App state and queries**

Remove product-path usage of:

```text
signalLabStage
signalLabHorizon
signalLabInspectorTab
SignalLabChain selected object
```

Use:

```text
signalLabKind
signalLabHandle
signalLabSearch
TradingAttentionItem selected object
```

- [ ] **Step 4: Run frontend tests/build**

Run:

```bash
npm test -- --run src/App.test.tsx src/components/SignalLabPulse.test.tsx
npm run build
```

Expected: pass.

---

## Task 5: Verification

**Files:** all changed files

- [ ] **Step 1: Python scoped checks**

Run:

```bash
uv run pytest tests/test_trading_attention_service.py tests/test_api_http.py -q
uv run ruff check src/gmgn_twitter_intel/retrieval/trading_attention_service.py src/gmgn_twitter_intel/api/http.py tests/test_trading_attention_service.py tests/test_api_http.py
uv run python -m compileall src tests
```

- [ ] **Step 2: Frontend checks**

Run:

```bash
npm test -- --run src/components/SignalLabPulse.test.tsx src/App.test.tsx
npm run build
```

- [ ] **Step 3: Live local check**

Run:

```bash
docker compose up -d --build
curl -fsS http://127.0.0.1:8765/healthz
curl -fsS "http://127.0.0.1:8765/api/signal-lab/pulse?token=$TOKEN&window=24h&scope=all&limit=20"
```

Expected:

```text
No lifecycle labels in Signal Lab UI.
Pulse data returns trading attention items or a real empty state.
```

