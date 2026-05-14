# Pulse Detail Page Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace `SignalLabInspector` with a new researcher-facing `PulseDetailView` that surfaces Analyst → Critic → Judge agent reasoning, gate-vs-agent disagreement, and full source-event content, used both by the dedicated `/signal-lab/pulse/<id>` route (full mode) and the queue right-pane inline view (compact mode).

**Architecture:** Backend extends the `/api/signal-lab/pulse/{id}` payload with a `stages` projection from `pulse_agent_run_steps`, and adds a new `/api/social-events/by-ids` batch endpoint. Frontend builds a pure view-model (`buildPulseDetailView`) from `(SignalPulseItem, SocialEventDetail[], now)`, then renders 6 leaf components (`PulseHero / PulseTimeline / PulseFactorFamilies / PulseMarketContext / PulseEvidenceList / PulseAgentRail`) inside `PulseDetailView`. Route topology is flattened so the dedicated route exits the queue 2-column layout. Hard cut — `SignalLabInspector`, `pulseCase.ts`, and `signal-pulse-*` CSS are deleted in the same PR. No coupling: components import zero routing / data-fetching code; CSS uses `*.module.css`, never globals.

**Tech Stack:**
- Backend: Python 3, FastAPI, psycopg, pytest. New code in `src/gmgn_twitter_intel/domains/pulse_lab/read_models/` and `src/gmgn_twitter_intel/app/surfaces/api/http.py`.
- Frontend: React 18, TypeScript, Vite, vitest, @testing-library/react, CSS modules, react-router-dom, @tanstack/react-query. New code in `web/src/features/signal-lab/ui/PulseDetail/`, `web/src/features/signal-lab/model/`, `web/src/features/signal-lab/api/`.
- E2E: Playwright (`web/e2e/golden-paths/`).
- Fixture: real `$TITTY` pulse (`pulse-fa2a12fedd9332271732110ed8bd7b1b49065282`) loaded from production DB.

**Spec:** `docs/superpowers/specs/active/2026-05-14-pulse-detail-redesign-cn.md`

**Commands cheat-sheet:**
- Backend test: `uv run pytest tests/path/test.py::test_name -v`
- Frontend unit test: `cd web && pnpm test -- --run path/to.test.ts`
- Frontend typecheck: `cd web && pnpm typecheck`
- Frontend lint: `cd web && pnpm lint`
- Frontend e2e: `cd web && pnpm test:e2e -- pulse-detail.spec.ts`
- DB shell: `docker exec gmgn-twitter-intel-postgres-1 psql -U gmgn_app -d gmgn_twitter_intel`

**File Structure (created or modified):**

```
Backend
  src/gmgn_twitter_intel/domains/pulse_lab/read_models/signal_pulse_service.py   [MODIFY]
  src/gmgn_twitter_intel/app/surfaces/api/http.py                                [MODIFY]
  src/gmgn_twitter_intel/app/surfaces/api/schemas.py                             [MODIFY]
  src/gmgn_twitter_intel/domains/evidence/repositories/evidence_repository.py    [REUSE events_by_ids]
  tests/unit/test_signal_pulse_service.py                                        [MODIFY]
  tests/integration/test_api_http.py                                             [MODIFY]

Frontend
  web/src/lib/format.ts                                                          [MODIFY add utc helpers]
  web/src/lib/format.test.ts                                                     [MODIFY]
  web/src/lib/types/frontend-contracts.ts                                        [MODIFY add stages + SocialEventDetail]
  web/src/features/signal-lab/api/useSignalPulseQueries.ts                       [MODIFY type, add useSourceEvents]
  web/src/features/signal-lab/model/pulseDetail.ts                               [CREATE pure view-model builder]
  web/src/features/signal-lab/model/pulseDetail.test.ts                          [CREATE]
  web/src/features/signal-lab/ui/PulseDetail/PulseDetailView.tsx                 [CREATE orchestrator]
  web/src/features/signal-lab/ui/PulseDetail/PulseDetailView.module.css          [CREATE]
  web/src/features/signal-lab/ui/PulseDetail/PulseDetailView.test.tsx            [CREATE integration]
  web/src/features/signal-lab/ui/PulseDetail/PulseHero.tsx                       [CREATE]
  web/src/features/signal-lab/ui/PulseDetail/PulseHero.module.css                [CREATE]
  web/src/features/signal-lab/ui/PulseDetail/PulseHero.test.tsx                  [CREATE]
  web/src/features/signal-lab/ui/PulseDetail/PulseTimeline.tsx                   [CREATE]
  web/src/features/signal-lab/ui/PulseDetail/PulseTimeline.module.css            [CREATE]
  web/src/features/signal-lab/ui/PulseDetail/PulseTimeline.test.tsx              [CREATE]
  web/src/features/signal-lab/ui/PulseDetail/PulseFactorFamilies.tsx             [CREATE]
  web/src/features/signal-lab/ui/PulseDetail/PulseFactorFamilies.module.css      [CREATE]
  web/src/features/signal-lab/ui/PulseDetail/PulseFactorFamilies.test.tsx        [CREATE]
  web/src/features/signal-lab/ui/PulseDetail/PulseMarketContext.tsx              [CREATE]
  web/src/features/signal-lab/ui/PulseDetail/PulseMarketContext.module.css       [CREATE]
  web/src/features/signal-lab/ui/PulseDetail/PulseMarketContext.test.tsx         [CREATE]
  web/src/features/signal-lab/ui/PulseDetail/PulseEvidenceList.tsx               [CREATE]
  web/src/features/signal-lab/ui/PulseDetail/PulseEvidenceList.module.css        [CREATE]
  web/src/features/signal-lab/ui/PulseDetail/PulseEvidenceList.test.tsx          [CREATE]
  web/src/features/signal-lab/ui/PulseDetail/PulseAgentRail.tsx                  [CREATE]
  web/src/features/signal-lab/ui/PulseDetail/PulseAgentRail.module.css           [CREATE]
  web/src/features/signal-lab/ui/PulseDetail/PulseAgentRail.test.tsx             [CREATE]
  web/src/features/signal-lab/ui/PulseDetail/index.ts                            [CREATE]
  web/src/features/signal-lab/test/fixtures/titty-pulse.ts                       [CREATE fixture]
  web/src/features/signal-lab/test/fixtures/titty-source-events.ts               [CREATE fixture]
  web/src/features/signal-lab/index.ts                                           [MODIFY remove old export]
  web/src/features/signal-lab/ui/SignalLabInspector.tsx                          [DELETE]
  web/src/features/signal-lab/ui/SignalLabInspector.test.tsx                     [DELETE]
  web/src/features/signal-lab/ui/SignalLabPulse.tsx                              [DELETE if unreferenced]
  web/src/features/signal-lab/ui/PulseDetailPage.tsx                             [DELETE moved into new route]
  web/src/features/signal-lab/model/pulseCase.ts                                 [DELETE]
  web/src/features/signal-lab/ui/signalLab.module.css                            [MODIFY strip .signal-pulse-*]
  web/src/features/signal-lab/ui/SignalLabPage.tsx                               [MODIFY remove isPulseRoute branch + density wire]
  web/src/routes/AppRoutes.tsx                                                   [MODIFY hoist /signal-lab/pulse/:id]
  web/src/routes/signal-lab.pulse.route.tsx                                      [MODIFY render PulseDetailRoute layout]
  web/e2e/golden-paths/pulse-detail.spec.ts                                      [CREATE]
  web/e2e/support/mockApi.ts                                                     [MODIFY add stages + by-ids mocks]
```

---

## Task 1: Backend — Extend pulse-by-id payload with `stages`

**Files:**
- Modify: `src/gmgn_twitter_intel/domains/pulse_lab/read_models/signal_pulse_service.py`
- Test: `tests/unit/test_signal_pulse_service.py`

**Background:** `SignalPulseService.candidate(candidate_id)` projects a single row via `pulse_item_from_row`. We add an optional `stages` block keyed by `analyst / critic / judge / research_only_gate`, populated from `repos.pulse.list_agent_run_steps(agent_run_id)`. List endpoint is untouched (perf).

- [ ] **Step 1: Write the failing test**

Add to `tests/unit/test_signal_pulse_service.py`:

```python
def test_candidate_includes_stages_from_run_steps() -> None:
    repository = FakePulseRepository()
    repository.candidate_rows["pulse-1"] = _candidate_row_with_run("pulse-1", run_id="run-1")
    repository.agent_run_steps["run-1"] = [
        {
            "stage": "analyst",
            "route": "meme",
            "status": "ok",
            "model": "qwen3.6",
            "started_at_ms": 100,
            "finished_at_ms": 200,
            "latency_ms": 100,
            "attempt_index": 0,
            "response_json": {"confidence": 0.82, "recommendation": "trade_candidate"},
        },
        {
            "stage": "critic",
            "route": "meme",
            "status": "ok",
            "model": "qwen3.6",
            "started_at_ms": 200,
            "finished_at_ms": 350,
            "latency_ms": 150,
            "attempt_index": 0,
            "response_json": {"confidence_ceiling": 0.45, "should_abstain": False},
        },
        {
            "stage": "judge",
            "route": "meme",
            "status": "ok",
            "model": "qwen3.6",
            "started_at_ms": 350,
            "finished_at_ms": 500,
            "latency_ms": 150,
            "attempt_index": 0,
            "response_json": {"confidence": 0.35, "recommendation": "trade_candidate"},
        },
    ]

    service = SignalPulseService(pulse=repository)
    item = service.candidate(candidate_id="pulse-1")

    assert item is not None
    stages = item["stages"]
    assert stages["analyst"]["response"]["confidence"] == 0.82
    assert stages["analyst"]["latency_ms"] == 100
    assert stages["critic"]["response"]["confidence_ceiling"] == 0.45
    assert stages["judge"]["response"]["confidence"] == 0.35
    assert stages.get("research_only_gate") is None


def test_candidate_stages_takes_latest_attempt_per_stage() -> None:
    repository = FakePulseRepository()
    repository.candidate_rows["pulse-2"] = _candidate_row_with_run("pulse-2", run_id="run-2")
    repository.agent_run_steps["run-2"] = [
        {
            "stage": "analyst", "route": "meme", "status": "failed", "model": "qwen3.6",
            "started_at_ms": 100, "finished_at_ms": 200, "latency_ms": 100,
            "attempt_index": 0, "response_json": None,
        },
        {
            "stage": "analyst", "route": "meme", "status": "ok", "model": "qwen3.6",
            "started_at_ms": 300, "finished_at_ms": 400, "latency_ms": 100,
            "attempt_index": 1, "response_json": {"confidence": 0.7},
        },
    ]

    item = SignalPulseService(pulse=repository).candidate(candidate_id="pulse-2")
    assert item["stages"]["analyst"]["status"] == "ok"
    assert item["stages"]["analyst"]["response"]["confidence"] == 0.7


def test_candidate_stages_absent_when_no_run() -> None:
    repository = FakePulseRepository()
    repository.candidate_rows["pulse-3"] = _candidate_row_with_run("pulse-3", run_id=None)
    item = SignalPulseService(pulse=repository).candidate(candidate_id="pulse-3")
    assert item["stages"] == {
        "analyst": None,
        "critic": None,
        "judge": None,
        "research_only_gate": None,
    }
```

And add this helper at the top of the test file alongside `FakePulseRepository`:

```python
def _candidate_row_with_run(candidate_id: str, *, run_id: str | None) -> dict[str, Any]:
    return {
        "candidate_id": candidate_id,
        "candidate_type": "token_target",
        "subject_key": "sub",
        "target_type": "Asset",
        "target_id": "asset:solana:token:x",
        "symbol": "X",
        "window": "1h",
        "scope": "all",
        "pulse_status": "trade_candidate",
        "verdict": "trade_candidate",
        "social_phase": "ignition",
        "narrative_type": "direct_token",
        "candidate_score": 80,
        "score_band": "high_conviction",
        "agent_run_id": run_id,
        "pulse_version": "v1",
        "gate_version": "v1",
        "prompt_version": "p1",
        "schema_version": "s1",
        "created_at_ms": 0,
        "updated_at_ms": 0,
        "decision_route": "meme",
        "decision_recommendation": "trade_candidate",
        "decision_confidence": 0.35,
        "decision_abstain_reason": None,
        "decision_stage_count": 3,
        "decision_json": {},
        "factor_snapshot_json": {
            "schema_version": "token_factor_snapshot_v3_social_attention",
            "subject": {"symbol": "X"},
        },
        "gate_json": {},
        "gate_reasons_json": [],
        "risk_reasons_json": [],
        "evidence_event_ids_json": [],
        "source_event_ids_json": [],
    }
```

Also extend `FakePulseRepository`'s `__init__` with `self.agent_run_steps: dict[str, list[dict]] = {}` and add methods:

```python
def candidate_by_id(self, candidate_id: str) -> dict[str, Any] | None:
    return self.candidate_rows.get(candidate_id)

def list_agent_run_steps(self, run_id: str) -> list[dict[str, Any]]:
    return list(self.agent_run_steps.get(run_id, []))
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
uv run pytest tests/unit/test_signal_pulse_service.py::test_candidate_includes_stages_from_run_steps -v
```

Expected: FAIL — `KeyError: 'stages'` (or `assert "stages" in item`).

- [ ] **Step 3: Implement stages projection in `signal_pulse_service.py`**

In `src/gmgn_twitter_intel/domains/pulse_lab/read_models/signal_pulse_service.py`, change the `candidate` method:

```python
def candidate(self, *, candidate_id: str) -> dict[str, Any] | None:
    row = self.pulse_repository.candidate_by_id(candidate_id)
    if row is None:
        return None
    if not _is_displayable(row):
        return None
    item = pulse_item_from_row(row)
    item["stages"] = self._stages_for(row.get("agent_run_id"))
    return item

def _stages_for(self, run_id: Any) -> dict[str, Any]:
    empty = {"analyst": None, "critic": None, "judge": None, "research_only_gate": None}
    if not run_id:
        return empty
    try:
        steps = self.pulse_repository.list_agent_run_steps(str(run_id))
    except Exception:
        return empty
    by_stage: dict[str, dict[str, Any]] = {}
    for step in steps:
        stage = step.get("stage")
        if stage not in empty:
            continue
        prior = by_stage.get(stage)
        if prior is None or _is_better_step(step, prior):
            by_stage[stage] = step
    result = dict(empty)
    for stage, step in by_stage.items():
        result[stage] = _stage_payload(step)
    return result


def _is_better_step(candidate: dict[str, Any], existing: dict[str, Any]) -> bool:
    candidate_ok = candidate.get("status") == "ok"
    existing_ok = existing.get("status") == "ok"
    if candidate_ok != existing_ok:
        return candidate_ok
    return int(candidate.get("attempt_index") or 0) >= int(existing.get("attempt_index") or 0)


def _stage_payload(step: dict[str, Any]) -> dict[str, Any]:
    return {
        "stage": step.get("stage"),
        "route": step.get("route"),
        "status": step.get("status"),
        "model": step.get("model"),
        "started_at_ms": step.get("started_at_ms"),
        "finished_at_ms": step.get("finished_at_ms"),
        "latency_ms": step.get("latency_ms"),
        "attempt_index": step.get("attempt_index"),
        "response": _dict(step.get("response_json")) or step.get("response_json"),
        "error": step.get("error"),
    }
```

(Place `_is_better_step` and `_stage_payload` alongside other module-private helpers near the bottom.)

- [ ] **Step 4: Run the test to verify it passes**

```bash
uv run pytest tests/unit/test_signal_pulse_service.py::test_candidate_includes_stages_from_run_steps tests/unit/test_signal_pulse_service.py::test_candidate_stages_takes_latest_attempt_per_stage tests/unit/test_signal_pulse_service.py::test_candidate_stages_absent_when_no_run -v
```

Expected: 3 passed.

- [ ] **Step 5: Run the full pulse-service test suite to verify no regression**

```bash
uv run pytest tests/unit/test_signal_pulse_service.py -v
```

Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add src/gmgn_twitter_intel/domains/pulse_lab/read_models/signal_pulse_service.py tests/unit/test_signal_pulse_service.py
git commit -m "Add stages projection to pulse_by_id payload"
```

---

## Task 2: Backend — Update API schema and add HTTP-level test for `stages`

**Files:**
- Modify: `src/gmgn_twitter_intel/app/surfaces/api/schemas.py`
- Test: `tests/integration/test_api_http.py`

**Background:** `api_schemas.SignalPulseItem` is the response model that pyantic enforces. We add `stages` as a typed nested dict so OpenAPI docs reflect it, then add a TestClient integration test that hits `/api/signal-lab/pulse/{id}`.

- [ ] **Step 1: Inspect current schema for `SignalPulseItem`**

```bash
grep -n "SignalPulseItem\|class SignalPulse" src/gmgn_twitter_intel/app/surfaces/api/schemas.py | head -20
```

- [ ] **Step 2: Extend the schema**

In `src/gmgn_twitter_intel/app/surfaces/api/schemas.py`, locate `class SignalPulseItem(BaseModel)` (or the dict-typed equivalent) and add — alongside the existing fields:

```python
class SignalPulseStagePayload(BaseModel):
    stage: str | None = None
    route: str | None = None
    status: str | None = None
    model: str | None = None
    started_at_ms: int | None = None
    finished_at_ms: int | None = None
    latency_ms: int | None = None
    attempt_index: int | None = None
    response: dict[str, Any] | None = None
    error: str | None = None


class SignalPulseStages(BaseModel):
    analyst: SignalPulseStagePayload | None = None
    critic: SignalPulseStagePayload | None = None
    judge: SignalPulseStagePayload | None = None
    research_only_gate: SignalPulseStagePayload | None = None
```

Then in the existing `SignalPulseItem` model, add:

```python
    stages: SignalPulseStages | None = None
```

If the existing model uses a permissive `dict[str, Any]` shape rather than a strict class, this addition still validates because `SignalPulseStages` accepts a dict.

- [ ] **Step 3: Write the failing integration test**

Append to `tests/integration/test_api_http.py`:

```python
def test_signal_lab_pulse_by_id_returns_stages(setup_api_with_seeded_pulse):
    client, candidate_id = setup_api_with_seeded_pulse
    headers = {"Authorization": "Bearer secret"}

    response = client.get(f"/api/signal-lab/pulse/{candidate_id}", headers=headers)

    assert response.status_code == 200
    body = response.json()
    stages = body["data"]["stages"]
    assert set(stages.keys()) == {"analyst", "critic", "judge", "research_only_gate"}
    assert stages["analyst"]["status"] == "ok"
    assert stages["analyst"]["response"]["confidence"] == 0.82
    assert stages["judge"]["response"]["confidence"] == 0.35
```

`setup_api_with_seeded_pulse` is a new fixture you define in the same file:

```python
@pytest.fixture
def setup_api_with_seeded_pulse(tmp_path, postgres_dsn):
    # Reuse the helper that already builds the API + seeded postgres in this module.
    # Search for `build_test_api(` or `seed_pulse_candidate(` for the existing helpers
    # used by other tests in this file, and wire one minimal pulse with three run_steps.
    ...
```

If `tests/integration/test_api_http.py` already uses a `build_test_api` helper, write the fixture using the same setup. Mirror an existing test that seeds a pulse_candidate (search by `pulse_candidates`).

- [ ] **Step 4: Run the new test, observe it fails (or seed-helper missing)**

```bash
uv run pytest tests/integration/test_api_http.py::test_signal_lab_pulse_by_id_returns_stages -v
```

Expected: FAIL — until both schema and any missing seed helpers are wired.

- [ ] **Step 5: Make the seed helper concrete**

Inside the new fixture, seed via `repos.pulse.upsert_candidate(...)` and `repos.pulse.upsert_agent_run_steps(...)` (or whatever real method names the repository exposes — search `def upsert` in `pulse_repository.py`). Use minimal data: candidate_id `pulse-stages-test`, run_id `run-stages-test`, three steps with response_json `{"confidence": 0.82}` / `{"confidence_ceiling": 0.45}` / `{"confidence": 0.35}`.

- [ ] **Step 6: Run the test to verify it passes**

```bash
uv run pytest tests/integration/test_api_http.py::test_signal_lab_pulse_by_id_returns_stages -v
```

Expected: PASS.

- [ ] **Step 7: Run the full integration suite for the file**

```bash
uv run pytest tests/integration/test_api_http.py -v
```

Expected: all green.

- [ ] **Step 8: Commit**

```bash
git add src/gmgn_twitter_intel/app/surfaces/api/schemas.py tests/integration/test_api_http.py
git commit -m "Expose pulse stages on /api/signal-lab/pulse/{id}"
```

---

## Task 3: Backend — New endpoint `/api/social-events/by-ids`

**Files:**
- Modify: `src/gmgn_twitter_intel/app/surfaces/api/http.py`
- Modify: `src/gmgn_twitter_intel/app/surfaces/api/schemas.py`
- Test: `tests/integration/test_api_http.py`

**Background:** The endpoint accepts a comma-separated `ids` query parameter, looks up events via `repos.evidence.events_by_ids(ids)`, joins each author handle against `account_profiles.watched_status` to populate `author_watched`, and returns a typed list. Hard cap 200 ids per request.

- [ ] **Step 1: Add the response schema**

In `src/gmgn_twitter_intel/app/surfaces/api/schemas.py`:

```python
class SocialEventDetail(BaseModel):
    event_id: str
    timestamp_ms: int
    source_provider: str
    channel: str
    action: str
    author_handle: str | None = None
    author_name: str | None = None
    author_followers: int | None = None
    author_watched: bool = False
    text_clean: str | None = None
    canonical_url: str | None = None


class SocialEventsByIdsData(BaseModel):
    events: list[SocialEventDetail] = Field(default_factory=list)
    not_found: list[str] = Field(default_factory=list)
```

- [ ] **Step 2: Write the failing integration test**

Append to `tests/integration/test_api_http.py`:

```python
def test_social_events_by_ids_returns_full_records(setup_api_with_seeded_events):
    client, ids = setup_api_with_seeded_events  # seeds 2 events: 1 watched author, 1 non-watched
    headers = {"Authorization": "Bearer secret"}

    response = client.get(
        "/api/social-events/by-ids",
        params={"ids": ",".join(ids)},
        headers=headers,
    )
    assert response.status_code == 200
    body = response.json()
    events = body["data"]["events"]
    assert {ev["event_id"] for ev in events} == set(ids)
    by_handle = {ev["author_handle"]: ev for ev in events}
    assert by_handle["watched_kol"]["author_watched"] is True
    assert by_handle["random_dude"]["author_watched"] is False


def test_social_events_by_ids_skips_missing(setup_api_with_seeded_events):
    client, ids = setup_api_with_seeded_events
    headers = {"Authorization": "Bearer secret"}

    response = client.get(
        "/api/social-events/by-ids",
        params={"ids": f"{ids[0]},nonexistent-id"},
        headers=headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert len(body["data"]["events"]) == 1
    assert body["data"]["not_found"] == ["nonexistent-id"]


def test_social_events_by_ids_rejects_too_many(setup_api_with_seeded_events):
    client, _ids = setup_api_with_seeded_events
    headers = {"Authorization": "Bearer secret"}
    huge = ",".join(f"id-{i}" for i in range(201))
    response = client.get("/api/social-events/by-ids", params={"ids": huge}, headers=headers)
    assert response.status_code == 400
    assert response.json()["error"] == "too_many_ids"


def test_social_events_by_ids_requires_ids(setup_api_with_seeded_events):
    client, _ids = setup_api_with_seeded_events
    headers = {"Authorization": "Bearer secret"}
    response = client.get("/api/social-events/by-ids", headers=headers)
    assert response.status_code == 400
    assert response.json()["error"] == "ids_required"
```

Define the fixture using the same setup helpers as Task 2:

```python
@pytest.fixture
def setup_api_with_seeded_events(tmp_path, postgres_dsn):
    # Build API, then insert into `account_profiles` (handle, watched_status='active' vs 'inactive')
    # and `events` (event_id, author_handle, timestamp_ms, source_provider, channel, action, text_clean).
    # Return (client, [event_id_1, event_id_2])
    ...
```

- [ ] **Step 3: Run the failing tests**

```bash
uv run pytest tests/integration/test_api_http.py::test_social_events_by_ids_returns_full_records tests/integration/test_api_http.py::test_social_events_by_ids_skips_missing tests/integration/test_api_http.py::test_social_events_by_ids_rejects_too_many tests/integration/test_api_http.py::test_social_events_by_ids_requires_ids -v
```

Expected: 404 / 4 FAILs (route not yet registered).

- [ ] **Step 4: Implement the endpoint**

In `src/gmgn_twitter_intel/app/surfaces/api/http.py`, add this route (near the other social-event routes, around line 459 `social-events`):

```python
@router.get(
    "/social-events/by-ids",
    response_model=api_schemas.ApiEnvelope[api_schemas.SocialEventsByIdsData],
)
async def social_events_by_ids(
    request: Request,
    ids: Annotated[str, Query()] = "",
) -> JSONResponse:
    runtime = _authenticated_runtime(request)
    raw = [token.strip() for token in (ids or "").split(",") if token.strip()]
    if not raw:
        return JSONResponse(
            {"ok": False, "error": "ids_required", "field": "ids"},
            status_code=400,
        )
    if len(raw) > 200:
        return JSONResponse(
            {"ok": False, "error": "too_many_ids", "field": "ids", "limit": 200},
            status_code=400,
        )
    with runtime.repositories() as repos:
        records = repos.evidence.events_by_ids(raw)
        handles = sorted(
            {
                str(event.get("author_handle"))
                for event in records.values()
                if event.get("author_handle")
            }
        )
        watched = _watched_handle_set(repos, handles)
        events_payload = [
            _social_event_detail(records[event_id], watched)
            for event_id in raw
            if event_id in records
        ]
        not_found = [event_id for event_id in raw if event_id not in records]
    return _json({"ok": True, "data": {"events": events_payload, "not_found": not_found}})
```

Helpers in the same module (near `_payload_for_event`):

```python
def _watched_handle_set(repos: Any, handles: list[str]) -> set[str]:
    if not handles:
        return set()
    try:
        profiles = repos.account_profiles.profiles_by_handles(handles)
    except Exception:
        return set()
    return {
        handle
        for handle, profile in profiles.items()
        if (profile or {}).get("watched_status") == "active"
    }


def _social_event_detail(event: dict[str, Any], watched: set[str]) -> dict[str, Any]:
    handle = event.get("author_handle")
    return {
        "event_id": str(event["event_id"]),
        "timestamp_ms": int(event.get("timestamp_ms") or 0),
        "source_provider": event.get("source_provider") or "",
        "channel": event.get("channel") or "",
        "action": event.get("action") or "",
        "author_handle": handle,
        "author_name": event.get("author_name"),
        "author_followers": (
            int(event["author_followers"]) if event.get("author_followers") is not None else None
        ),
        "author_watched": bool(handle and handle in watched),
        "text_clean": event.get("text_clean") or event.get("text") or event.get("text_raw"),
        "canonical_url": event.get("canonical_url"),
    }
```

- [ ] **Step 5: Add `profiles_by_handles` to account profiles repo if it doesn't exist**

Check first:

```bash
grep -n "profiles_by_handles\|def profiles_by\|watched_status" src/gmgn_twitter_intel/domains/account_profiles -r
```

If absent, add to the repository:

```python
def profiles_by_handles(self, handles: list[str]) -> dict[str, dict[str, Any]]:
    if not handles:
        return {}
    rows = self.conn.execute(
        "SELECT handle, watched_status FROM account_profiles WHERE handle = ANY(%s)",
        (list(handles),),
    ).fetchall()
    return {row["handle"]: dict(row) for row in rows}
```

Wire it onto `repos.account_profiles` if not already exposed.

- [ ] **Step 6: Run the tests to verify they pass**

```bash
uv run pytest tests/integration/test_api_http.py -k social_events_by_ids -v
```

Expected: 4 passed.

- [ ] **Step 7: Run the full HTTP test file**

```bash
uv run pytest tests/integration/test_api_http.py -v
```

Expected: all pass.

- [ ] **Step 8: Commit**

```bash
git add src/gmgn_twitter_intel/app/surfaces/api/http.py src/gmgn_twitter_intel/app/surfaces/api/schemas.py src/gmgn_twitter_intel/domains/account_profiles tests/integration/test_api_http.py
git commit -m "Add GET /api/social-events/by-ids batch endpoint"
```

---

## Task 4: Frontend — Time formatting helpers in `format.ts`

**Files:**
- Modify: `web/src/lib/format.ts`
- Test: `web/src/lib/format.test.ts`

**Background:** Spec G7 requires absolute UTC display for all point-in-time fields and relative duration in parens as副注. Add two pure helpers next to the existing `formatRelativeTime` so the rest of the feature has a single source of truth.

- [ ] **Step 1: Write the failing tests**

Append to `web/src/lib/format.test.ts`:

```typescript
import { formatUtcTimestamp, formatRelativeAge } from "./format";

describe("formatUtcTimestamp", () => {
  it("formats ms epoch as YYYY-MM-DD HH:mm UTC", () => {
    expect(formatUtcTimestamp(1778726642689)).toBe("2026-05-13 17:04 UTC");
  });

  it("returns - for null", () => {
    expect(formatUtcTimestamp(null)).toBe("-");
  });

  it("returns - for non-finite", () => {
    expect(formatUtcTimestamp(Number.NaN)).toBe("-");
  });

  it("optionally omits the UTC suffix", () => {
    expect(formatUtcTimestamp(1778726642689, { suffix: false })).toBe("2026-05-13 17:04");
  });
});

describe("formatRelativeAge", () => {
  const now = 1778726642689;

  it("returns '(Nm ago)' for past < 1h", () => {
    expect(formatRelativeAge(now - 119 * 60_000, now)).toBe("(119m ago)");
  });

  it("returns '(Nh ago)' for hours", () => {
    expect(formatRelativeAge(now - 2 * 3_600_000, now)).toBe("(2h ago)");
  });

  it("returns '(just now)' under 30s", () => {
    expect(formatRelativeAge(now - 10_000, now)).toBe("(just now)");
  });

  it("returns '(in Nm)' for future", () => {
    expect(formatRelativeAge(now + 4 * 60_000, now)).toBe("(in 4m)");
  });

  it("returns empty string for null", () => {
    expect(formatRelativeAge(null, now)).toBe("");
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd web && pnpm test -- --run src/lib/format.test.ts
```

Expected: FAIL — `formatUtcTimestamp is not a function`.

- [ ] **Step 3: Implement the helpers**

In `web/src/lib/format.ts`, append:

```typescript
type UtcFormatOptions = { suffix?: boolean };

export function formatUtcTimestamp(
  value: number | null | undefined,
  options: UtcFormatOptions = {},
): string {
  if (value === null || value === undefined || !Number.isFinite(value)) {
    return "-";
  }
  const date = new Date(value);
  const yyyy = date.getUTCFullYear();
  const mm = String(date.getUTCMonth() + 1).padStart(2, "0");
  const dd = String(date.getUTCDate()).padStart(2, "0");
  const hh = String(date.getUTCHours()).padStart(2, "0");
  const min = String(date.getUTCMinutes()).padStart(2, "0");
  const base = `${yyyy}-${mm}-${dd} ${hh}:${min}`;
  return options.suffix === false ? base : `${base} UTC`;
}

export function formatRelativeAge(
  value: number | null | undefined,
  now: number = Date.now(),
): string {
  if (value === null || value === undefined || !Number.isFinite(value)) {
    return "";
  }
  const delta = value - now;
  const abs = Math.abs(delta);
  if (abs < 30_000) {
    return "(just now)";
  }
  const inFuture = delta > 0;
  let unit: string;
  let amount: number;
  if (abs < 3_600_000) {
    unit = "m";
    amount = Math.round(abs / 60_000);
  } else if (abs < 86_400_000) {
    unit = "h";
    amount = Math.round(abs / 3_600_000);
  } else {
    unit = "d";
    amount = Math.round(abs / 86_400_000);
  }
  return inFuture ? `(in ${amount}${unit})` : `(${amount}${unit} ago)`;
}
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
cd web && pnpm test -- --run src/lib/format.test.ts
```

Expected: PASS (all `formatUtcTimestamp` + `formatRelativeAge` tests green).

- [ ] **Step 5: Typecheck**

```bash
cd web && pnpm typecheck
```

Expected: clean.

- [ ] **Step 6: Commit**

```bash
git add web/src/lib/format.ts web/src/lib/format.test.ts
git commit -m "Add formatUtcTimestamp and formatRelativeAge helpers"
```

---

## Task 5: Frontend — Type definitions for `stages` and `SocialEventDetail`

**Files:**
- Modify: `web/src/lib/types/frontend-contracts.ts`

**Background:** Spec requires `SignalPulseItem` to carry `stages` and that a new `SocialEventDetail` type be importable everywhere. Both are flat additions, no breaking change.

- [ ] **Step 1: Add the types**

In `web/src/lib/types/frontend-contracts.ts`, find the existing `SignalPulseItem` (line ~1156) and add `stages?: SignalPulseStages | null;` to it. Then add — directly above `SignalPulseItem` — the supporting types:

```typescript
export type SignalPulseStageName = "analyst" | "critic" | "judge" | "research_only_gate";

export type SignalPulseStagePayload = {
  stage: SignalPulseStageName | string | null;
  route: string | null;
  status: "ok" | "failed" | "timeout" | "skipped" | string | null;
  model: string | null;
  started_at_ms: number | null;
  finished_at_ms: number | null;
  latency_ms: number | null;
  attempt_index: number | null;
  response: Record<string, unknown> | null;
  error: string | null;
};

export type SignalPulseStages = {
  analyst: SignalPulseStagePayload | null;
  critic: SignalPulseStagePayload | null;
  judge: SignalPulseStagePayload | null;
  research_only_gate: SignalPulseStagePayload | null;
};
```

Then add below the `SignalPulseData` type:

```typescript
export type SocialEventDetail = {
  event_id: string;
  timestamp_ms: number;
  source_provider: string;
  channel: string;
  action: "tweet" | "quote" | "repost" | "reply" | string;
  author_handle: string | null;
  author_name: string | null;
  author_followers: number | null;
  author_watched: boolean;
  text_clean: string | null;
  canonical_url: string | null;
};

export type SocialEventsByIdsData = {
  events: SocialEventDetail[];
  not_found: string[];
};
```

- [ ] **Step 2: Typecheck — verifies no existing consumer breaks**

```bash
cd web && pnpm typecheck
```

Expected: clean. (`stages` is optional so callers that ignore it are unaffected.)

- [ ] **Step 3: Commit**

```bash
git add web/src/lib/types/frontend-contracts.ts
git commit -m "Type stages and SocialEventDetail contracts"
```

---

## Task 6: Frontend — `$TITTY` fixtures

**Files:**
- Create: `web/src/features/signal-lab/test/fixtures/titty-pulse.ts`
- Create: `web/src/features/signal-lab/test/fixtures/titty-source-events.ts`
- Create: `web/src/features/signal-lab/test/fixtures/index.ts`

**Background:** All downstream tests (view-model + each component + integration) need a single, faithful sample. We use the real `$TITTY` pulse (`pulse-fa2a12fedd9332271732110ed8bd7b1b49065282`) captured directly from production DB so what the test pins is what production renders.

- [ ] **Step 1: Capture the real pulse JSON from the DB**

Run this command and copy the output:

```bash
docker exec gmgn-twitter-intel-postgres-1 psql -U gmgn_app -d gmgn_twitter_intel -At -c "
  SELECT jsonb_pretty(
    jsonb_build_object(
      'candidate_id', candidate_id,
      'candidate_type', candidate_type,
      'subject_key', subject_key,
      'target_type', target_type,
      'target_id', target_id,
      'symbol', symbol,
      'window', \"window\",
      'scope', scope,
      'pulse_status', pulse_status,
      'verdict', verdict,
      'social_phase', social_phase,
      'narrative_type', narrative_type,
      'candidate_score', candidate_score,
      'score_band', score_band,
      'evidence_event_ids', evidence_event_ids_json,
      'source_event_ids', source_event_ids_json,
      'factor_snapshot', factor_snapshot_json,
      'decision', decision_json,
      'gate', gate_json,
      'agent_run_id', agent_run_id,
      'pulse_version', pulse_version,
      'gate_version', gate_version,
      'prompt_version', prompt_version,
      'schema_version', schema_version,
      'created_at_ms', created_at_ms,
      'updated_at_ms', updated_at_ms
    )
  )
  FROM pulse_candidates
  WHERE candidate_id = 'pulse-fa2a12fedd9332271732110ed8bd7b1b49065282';
"
```

Save the verbatim JSON output as part of step 2.

- [ ] **Step 2: Write `titty-pulse.ts`**

```typescript
import type { SignalPulseItem, SignalPulseStages } from "@lib/types";

const stages: SignalPulseStages = {
  analyst: {
    stage: "analyst",
    route: "meme",
    status: "ok",
    model: "qwen3.6",
    started_at_ms: 1778726642689 - 14702,
    finished_at_ms: 1778726642689 - 11000,
    latency_ms: 3704,
    attempt_index: 0,
    response: {
      route: "meme",
      confidence: 0.82,
      summary_zh:
        "TITTY 在 Solana 链上显示出显著的社会热度（得分91），特别是注意力意外惊喜和独立作者传播力较强。尽管语义催化剂数据缺失，但社交媒体层面的互动活跃度较高，且已突破10万美元市值门槛，流动性约3万美元，具备早期 meme 代币的投机潜力，建议作为交易候选关注。",
      recommendation: "trade_candidate",
      evidence: [
        "社会热度得分极高（91分），注意力意外惊喜指数为 1.79，显示近期关注度非正常爆发。",
        "社交传播得分 85 分，独立作者数 3 人，传播速度较快（第二作者响应时间约 283 秒）。",
        "市值约 11.4 万美元，流动性约 3.08 万美元，处于早期成长阶段。",
        "主要推文由 @moontoklisting 和 @cache100x 等 KOL 或营销账号发布，存在集中营销风险但推动了热度。",
        "24 小时交易量达 153 万美元，相对于市值而言换手率极高，表明市场参与度活跃。",
      ],
    },
    error: null,
  },
  critic: {
    stage: "critic",
    route: "meme",
    status: "ok",
    model: "qwen3.6",
    started_at_ms: 1778726642689 - 11000,
    finished_at_ms: 1778726642689 - 6122,
    latency_ms: 4876,
    attempt_index: 0,
    response: {
      route: "meme",
      should_abstain: false,
      confidence_ceiling: 0.45,
      weaknesses: [
        "Social propagation relies heavily on a single active account (@cache100x) which posts 3 out of 5 selected posts, indicating low organic spread despite the '3 independent authors' metric.",
        "Semantic catalyst data is entirely missing (score 0, confidence 0), meaning there is no qualitative understanding of the narrative or novelty driving the attention.",
        "The 'attention surprise' is statistically weak (1.79) based on a tiny baseline (6 samples), making the 'explosion' claim fragile.",
        "Volume (1.5M) is 13x Market Cap (114k), suggesting extreme speculative churn or bot activity rather than healthy demand.",
        "Holder count (968) relative to market cap implies a low average hold size, increasing vulnerability to coordinated dumps.",
      ],
      missing_fact_impacts: [
        "Liquidity depth analysis is missing: Without knowing the pair composition or slippage impact, the 30k liquidity figure is insufficient to assess exit risk for larger positions.",
        "Holder distribution data is absent: Cannot determine if the 968 holders are concentrated among the marketing accounts or truly distributed, which is critical for 'cohort quality' assessment.",
        "Smart contract ownership renunciation status is unknown: High risk of rug pull given the early stage and aggressive marketing.",
        "On-chain wallet tracking of the top 5 holders is missing: Cannot verify if the 'independent authors' are funding the volume or if the volume is self-generated by the same entities.",
      ],
    },
    error: null,
  },
  judge: {
    stage: "judge",
    route: "meme",
    status: "ok",
    model: "qwen3.6",
    started_at_ms: 1778726642689 - 6122,
    finished_at_ms: 1778726642689,
    latency_ms: 6122,
    attempt_index: 0,
    response: {
      route: "meme",
      confidence: 0.35,
      summary_zh:
        "TITTY 代币在 Solana 链上呈现极高的社交热度（得分91）和异常的注意力爆发，但数据质量存在严重缺陷。流动性仅3万美元，24小时交易量却高达153万美元（换手率极高），暗示强烈的投机或机器人交易行为。社交传播主要由单一营销账号主导，独立作者真实性存疑，且缺乏语义催化剂数据和持有者分布信息。虽然具备早期 meme 的高波动投机属性，但 Rug Pull 风险和流动性深度不足是主要障碍，仅适合高风险投机，不建议作为稳健标的。",
      abstain_reason: null,
      recommendation: "trade_candidate",
      residual_risks: [
        "流动性极浅（3万美元），大额交易滑点风险极高",
        "高度集中的营销推送可能导致价格瞬间崩盘",
        "智能合约未验证所有权弃置，存在 Rug Pull 风险",
        "交易量可能由做市机器人自买自卖制造，缺乏真实需求",
        "持有者结构不透明，无法排除巨鲸集中控盘",
      ],
      invalidation_conditions: [
        "流动性池规模急剧缩减超过 20%",
        "持有者数量在 1 小时内出现断崖式下跌超过 10%",
        "主要营销账号停止发声或社交媒体热度得分骤降至 50 以下",
      ],
      evidence_event_ids: [
        "gmgn:twitter_monitor_basic:616d49c8-8186-4200-8c04-682d15c9d565",
        "gmgn:twitter_monitor_basic:6adbc0a4-3001-4d68-a1d5-7b942fe07214",
        "gmgn:twitter_monitor_basic:aac4a193-4d22-44e9-be67-34f18f57c907",
        "gmgn:twitter_monitor_basic:e85fe52a-048e-4539-b262-539a8ed43016",
        "gmgn:twitter_monitor_basic:ee31804e-92ba-4ba2-b38e-9d898d8b3a5a",
      ],
    },
    error: null,
  },
  research_only_gate: null,
};

export const tittyPulseFixture: SignalPulseItem = {
  candidate_id: "pulse-fa2a12fedd9332271732110ed8bd7b1b49065282",
  candidate_type: "token_target",
  subject_key: "titty",
  target_type: "Asset",
  target_id: "asset:solana:token:gTi4ZMMM2M7vQqZeetyQpWpjFr57zFZ7MCu4krypump",
  symbol: "TITTY",
  window: "1h",
  scope: "all",
  pulse_status: "trade_candidate",
  verdict: "trade_candidate",
  social_phase: "ignition",
  narrative_type: "direct_token",
  candidate_score: 82,
  score_band: "high_conviction",
  evidence_event_ids: [
    "gmgn:twitter_monitor_basic:616d49c8-8186-4200-8c04-682d15c9d565",
    "gmgn:twitter_monitor_basic:6adbc0a4-3001-4d68-a1d5-7b942fe07214",
    "gmgn:twitter_monitor_basic:aac4a193-4d22-44e9-be67-34f18f57c907",
    "gmgn:twitter_monitor_basic:e85fe52a-048e-4539-b262-539a8ed43016",
    "gmgn:twitter_monitor_basic:ee31804e-92ba-4ba2-b38e-9d898d8b3a5a",
  ],
  source_event_ids: [
    "gmgn:twitter_monitor_basic:616d49c8-8186-4200-8c04-682d15c9d565",
    "gmgn:twitter_monitor_basic:6adbc0a4-3001-4d68-a1d5-7b942fe07214",
    "gmgn:twitter_monitor_basic:aac4a193-4d22-44e9-be67-34f18f57c907",
    "gmgn:twitter_monitor_basic:e85fe52a-048e-4539-b262-539a8ed43016",
    "gmgn:twitter_monitor_basic:ee31804e-92ba-4ba2-b38e-9d898d8b3a5a",
  ],
  factor_snapshot: tittyFactorSnapshot(),
  decision: {
    route: "meme",
    recommendation: "trade_candidate",
    confidence: 0.35,
    abstain_reason: null,
    stage_count: 3,
    summary_zh:
      "TITTY 代币在 Solana 链上呈现极高的社交热度（得分91）和异常的注意力爆发，但数据质量存在严重缺陷。流动性仅3万美元，24小时交易量却高达153万美元（换手率极高），暗示强烈的投机或机器人交易行为。社交传播主要由单一营销账号主导，独立作者真实性存疑，且缺乏语义催化剂数据和持有者分布信息。虽然具备早期 meme 的高波动投机属性，但 Rug Pull 风险和流动性深度不足是主要障碍，仅适合高风险投机，不建议作为稳健标的。",
    invalidation_conditions: [
      "流动性池规模急剧缩减超过 20%",
      "持有者数量在 1 小时内出现断崖式下跌超过 10%",
      "主要营销账号停止发声或社交媒体热度得分骤降至 50 以下",
    ],
    residual_risks: [
      "流动性极浅（3万美元），大额交易滑点风险极高",
      "高度集中的营销推送可能导致价格瞬间崩盘",
      "智能合约未验证所有权弃置，存在 Rug Pull 风险",
      "交易量可能由做市机器人自买自卖制造，缺乏真实需求",
      "持有者结构不透明，无法排除巨鲸集中控盘",
    ],
    evidence_event_ids: [
      "gmgn:twitter_monitor_basic:616d49c8-8186-4200-8c04-682d15c9d565",
      "gmgn:twitter_monitor_basic:6adbc0a4-3001-4d68-a1d5-7b942fe07214",
      "gmgn:twitter_monitor_basic:aac4a193-4d22-44e9-be67-34f18f57c907",
      "gmgn:twitter_monitor_basic:e85fe52a-048e-4539-b262-539a8ed43016",
      "gmgn:twitter_monitor_basic:ee31804e-92ba-4ba2-b38e-9d898d8b3a5a",
    ],
  },
  gate: {},
  fact_card: {
    mentions_1h: 5,
    unique_authors: 3,
    market_cap_usd: 114241.534330231,
    liquidity_usd: 30862.6465060373,
    holders: 968,
    volume_24h_usd: 1537005.60842172,
    watched_mentions: 0,
  },
  agent_run_id: "pulse-run:7d250fd8ed8838475aa1b9f8d7deef780e963804",
  pulse_version: "pulse-decision-harness-v1",
  gate_version: "gate-v1",
  prompt_version: "p4.2",
  schema_version: "token_factor_snapshot_v3_social_attention",
  created_at_ms: 1778725672119,
  updated_at_ms: 1778726642689,
  playbooks: [],
  stages,
};

function tittyFactorSnapshot() {
  return {
    schema_version: "token_factor_snapshot_v3_social_attention" as const,
    subject: {
      target_type: "Asset",
      target_id: "asset:solana:token:gTi4ZMMM2M7vQqZeetyQpWpjFr57zFZ7MCu4krypump",
      symbol: "TITTY",
      chain: "solana",
      address: "gTi4ZMMM2M7vQqZeetyQpWpjFr57zFZ7MCu4krypump",
      target_market_type: "dex",
      pricefeed_id: null,
    },
    market: {
      readiness: {
        stale_fields: ["decision_latest"],
        anchor_status: "missing",
        latest_status: "stale",
        missing_fields: [],
        dex_floor_status: "ready",
      },
      event_anchor: null,
      decision_latest: {
        source: "decision_latest",
        holders: 968,
        provider: "okx_dex_ws_price_info",
        price_usd: 0.000116212782553007,
        target_id: "asset:solana:token:gTi4ZMMM2M7vQqZeetyQpWpjFr57zFZ7MCu4krypump",
        liquidity_usd: 30862.6465060373,
        market_cap_usd: 114241.534330231,
        observed_at_ms: 1778719396208,
        received_at_ms: 1778719373102,
        volume_24h_usd: 1537005.60842172,
      },
    },
    gates: {
      max_decision: "high_alert",
      risk_reasons: [],
      blocked_reasons: [],
      eligible_for_high_alert: true,
    },
    data_health: { alpha: "ready", market: "missing", social: "ready", identity: "ready" },
    families: {
      social_heat: {
        facts: {
          mentions_1h: 5,
          mentions_4h: 13,
          mentions_24h: 13,
          unique_authors: 3,
          attention_surprise: null,
          new_burst_score: 1.791759469228055,
          watched_mentions: 0,
          baseline_sample_count: 6,
        },
        score: 91,
        weight: 0.45,
        factors: {},
        raw_score: 77,
        data_health: "ready",
      },
      social_propagation: {
        facts: {
          mentions: 5,
          independent_authors: 3,
          top_author_share: 0.6,
          duplicate_text_share: 0.2,
          time_to_second_author_ms: 283694,
          time_to_third_author_ms: 1744412,
          watched_author_count: 0,
          public_followup_author_count: 0,
        },
        score: 85,
        weight: 0.4,
        factors: {},
        raw_score: 76,
        data_health: "ready",
      },
      semantic_catalyst: {
        facts: { mentions: 5, llm_covered_mentions: 0 },
        score: 50,
        weight: 0.15,
        factors: {},
        raw_score: 0,
        data_health: "ready",
      },
      timing_risk: {
        facts: {
          price_change_status: "stale",
          social_signal_start_ms: 1778723098488,
          price_change_since_social_pct: null,
          price_change_before_social_pct: null,
        },
        score: 0,
        weight: 0.0,
        factors: {},
        raw_score: 0,
        data_health: "missing",
      },
    },
    normalization: {
      status: "ranked",
      alpha_rank: 0.822137,
      cohort_size: 131,
      cohort_status: "ready",
      factor_ranks: {
        social_heat: 0.9083969465648855,
        timing_risk: null,
        semantic_catalyst: 0.4961832061068702,
        social_propagation: 0.8473282442748091,
      },
    },
    composite: {
      rank_score: 82,
      raw_alpha_score: 65,
      recommended_decision: "high_alert",
      family_scores: {
        social_heat: 91,
        timing_risk: 0,
        semantic_catalyst: 50,
        social_propagation: 85,
      },
    },
    provenance: {
      source_event_ids: [],
      computed_at_ms: 1778726642689,
    },
  };
}
```

- [ ] **Step 3: Write `titty-source-events.ts`**

```typescript
import type { SocialEventDetail } from "@lib/types";

export const tittySourceEventsFixture: SocialEventDetail[] = [
  {
    event_id: "gmgn:twitter_monitor_basic:aac4a193-4d22-44e9-be67-34f18f57c907",
    timestamp_ms: 1778723098000,
    source_provider: "gmgn",
    channel: "twitter_monitor_basic",
    action: "tweet",
    author_handle: "moontoklisting",
    author_name: "Moontok Listing Alert",
    author_followers: 48771,
    author_watched: false,
    text_clean:
      "月兔雷霆 - Moontok Xpress Troll Kitty ( $TITTY ) gTi4ZMMM2M7vQqZeetyQpWpjFr57zFZ7MCu4krypump LIQ: $27,373 | MC: $94,539 #altcoin #memecoins",
    canonical_url: null,
  },
  {
    event_id: "gmgn:twitter_monitor_basic:ee31804e-92ba-4ba2-b38e-9d898d8b3a5a",
    timestamp_ms: 1778723381000,
    source_provider: "gmgn",
    channel: "twitter_monitor_basic",
    action: "quote",
    author_handle: "cache100x",
    author_name: "Cache",
    author_followers: 2718,
    author_watched: false,
    text_clean:
      "solana:gTi4ZMMM2M7vQqZeetyQpWpjFr57zFZ7MCu4krypump's New @MoontokListing - LSGO Volume Bot Coming NEXT!",
    canonical_url: null,
  },
  {
    event_id: "gmgn:twitter_monitor_basic:6adbc0a4-3001-4d68-a1d5-7b942fe07214",
    timestamp_ms: 1778724842000,
    source_provider: "gmgn",
    channel: "twitter_monitor_basic",
    action: "repost",
    author_handle: "qkl2058",
    author_name: "区块链行情研究",
    author_followers: 66467,
    author_watched: false,
    text_clean: null,
    canonical_url: null,
  },
  {
    event_id: "gmgn:twitter_monitor_basic:e85fe52a-048e-4539-b262-539a8ed43016",
    timestamp_ms: 1778726164000,
    source_provider: "gmgn",
    channel: "twitter_monitor_basic",
    action: "tweet",
    author_handle: "cache100x",
    author_name: "Cache",
    author_followers: 2719,
    author_watched: false,
    text_clean:
      "100x Boost For solana:gTi4ZMMM2M7vQqZeetyQpWpjFr57zFZ7MCu4krypump at 150k MC! LSGO",
    canonical_url: null,
  },
  {
    event_id: "gmgn:twitter_monitor_basic:616d49c8-8186-4200-8c04-682d15c9d565",
    timestamp_ms: 1778726543000,
    source_provider: "gmgn",
    channel: "twitter_monitor_basic",
    action: "reply",
    author_handle: "cache100x",
    author_name: "Cache",
    author_followers: 2719,
    author_watched: false,
    text_clean: "solana:gTi4ZMMM2M7vQqZeetyQpWpjFr57zFZ7MCu4krypump The Saviour Trust!",
    canonical_url: null,
  },
];

export const TITTY_NOW_MS = 1778726642689;
```

- [ ] **Step 4: Write `index.ts` barrel**

```typescript
export { tittyPulseFixture } from "./titty-pulse";
export { tittySourceEventsFixture, TITTY_NOW_MS } from "./titty-source-events";
```

- [ ] **Step 5: Typecheck**

```bash
cd web && pnpm typecheck
```

Expected: clean (fixtures are syntactically valid `SignalPulseItem` & `SocialEventDetail` after Task 5).

- [ ] **Step 6: Commit**

```bash
git add web/src/features/signal-lab/test/fixtures/
git commit -m "Add real \$TITTY pulse fixture for component tests"
```

---

## Task 7: Frontend — `buildPulseDetailView` pure view-model + tests

**Files:**
- Create: `web/src/features/signal-lab/model/pulseDetail.ts`
- Create: `web/src/features/signal-lab/model/pulseDetail.test.ts`

**Background:** This is the heart of the redesign. A single pure function takes `(SignalPulseItem, SocialEventDetail[], now)` and returns a fully shaped `PulseDetailViewModel` that components only need to render. All time bucketing, group computation, author classification, gate-vs-agent detection, fallback handling lives here — never in components. Components contain JSX + a11y only.

- [ ] **Step 1: Write the failing tests first**

Create `web/src/features/signal-lab/model/pulseDetail.test.ts`:

```typescript
import { describe, expect, it } from "vitest";

import { tittyPulseFixture, tittySourceEventsFixture, TITTY_NOW_MS } from "../test/fixtures";

import { buildPulseDetailView, GATE_AGENT_MISMATCH_CONFIDENCE } from "./pulseDetail";

describe("buildPulseDetailView · TITTY fixture", () => {
  const view = buildPulseDetailView({
    item: tittyPulseFixture,
    sourceEvents: tittySourceEventsFixture,
    now: TITTY_NOW_MS,
  });

  it("constructs hero identity", () => {
    expect(view.hero.subject.symbol).toBe("TITTY");
    expect(view.hero.subject.chain).toBe("solana");
    expect(view.hero.subject.shortAddress).toMatch(/^gTi4ZMMM/);
  });

  it("emits gate-agent mismatch pill on high_conviction band + confidence 0.35", () => {
    expect(view.hero.pills).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ id: "score_band", tone: "opportunity" }),
        expect.objectContaining({ id: "route", tone: "info" }),
        expect.objectContaining({ id: "gate_agent_mismatch", tone: "risk" }),
        expect.objectContaining({ id: "market_data_stale", tone: "risk" }),
      ]),
    );
  });

  it("computes freshness rows with absolute and relative time", () => {
    const market = view.hero.freshness.find((row) => row.label === "decision_latest");
    expect(market?.value).toMatch(/119m ago/);
    const anchor = view.hero.freshness.find((row) => row.label === "event_anchor");
    expect(anchor?.tone).toBe("risk");
    expect(anchor?.value).toBe("missing");
  });

  it("bins burst histogram into 24 hourly buckets ending at now", () => {
    expect(view.hero.burstHistogram.bins).toHaveLength(24);
    const total = view.hero.burstHistogram.bins.reduce((acc, bin) => acc + bin.count, 0);
    expect(total).toBe(tittySourceEventsFixture.length);
    expect(view.hero.burstHistogram.firstEventAt).toBe(1778723098000);
    expect(view.hero.burstHistogram.peakBucketIndex).toBeGreaterThanOrEqual(0);
  });

  it("computes timeline nodes", () => {
    expect(view.timeline.nodes.map((node) => node.kind)).toEqual([
      "market_anchor",
      "first",
      "peak",
      "now",
    ]);
    expect(view.timeline.nodes[0].timestampLabel).toMatch(/UTC$/);
    expect(view.timeline.nodes[0].tone).toBe("risk");
  });

  it("orders factor families and flags missing data", () => {
    expect(view.families.map((fam) => fam.id)).toEqual([
      "social_heat",
      "social_propagation",
      "semantic_catalyst",
      "timing_risk",
    ]);
    expect(view.families[0].score).toBe(91);
    expect(view.families[0].rankLabel).toMatch(/top 9%/);
    expect(view.families[3].dataHealth).toBe("missing");
    expect(view.families[3].breakdown.every((row) => row.tone !== "health")).toBe(true);
  });

  it("flags market metrics correctly", () => {
    const market = view.market;
    expect(market.metrics.map((m) => m.id)).toEqual(["mcap", "liq", "vol_24h", "holders"]);
    const liq = market.metrics.find((m) => m.id === "liq")!;
    expect(liq.tone).toBe("warn"); // < $50K
    const vol = market.metrics.find((m) => m.id === "vol_24h")!;
    expect(vol.tone).toBe("risk"); // 13x mcap
    expect(vol.subValue).toMatch(/13\.5× mcap/);
    expect(market.staleNotice).toBeTruthy();
  });

  it("groups evidence events by timeline period", () => {
    const groupIds = view.evidence.groups.map((g) => g.id);
    // TITTY: first @ T-101m, peak burst includes most events, no pre-burst
    expect(groupIds).toContain("burst_window");
    // No empty groups should be present
    for (const group of view.evidence.groups) {
      expect(group.rows.length).toBeGreaterThan(0);
    }
  });

  it("classifies authors", () => {
    const rows = view.evidence.groups.flatMap((g) => g.rows);
    const cacheRows = rows.filter((row) => row.handle === "cache100x");
    expect(cacheRows).toHaveLength(3);
    expect(cacheRows[0].authorTag).toBe("spam_suspect"); // 3/5 = 60% share, low followers
    expect(cacheRows[0].cohortPosition).toMatch(/\d+\/3/);

    const moontok = rows.find((row) => row.handle === "moontoklisting");
    expect(moontok?.authorTag).toBe("kol_signal");
  });

  it("computes author concentration bar segments", () => {
    expect(view.evidence.concentration.segments).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ handle: "cache100x", count: 3, tone: "risk" }),
        expect.objectContaining({ handle: "moontoklisting", count: 1, tone: "opportunity" }),
      ]),
    );
    expect(view.evidence.concentration.topAuthorShare).toBeCloseTo(0.6);
  });

  it("derives author chips top 5 + +N more", () => {
    expect(view.evidence.authorChips.length).toBeLessThanOrEqual(5);
    expect(view.evidence.authorChips[0].handle).toBe("cache100x");
    expect(view.evidence.totalUniqueAuthors).toBe(3);
  });

  it("captures all 3 agent stages with delta annotations", () => {
    expect(view.agent.analyst?.confidence).toBe(0.82);
    expect(view.agent.critic?.confidenceCeiling).toBe(0.45);
    expect(view.agent.critic?.ceilingDeltaFromAnalyst).toBeCloseTo(0.45 - 0.82);
    expect(view.agent.judge?.confidence).toBe(0.35);
    expect(view.agent.judge?.belowCeiling).toBe(true);
  });

  it("surfaces gate-vs-agent mismatch", () => {
    expect(view.agent.mismatch).not.toBeNull();
    expect(view.agent.mismatch?.gateLabel).toMatch(/high_conviction/);
    expect(view.agent.mismatch?.agentLabel).toMatch(/0\.35/);
  });

  it("populates replay versions", () => {
    expect(view.agent.replay.pulseVersion).toBe("pulse-decision-harness-v1");
    expect(view.agent.replay.runId).toMatch(/pulse-run:/);
  });
});

describe("buildPulseDetailView · abstain edge case", () => {
  it("hides cited tab and shows callout when evidence_event_ids empty", () => {
    const abstain = {
      ...tittyPulseFixture,
      evidence_event_ids: [],
      decision: { ...tittyPulseFixture.decision, recommendation: "abstain", confidence: 0, evidence_event_ids: [] },
    };
    const view = buildPulseDetailView({ item: abstain, sourceEvents: tittySourceEventsFixture, now: TITTY_NOW_MS });
    expect(view.evidence.citedCount).toBe(0);
    expect(view.evidence.abstainCallout).toMatch(/agent abstained/);
  });
});

describe("buildPulseDetailView · research_only route", () => {
  it("omits Analyst/Critic/Judge and exposes gate-only stage", () => {
    const research = {
      ...tittyPulseFixture,
      decision: { ...tittyPulseFixture.decision, route: "research_only", recommendation: "abstain", confidence: 0 },
      stages: {
        analyst: null,
        critic: null,
        judge: null,
        research_only_gate: {
          stage: "research_only_gate",
          route: "research_only",
          status: "ok",
          model: null,
          started_at_ms: TITTY_NOW_MS,
          finished_at_ms: TITTY_NOW_MS,
          latency_ms: 0,
          attempt_index: 0,
          response: { abstain_reason: "no_target_resolved" },
          error: null,
        },
      },
    };
    const view = buildPulseDetailView({ item: research, sourceEvents: [], now: TITTY_NOW_MS });
    expect(view.agent.kind).toBe("research_only");
    expect(view.agent.analyst).toBeNull();
    expect(view.agent.researchOnlyGate?.abstainReason).toBe("no_target_resolved");
  });
});

describe("buildPulseDetailView · stage failure", () => {
  it("renders failed analyst as skipped placeholder", () => {
    const failed = {
      ...tittyPulseFixture,
      stages: {
        ...tittyPulseFixture.stages!,
        analyst: { ...tittyPulseFixture.stages!.analyst!, status: "failed", response: null },
      },
    };
    const view = buildPulseDetailView({ item: failed, sourceEvents: tittySourceEventsFixture, now: TITTY_NOW_MS });
    expect(view.agent.analyst?.status).toBe("failed");
    expect(view.agent.analyst?.confidence).toBeNull();
    expect(view.agent.critic?.ceilingDeltaFromAnalyst).toBeNull();
  });
});

describe("buildPulseDetailView · single-event pulse (p50)", () => {
  it("emits only burst_window group and no concentration bar when single author", () => {
    const single = {
      ...tittyPulseFixture,
      evidence_event_ids: [tittySourceEventsFixture[0].event_id],
      source_event_ids: [tittySourceEventsFixture[0].event_id],
    };
    const view = buildPulseDetailView({
      item: single,
      sourceEvents: [tittySourceEventsFixture[0]],
      now: TITTY_NOW_MS,
    });
    expect(view.evidence.groups).toHaveLength(1);
    expect(view.evidence.groups[0].id).toBe("burst_window");
    expect(view.evidence.authorChips).toHaveLength(0); // hidden when uniqueAuthors == 1
    expect(view.evidence.concentration.segments).toHaveLength(1);
  });
});

describe("GATE_AGENT_MISMATCH_CONFIDENCE constant", () => {
  it("is 0.5", () => {
    expect(GATE_AGENT_MISMATCH_CONFIDENCE).toBe(0.5);
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd web && pnpm test -- --run src/features/signal-lab/model/pulseDetail.test.ts
```

Expected: FAIL — module not found.

- [ ] **Step 3: Implement `pulseDetail.ts`**

Create `web/src/features/signal-lab/model/pulseDetail.ts`. This file is ~400 lines; below is the complete contents:

```typescript
import { compactNumber, formatRelativeAge, formatUsdCompact, formatUtcTimestamp, shortAddress } from "@lib/format";
import type {
  SignalPulseItem,
  SignalPulseStagePayload,
  SignalPulseStages,
  SocialEventDetail,
} from "@lib/types";

export const GATE_AGENT_MISMATCH_CONFIDENCE = 0.5;
const BURST_WINDOW_MS = 12 * 60 * 1000;
const BURST_PRE_WINDOW_MS = 30 * 60 * 1000;
const LATEST_WINDOW_MS = 10 * 60 * 1000;
const HISTOGRAM_BUCKETS = 24;
const HISTOGRAM_SPAN_MS = 24 * 60 * 60 * 1000;
const AUTHOR_SPAM_FOLLOWER_MAX = 5000;
const AUTHOR_SPAM_SHARE_MIN = 0.3;
const AUTHOR_KOL_FOLLOWER_MIN = 10000;
const LIQ_WARN_MAX = 50_000;
const HOLDERS_WARN_MAX = 500;
const VOL_MCAP_RISK_RATIO = 5;

export type Tone = "opportunity" | "health" | "info" | "risk" | "agent" | "neutral" | "warn";

export type Pill = { id: string; label: string; tone: Tone };

export type FreshnessRow = {
  label: string;
  value: string;
  tone: Tone;
};

export type BurstBin = { startMs: number; endMs: number; count: number };

export type BurstHistogram = {
  bins: BurstBin[];
  firstEventAt: number | null;
  peakBucketIndex: number;
  peakAt: number | null;
  nowAt: number;
  uniqueAuthors: number;
};

export type TimelineNode = {
  kind: "market_anchor" | "first" | "peak" | "now";
  title: string;
  timestampLabel: string;
  relativeAgeLabel: string;
  meta: string;
  tone: Tone;
};

export type FactorFamilyBreakdownRow = {
  label: string;
  value: string;
  tone: Tone;
};

export type FactorFamilyView = {
  id: "social_heat" | "social_propagation" | "semantic_catalyst" | "timing_risk";
  name: string;
  score: number;
  scoreTone: Tone;
  rankLabel: string;
  dataHealth: string;
  breakdown: FactorFamilyBreakdownRow[];
};

export type MarketMetric = {
  id: "mcap" | "liq" | "vol_24h" | "holders";
  label: string;
  value: string;
  subValue: string | null;
  tone: Tone;
};

export type EvidenceAuthorTag = "watched" | "spam_suspect" | "kol_signal" | "normal";

export type EvidenceRow = {
  eventId: string;
  timestampMs: number;
  timestampLabel: string;
  handle: string;
  displayName: string;
  followers: number | null;
  channel: string;
  action: string;
  body: string | null;
  isEmptyBody: boolean;
  cited: boolean;
  authorTag: EvidenceAuthorTag;
  cohortPosition: string | null;
};

export type EvidenceGroupId = "earlier" | "burst_window" | "post_burst" | "latest";

export type EvidenceGroup = {
  id: EvidenceGroupId;
  title: string;
  rangeLabel: string;
  defaultExpanded: boolean;
  rows: EvidenceRow[];
  citedCount: number;
  uniqueAuthors: number;
};

export type EvidenceAuthorChip = {
  handle: string;
  postCount: number;
  authorTag: EvidenceAuthorTag;
};

export type AuthorConcentrationSegment = {
  handle: string;
  count: number;
  share: number;
  tone: Tone;
};

export type AuthorConcentrationBar = {
  segments: AuthorConcentrationSegment[];
  topAuthorShare: number;
};

export type EvidenceView = {
  totalCount: number;
  citedCount: number;
  totalUniqueAuthors: number;
  authorChips: EvidenceAuthorChip[];
  groups: EvidenceGroup[];
  concentration: AuthorConcentrationBar;
  abstainCallout: string | null;
};

export type AnalystView = {
  status: string;
  latencyMs: number;
  model: string;
  recommendation: string;
  confidence: number | null;
  summary: string;
  evidence: string[];
} | null;

export type CriticView = {
  status: string;
  latencyMs: number;
  model: string;
  shouldAbstain: boolean;
  confidenceCeiling: number | null;
  ceilingDeltaFromAnalyst: number | null;
  weaknesses: string[];
  missingFactImpacts: string[];
} | null;

export type JudgeView = {
  status: string;
  latencyMs: number;
  model: string;
  route: string;
  recommendation: string;
  confidence: number | null;
  belowCeiling: boolean;
  abstainReason: string | null;
  summary: string;
  residualRisks: string[];
  invalidationConditions: string[];
} | null;

export type ResearchOnlyGateView = {
  status: string;
  abstainReason: string;
} | null;

export type GateAgentMismatch = {
  gateLabel: string;
  agentLabel: string;
  note: string;
} | null;

export type ReplayMeta = {
  pulseVersion: string;
  gateVersion: string;
  promptVersion: string;
  schemaVersion: string;
  runId: string;
  candidateId: string;
  agentRunId: string;
};

export type AgentRailView = {
  kind: "stages" | "research_only";
  totalLatencyMs: number;
  model: string;
  mismatch: GateAgentMismatch;
  analyst: AnalystView;
  critic: CriticView;
  judge: JudgeView;
  researchOnlyGate: ResearchOnlyGateView;
  replay: ReplayMeta;
};

export type PulseDetailViewModel = {
  candidateId: string;
  hero: {
    subject: { symbol: string; chain: string; shortAddress: string; targetMarketType: string };
    pills: Pill[];
    candidateIdShort: string;
    burstHistogram: BurstHistogram;
    freshness: FreshnessRow[];
  };
  timeline: { nodes: TimelineNode[] };
  families: FactorFamilyView[];
  market: { metrics: MarketMetric[]; staleNotice: string | null };
  evidence: EvidenceView;
  agent: AgentRailView;
};

export type BuildPulseDetailViewInput = {
  item: SignalPulseItem;
  sourceEvents: SocialEventDetail[];
  now: number;
};

export function buildPulseDetailView(input: BuildPulseDetailViewInput): PulseDetailViewModel {
  const { item, sourceEvents, now } = input;
  const events = [...sourceEvents].sort((a, b) => a.timestamp_ms - b.timestamp_ms);
  const burst = buildBurst(events, now);
  const evidence = buildEvidence(item, events, burst, now);
  const families = buildFamilies(item);
  const market = buildMarket(item);
  const agent = buildAgent(item, evidence.totalCount);
  const hero = buildHero(item, burst, agent, now);
  return {
    candidateId: item.candidate_id,
    hero,
    timeline: { nodes: buildTimeline(item, burst, now) },
    families,
    market,
    evidence,
    agent,
  };
}

// --- Hero ---

function buildHero(
  item: SignalPulseItem,
  burst: BurstHistogram,
  agent: AgentRailView,
  now: number,
): PulseDetailViewModel["hero"] {
  const snapshot = item.factor_snapshot;
  const subject = snapshot.subject ?? {};
  const decisionLatest = snapshot.market?.decision_latest;
  const eventAnchorMissing = !snapshot.market?.event_anchor;
  const latestStale = snapshot.market?.readiness?.latest_status === "stale";
  const pills: Pill[] = [];
  pills.push({ id: "score_band", label: item.score_band ?? "-", tone: scoreBandTone(item.score_band) });
  if (item.decision.route) {
    pills.push({ id: "route", label: `${item.decision.route} route`, tone: "info" });
  }
  if (agent.mismatch) {
    pills.push({ id: "gate_agent_mismatch", label: "gate-agent mismatch", tone: "risk" });
  }
  if (eventAnchorMissing || latestStale) {
    pills.push({ id: "market_data_stale", label: "market data stale", tone: "risk" });
  }
  return {
    subject: {
      symbol: `$${(subject.symbol ?? item.symbol ?? item.subject_key ?? "").replace(/^\$+/, "")}`,
      chain: subject.chain ?? "",
      shortAddress: shortAddress(subject.address ?? subject.target_id ?? null),
      targetMarketType: subject.target_market_type ?? "",
    },
    pills,
    candidateIdShort: shortenCandidateId(item.candidate_id),
    burstHistogram: burst,
    freshness: buildFreshness(item, decisionLatest, now),
  };
}

function buildFreshness(
  item: SignalPulseItem,
  decisionLatest: any,
  now: number,
): FreshnessRow[] {
  const snapshot = item.factor_snapshot;
  const dataHealth = snapshot.data_health ?? {};
  const rows: FreshnessRow[] = [];
  rows.push({
    label: "identity",
    value: String(dataHealth.identity ?? "-"),
    tone: dataHealth.identity === "ready" ? "health" : "risk",
  });
  rows.push({
    label: "social",
    value: String(dataHealth.social ?? "-"),
    tone: dataHealth.social === "ready" ? "health" : "risk",
  });
  rows.push({
    label: "event_anchor",
    value: snapshot.market?.event_anchor ? "ready" : "missing",
    tone: snapshot.market?.event_anchor ? "health" : "risk",
  });
  if (decisionLatest?.observed_at_ms) {
    const ageLabel = formatRelativeAge(decisionLatest.observed_at_ms, now);
    rows.push({
      label: "decision_latest",
      value: `${snapshot.market?.readiness?.latest_status ?? "ready"} ${ageLabel}`.trim(),
      tone:
        snapshot.market?.readiness?.latest_status === "stale" || snapshot.market?.readiness?.latest_status === "missing"
          ? "warn"
          : "health",
    });
  } else {
    rows.push({ label: "decision_latest", value: "missing", tone: "risk" });
  }
  const cohort = snapshot.normalization;
  rows.push({
    label: "cohort",
    value:
      cohort?.cohort_status === "ready"
        ? `ranked · ${cohort.cohort_size ?? 0}`
        : String(cohort?.cohort_status ?? "-"),
    tone: cohort?.cohort_status === "ready" ? "health" : "warn",
  });
  if (cohort?.alpha_rank != null) {
    const pctTop = Math.round((1 - cohort.alpha_rank) * 100);
    rows.push({
      label: "alpha rank",
      value: `${cohort.alpha_rank.toFixed(3)} · top ${pctTop}%`,
      tone: "info",
    });
  } else {
    rows.push({ label: "alpha rank", value: "n/a", tone: "neutral" });
  }
  return rows;
}

function shortenCandidateId(id: string): string {
  if (id.length <= 24) return id;
  return `${id.slice(0, 14)}…${id.slice(-5)}`;
}

function scoreBandTone(band: string | null | undefined): Tone {
  switch (band) {
    case "high_conviction":
    case "trade_candidate":
      return "opportunity";
    case "token_watch":
    case "theme_watch":
      return "info";
    case "risk_rejected_high_info":
      return "risk";
    default:
      return "neutral";
  }
}

// --- Burst histogram ---

function buildBurst(events: SocialEventDetail[], now: number): BurstHistogram {
  const bucketMs = HISTOGRAM_SPAN_MS / HISTOGRAM_BUCKETS;
  const startMs = now - HISTOGRAM_SPAN_MS;
  const bins: BurstBin[] = Array.from({ length: HISTOGRAM_BUCKETS }, (_, i) => ({
    startMs: startMs + i * bucketMs,
    endMs: startMs + (i + 1) * bucketMs,
    count: 0,
  }));
  for (const event of events) {
    if (event.timestamp_ms < startMs || event.timestamp_ms > now) continue;
    const idx = Math.min(
      HISTOGRAM_BUCKETS - 1,
      Math.floor((event.timestamp_ms - startMs) / bucketMs),
    );
    bins[idx].count += 1;
  }
  let peakIdx = 0;
  let peakCount = 0;
  bins.forEach((bin, idx) => {
    if (bin.count > peakCount) {
      peakCount = bin.count;
      peakIdx = idx;
    }
  });
  return {
    bins,
    firstEventAt: events[0]?.timestamp_ms ?? null,
    peakBucketIndex: peakIdx,
    peakAt: peakCount > 0 ? bins[peakIdx].startMs + bucketMs / 2 : null,
    nowAt: now,
    uniqueAuthors: new Set(events.map((e) => e.author_handle).filter(Boolean)).size,
  };
}

// --- Timeline ---

function buildTimeline(item: SignalPulseItem, burst: BurstHistogram, now: number): TimelineNode[] {
  const snapshot = item.factor_snapshot;
  const decisionLatest = snapshot.market?.decision_latest;
  const nodes: TimelineNode[] = [];
  if (decisionLatest?.observed_at_ms) {
    nodes.push({
      kind: "market_anchor",
      title: "decision_latest snapshot",
      timestampLabel: formatUtcTimestamp(decisionLatest.observed_at_ms),
      relativeAgeLabel: formatRelativeAge(decisionLatest.observed_at_ms, now),
      meta: `mcap ${formatUsdCompact(decisionLatest.market_cap_usd)} · liq ${formatUsdCompact(decisionLatest.liquidity_usd)} · ${compactNumber(decisionLatest.holders)} holders · vol24h ${formatUsdCompact(decisionLatest.volume_24h_usd)}`,
      tone: snapshot.market?.readiness?.latest_status === "stale" ? "risk" : "health",
    });
  }
  if (burst.firstEventAt) {
    nodes.push({
      kind: "first",
      title: "first mention",
      timestampLabel: formatUtcTimestamp(burst.firstEventAt),
      relativeAgeLabel: formatRelativeAge(burst.firstEventAt, now),
      meta: "first source event captured",
      tone: "neutral",
    });
  }
  if (burst.peakAt) {
    nodes.push({
      kind: "peak",
      title: "burst peak",
      timestampLabel: formatUtcTimestamp(burst.peakAt),
      relativeAgeLabel: formatRelativeAge(burst.peakAt, now),
      meta: `${burst.bins[burst.peakBucketIndex].count} mentions / 1h · ${burst.uniqueAuthors} unique authors total`,
      tone: "opportunity",
    });
  }
  nodes.push({
    kind: "now",
    title: "pulse decision",
    timestampLabel: formatUtcTimestamp(item.updated_at_ms),
    relativeAgeLabel: formatRelativeAge(item.updated_at_ms, now),
    meta: `stages ${item.decision.stage_count ?? 0} · ${item.decision.recommendation ?? "-"} · conf ${formatConfidence(item.decision.confidence)}`,
    tone: "health",
  });
  return nodes;
}

function formatConfidence(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "n/a";
  return value.toFixed(2);
}

// --- Families ---

function buildFamilies(item: SignalPulseItem): FactorFamilyView[] {
  const snapshot = item.factor_snapshot;
  const familyOrder: FactorFamilyView["id"][] = [
    "social_heat",
    "social_propagation",
    "semantic_catalyst",
    "timing_risk",
  ];
  const labels: Record<FactorFamilyView["id"], string> = {
    social_heat: "social heat",
    social_propagation: "propagation",
    semantic_catalyst: "semantic catalyst",
    timing_risk: "timing / risk",
  };
  return familyOrder.map((id) => buildFamily(id, labels[id], snapshot.families?.[id], snapshot.normalization));
}

function buildFamily(
  id: FactorFamilyView["id"],
  name: string,
  family: any,
  normalization: any,
): FactorFamilyView {
  const score = Math.round(family?.score ?? 0);
  const dataHealth = String(family?.data_health ?? "missing");
  const rank = normalization?.factor_ranks?.[id];
  const cohortSize = normalization?.cohort_size ?? 0;
  const rankLabel =
    typeof rank === "number"
      ? `cohort rank ${rank.toFixed(2)} · top ${Math.max(1, Math.round((1 - rank) * 100))}%`
      : dataHealth === "missing"
        ? "data_health: missing"
        : `cohort size ${cohortSize}`;
  const facts = family?.facts ?? {};
  const breakdown: FactorFamilyBreakdownRow[] = [];
  switch (id) {
    case "social_heat":
      breakdown.push(
        { label: "mentions 1h / 4h / 24h", value: `${facts.mentions_1h ?? 0} · ${facts.mentions_4h ?? 0} · ${facts.mentions_24h ?? 0}`, tone: "neutral" },
        { label: "unique authors", value: String(facts.unique_authors ?? 0), tone: "neutral" },
        {
          label: "attention surprise",
          value: facts.new_burst_score != null ? `${facts.new_burst_score.toFixed(2)} (baseline n=${facts.baseline_sample_count ?? "?"})` : "n/a (missing)",
          tone: (facts.baseline_sample_count ?? 0) < 10 ? "warn" : "neutral",
        },
        { label: "watched seed mentions", value: String(facts.watched_mentions ?? 0), tone: "neutral" },
      );
      break;
    case "social_propagation": {
      const topAuthorShare = facts.top_author_share ?? 0;
      const topAuthorTone: Tone = topAuthorShare >= 0.7 ? "risk" : topAuthorShare >= 0.5 ? "warn" : "neutral";
      breakdown.push(
        { label: "independent authors", value: String(facts.independent_authors ?? 0), tone: "neutral" },
        {
          label: "time to 2nd / 3rd author",
          value: `${msToHuman(facts.time_to_second_author_ms)} · ${msToHuman(facts.time_to_third_author_ms)}`,
          tone: "neutral",
        },
        {
          label: "top author share",
          value: typeof topAuthorShare === "number" ? topAuthorShare.toFixed(2) : "n/a",
          tone: topAuthorTone,
        },
        {
          label: "duplicate text share",
          value: typeof facts.duplicate_text_share === "number" ? facts.duplicate_text_share.toFixed(2) : "n/a",
          tone: (facts.duplicate_text_share ?? 0) >= 0.3 ? "warn" : "neutral",
        },
        { label: "watched / kol authors", value: String(facts.watched_author_count ?? 0), tone: "neutral" },
      );
      break;
    }
    case "semantic_catalyst":
      breakdown.push(
        {
          label: "llm covered mentions",
          value: `${facts.llm_covered_mentions ?? 0} / ${facts.mentions ?? 0}`,
          tone: (facts.llm_covered_mentions ?? 0) === 0 ? "risk" : "neutral",
        },
        { label: "direction mix", value: dataHealth === "missing" ? "n/a (missing)" : "see raw", tone: dataHealth === "missing" ? "risk" : "neutral" },
        { label: "impact / novelty", value: dataHealth === "missing" ? "n/a (missing)" : "see raw", tone: dataHealth === "missing" ? "risk" : "neutral" },
      );
      break;
    case "timing_risk":
      breakdown.push(
        {
          label: "price change before social",
          value: facts.price_change_before_social_pct != null ? `${facts.price_change_before_social_pct.toFixed(2)}%` : "n/a (price feed stale)",
          tone: facts.price_change_before_social_pct != null ? "neutral" : "risk",
        },
        {
          label: "price change since social",
          value: facts.price_change_since_social_pct != null ? `${facts.price_change_since_social_pct.toFixed(2)}%` : "n/a",
          tone: facts.price_change_since_social_pct != null ? "neutral" : "risk",
        },
        { label: "dex floor", value: "passed", tone: "neutral" },
      );
      break;
  }
  return {
    id,
    name,
    score,
    scoreTone: id === "timing_risk" ? "risk" : score >= 70 ? "health" : score >= 40 ? "info" : "neutral",
    rankLabel,
    dataHealth,
    breakdown,
  };
}

function msToHuman(value: number | null | undefined): string {
  if (!value) return "n/a";
  if (value < 60_000) return `${Math.round(value / 1000)}s`;
  if (value < 3_600_000) return `${Math.round(value / 60_000)}m`;
  return `${(value / 3_600_000).toFixed(1)}h`;
}

// --- Market ---

function buildMarket(item: SignalPulseItem): { metrics: MarketMetric[]; staleNotice: string | null } {
  const decisionLatest = item.factor_snapshot.market?.decision_latest;
  const readiness = item.factor_snapshot.market?.readiness;
  const mcap = decisionLatest?.market_cap_usd ?? null;
  const liq = decisionLatest?.liquidity_usd ?? null;
  const vol = decisionLatest?.volume_24h_usd ?? null;
  const holders = decisionLatest?.holders ?? null;
  const volRatio = mcap && vol ? vol / mcap : null;
  const metrics: MarketMetric[] = [
    { id: "mcap", label: "market cap", value: formatUsdCompact(mcap), subValue: null, tone: "neutral" },
    {
      id: "liq",
      label: liq != null && liq < LIQ_WARN_MAX ? "liquidity · thin" : "liquidity",
      value: formatUsdCompact(liq),
      subValue: null,
      tone: liq != null && liq < LIQ_WARN_MAX ? "warn" : "neutral",
    },
    {
      id: "vol_24h",
      label: "vol 24h",
      value: formatUsdCompact(vol),
      subValue: volRatio != null && volRatio >= VOL_MCAP_RISK_RATIO ? `${volRatio.toFixed(1)}× mcap` : null,
      tone: volRatio != null && volRatio >= VOL_MCAP_RISK_RATIO ? "risk" : "neutral",
    },
    {
      id: "holders",
      label: "holders",
      value: compactNumber(holders),
      subValue: null,
      tone: holders != null && holders < HOLDERS_WARN_MAX ? "warn" : "neutral",
    },
  ];
  const stale: string[] = [];
  if (!item.factor_snapshot.market?.event_anchor) stale.push("event_anchor null");
  if (readiness?.latest_status === "stale") stale.push(`decision_latest stale`);
  if ((readiness?.stale_fields ?? []).length > 0) {
    stale.push(`stale_fields: [${readiness.stale_fields.join(", ")}]`);
  }
  return {
    metrics,
    staleNotice: stale.length > 0 ? `⚠ ${stale.join(" · ")}` : null,
  };
}

// --- Evidence ---

function buildEvidence(
  item: SignalPulseItem,
  events: SocialEventDetail[],
  burst: BurstHistogram,
  now: number,
): EvidenceView {
  const citedSet = new Set(item.decision.evidence_event_ids ?? item.evidence_event_ids ?? []);
  const authorCounts = new Map<string, number>();
  for (const e of events) {
    const handle = e.author_handle ?? "(unknown)";
    authorCounts.set(handle, (authorCounts.get(handle) ?? 0) + 1);
  }
  const uniqueAuthors = authorCounts.size;
  const totalCount = events.length;

  const rows: EvidenceRow[] = events.map((event, index) => {
    const handle = event.author_handle ?? "(unknown)";
    const postCount = authorCounts.get(handle) ?? 1;
    const authorShare = totalCount > 0 ? postCount / totalCount : 0;
    const tag = classifyAuthor({
      followers: event.author_followers,
      watched: event.author_watched,
      authorShare,
      postCount,
    });
    const cohortPosition = postCount >= 2 ? `${authorRunIndex(events, event, index)}/${postCount}` : null;
    const body = event.text_clean ?? null;
    return {
      eventId: event.event_id,
      timestampMs: event.timestamp_ms,
      timestampLabel: formatUtcTimestamp(event.timestamp_ms),
      handle,
      displayName: event.author_name ?? handle,
      followers: event.author_followers,
      channel: event.channel,
      action: event.action,
      body,
      isEmptyBody: !body,
      cited: citedSet.has(event.event_id),
      authorTag: tag,
      cohortPosition,
    };
  });

  const groups = bucketGroups(rows, burst, item.updated_at_ms);
  const citedCount = rows.filter((row) => row.cited).length;
  const authorChips: EvidenceAuthorChip[] =
    uniqueAuthors > 1
      ? [...authorCounts.entries()]
          .sort((a, b) => b[1] - a[1])
          .slice(0, 5)
          .map(([handle, postCount]) => {
            const sample = rows.find((row) => row.handle === handle)!;
            return { handle, postCount, authorTag: sample.authorTag };
          })
      : [];

  const concentration = buildConcentration(rows, authorCounts);
  const abstain = item.decision.recommendation === "abstain";
  return {
    totalCount,
    citedCount,
    totalUniqueAuthors: uniqueAuthors,
    authorChips,
    groups,
    concentration,
    abstainCallout: abstain ? "agent abstained — showing all source events for context" : null,
  };
}

function authorRunIndex(events: SocialEventDetail[], event: SocialEventDetail, index: number): number {
  let count = 0;
  for (let i = 0; i <= index; i += 1) {
    if (events[i].author_handle === event.author_handle) count += 1;
  }
  return count;
}

function classifyAuthor(args: {
  followers: number | null;
  watched: boolean;
  authorShare: number;
  postCount: number;
}): EvidenceAuthorTag {
  if (args.watched) return "watched";
  if (
    args.followers != null &&
    args.followers < AUTHOR_SPAM_FOLLOWER_MAX &&
    args.authorShare >= AUTHOR_SPAM_SHARE_MIN
  )
    return "spam_suspect";
  if (args.followers != null && args.followers >= AUTHOR_KOL_FOLLOWER_MIN && args.postCount === 1)
    return "kol_signal";
  return "normal";
}

function bucketGroups(
  rows: EvidenceRow[],
  burst: BurstHistogram,
  updatedAtMs: number,
): EvidenceGroup[] {
  const totalCount = rows.length;
  const peak = burst.peakAt ?? burst.firstEventAt ?? updatedAtMs;
  const burstStart = peak - BURST_PRE_WINDOW_MS;
  const burstEnd = peak + BURST_WINDOW_MS;
  const latestStart = updatedAtMs - LATEST_WINDOW_MS;
  const groupsRaw: Record<EvidenceGroupId, EvidenceRow[]> = {
    earlier: [],
    burst_window: [],
    post_burst: [],
    latest: [],
  };
  for (const row of rows) {
    const t = row.timestampMs;
    if (t < burstStart) groupsRaw.earlier.push(row);
    else if (t <= burstEnd) groupsRaw.burst_window.push(row);
    else if (t <= latestStart) groupsRaw.post_burst.push(row);
    else groupsRaw.latest.push(row);
  }
  const groupTitles: Record<EvidenceGroupId, string> = {
    earlier: "earlier",
    burst_window: "burst window",
    post_burst: "post-burst",
    latest: "latest",
  };
  return (Object.keys(groupsRaw) as EvidenceGroupId[])
    .filter((id) => groupsRaw[id].length > 0)
    .map((id) => {
      const rowsInGroup = groupsRaw[id];
      const first = rowsInGroup[0].timestampMs;
      const last = rowsInGroup[rowsInGroup.length - 1].timestampMs;
      const defaultExpanded =
        id === "burst_window" ||
        id === "latest" ||
        (id === "earlier" && (rowsInGroup.length <= 5 || totalCount <= 20)) ||
        (id === "post_burst" && rowsInGroup.length <= 12);
      return {
        id,
        title: groupTitles[id],
        rangeLabel: `${formatUtcTimestamp(first, { suffix: false })} ~ ${formatUtcTimestamp(last, { suffix: false })} UTC`,
        defaultExpanded,
        rows: rowsInGroup,
        citedCount: rowsInGroup.filter((r) => r.cited).length,
        uniqueAuthors: new Set(rowsInGroup.map((r) => r.handle)).size,
      };
    });
}

function buildConcentration(
  rows: EvidenceRow[],
  authorCounts: Map<string, number>,
): AuthorConcentrationBar {
  const total = rows.length;
  const segments: AuthorConcentrationSegment[] = [...authorCounts.entries()]
    .sort((a, b) => b[1] - a[1])
    .map(([handle, count]) => {
      const sample = rows.find((row) => row.handle === handle)!;
      return {
        handle,
        count,
        share: total > 0 ? count / total : 0,
        tone: toneForAuthorTag(sample.authorTag),
      };
    });
  return {
    segments,
    topAuthorShare: segments[0]?.share ?? 0,
  };
}

function toneForAuthorTag(tag: EvidenceAuthorTag): Tone {
  switch (tag) {
    case "spam_suspect":
      return "risk";
    case "watched":
      return "health";
    case "kol_signal":
      return "opportunity";
    default:
      return "info";
  }
}

// --- Agent rail ---

function buildAgent(item: SignalPulseItem, totalEvents: number): AgentRailView {
  const stages = item.stages ?? emptyStages();
  const kind = item.decision.route === "research_only" ? "research_only" : "stages";
  const analyst = buildAnalyst(stages.analyst);
  const critic = buildCritic(stages.critic, analyst);
  const judge = buildJudge(stages.judge, critic);
  const totalLatency =
    (stages.analyst?.latency_ms ?? 0) +
    (stages.critic?.latency_ms ?? 0) +
    (stages.judge?.latency_ms ?? 0);
  const model = stages.judge?.model ?? stages.analyst?.model ?? "-";
  const mismatch = detectMismatch(item);
  return {
    kind,
    totalLatencyMs: totalLatency,
    model,
    mismatch,
    analyst,
    critic,
    judge,
    researchOnlyGate:
      kind === "research_only" && stages.research_only_gate
        ? {
            status: stages.research_only_gate.status ?? "ok",
            abstainReason:
              (stages.research_only_gate.response as { abstain_reason?: string } | null)
                ?.abstain_reason ?? item.decision.abstain_reason ?? "",
          }
        : null,
    replay: {
      pulseVersion: item.pulse_version ?? "-",
      gateVersion: item.gate_version ?? "-",
      promptVersion: item.prompt_version ?? "-",
      schemaVersion: item.schema_version ?? "-",
      runId: item.agent_run_id ?? "-",
      candidateId: item.candidate_id,
      agentRunId: item.agent_run_id ?? "-",
    },
  };
}

function emptyStages(): SignalPulseStages {
  return { analyst: null, critic: null, judge: null, research_only_gate: null };
}

function buildAnalyst(stage: SignalPulseStagePayload | null): AnalystView {
  if (!stage) return null;
  const response = (stage.response ?? {}) as Record<string, unknown>;
  return {
    status: stage.status ?? "skipped",
    latencyMs: stage.latency_ms ?? 0,
    model: stage.model ?? "-",
    recommendation: String(response.recommendation ?? "-"),
    confidence: numberOrNull(response.confidence),
    summary: String(response.summary_zh ?? ""),
    evidence: stringList(response.evidence),
  };
}

function buildCritic(stage: SignalPulseStagePayload | null, analyst: AnalystView): CriticView {
  if (!stage) return null;
  const response = (stage.response ?? {}) as Record<string, unknown>;
  const ceiling = numberOrNull(response.confidence_ceiling);
  const analystConfidence = analyst?.confidence ?? null;
  return {
    status: stage.status ?? "skipped",
    latencyMs: stage.latency_ms ?? 0,
    model: stage.model ?? "-",
    shouldAbstain: Boolean(response.should_abstain),
    confidenceCeiling: ceiling,
    ceilingDeltaFromAnalyst:
      ceiling != null && analystConfidence != null ? ceiling - analystConfidence : null,
    weaknesses: stringList(response.weaknesses),
    missingFactImpacts: stringList(response.missing_fact_impacts),
  };
}

function buildJudge(stage: SignalPulseStagePayload | null, critic: CriticView): JudgeView {
  if (!stage) return null;
  const response = (stage.response ?? {}) as Record<string, unknown>;
  const confidence = numberOrNull(response.confidence);
  const ceiling = critic?.confidenceCeiling ?? null;
  return {
    status: stage.status ?? "skipped",
    latencyMs: stage.latency_ms ?? 0,
    model: stage.model ?? "-",
    route: String(response.route ?? "-"),
    recommendation: String(response.recommendation ?? "-"),
    confidence,
    belowCeiling: confidence != null && ceiling != null && confidence <= ceiling,
    abstainReason: response.abstain_reason ? String(response.abstain_reason) : null,
    summary: String(response.summary_zh ?? ""),
    residualRisks: stringList(response.residual_risks),
    invalidationConditions: stringList(response.invalidation_conditions),
  };
}

function detectMismatch(item: SignalPulseItem): GateAgentMismatch {
  const highGate =
    item.score_band === "high_conviction" || item.score_band === "trade_candidate";
  if (!highGate) return null;
  const conf = item.decision.confidence ?? 0;
  const rec = item.decision.recommendation;
  const lowAgent = ["watchlist", "ignore", "abstain"].includes(rec ?? "") || conf < GATE_AGENT_MISMATCH_CONFIDENCE;
  if (!lowAgent) return null;
  return {
    gateLabel: `score gate: ${item.score_band ?? "-"} (${item.candidate_score ?? 0})`,
    agentLabel: `agent: ${rec ?? "-"} · ${conf.toFixed(2)}`,
    note: "composite rank score said top tier; the 3-stage agent collapsed confidence. Review reason in Critic.",
  };
}

function numberOrNull(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function stringList(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value.filter((entry): entry is string => typeof entry === "string" && entry.length > 0);
}
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
cd web && pnpm test -- --run src/features/signal-lab/model/pulseDetail.test.ts
```

Expected: all tests pass.

- [ ] **Step 5: Typecheck**

```bash
cd web && pnpm typecheck
```

Expected: clean.

- [ ] **Step 6: Commit**

```bash
git add web/src/features/signal-lab/model/pulseDetail.ts web/src/features/signal-lab/model/pulseDetail.test.ts
git commit -m "Add buildPulseDetailView pure view-model builder"
```

---

## Task 8: Frontend — `useSourceEvents` API hook

**Files:**
- Modify: `web/src/features/signal-lab/api/useSignalPulseQueries.ts`
- Modify: `web/src/shared/query/queryKeys.ts`

**Background:** Batch fetch full social events by their ids. Uses react-query keyed by sorted ids so two different orderings of the same list share cache. Disabled when ids is empty.

- [ ] **Step 1: Add a queryKey factory entry**

In `web/src/shared/query/queryKeys.ts` add (next to existing keys):

```typescript
sourceEventsByIds: (ids: string[]) => ["social-events", "by-ids", [...ids].sort()] as const,
```

- [ ] **Step 2: Add the hook**

Append to `web/src/features/signal-lab/api/useSignalPulseQueries.ts`:

```typescript
import type { SocialEventDetail, SocialEventsByIdsData } from "@lib/types";

type SourceEventsArgs = {
  token: string;
  ids: string[];
};

export function useSourceEvents({ token, ids }: SourceEventsArgs) {
  const normalizedIds = ids.filter((id) => Boolean(id));
  return useQuery({
    queryKey: queryKeys.sourceEventsByIds(normalizedIds),
    enabled: Boolean(token) && normalizedIds.length > 0,
    staleTime: 30_000,
    queryFn: async (): Promise<SocialEventDetail[]> => {
      const response = await getApi<SocialEventsByIdsData>("/api/social-events/by-ids", {
        token,
        params: { ids: normalizedIds.join(",") },
      });
      return response.data.events;
    },
  });
}
```

- [ ] **Step 3: Typecheck**

```bash
cd web && pnpm typecheck
```

Expected: clean.

- [ ] **Step 4: Add a unit test**

Create `web/src/features/signal-lab/api/useSignalPulseQueries.test.ts`:

```typescript
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import * as apiClient from "@lib/api/client";

import { useSourceEvents } from "./useSignalPulseQueries";

afterEach(() => vi.restoreAllMocks());

function wrapper() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
}

describe("useSourceEvents", () => {
  it("calls /api/social-events/by-ids with sorted ids", async () => {
    const spy = vi.spyOn(apiClient, "getApi").mockResolvedValue({
      ok: true,
      data: { events: [], not_found: [] },
    } as any);
    const { result } = renderHook(
      () => useSourceEvents({ token: "secret", ids: ["b", "a"] }),
      { wrapper: wrapper() },
    );
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(spy).toHaveBeenCalledWith(
      "/api/social-events/by-ids",
      expect.objectContaining({ token: "secret", params: { ids: "b,a" } }),
    );
  });

  it("is disabled with empty ids", async () => {
    const spy = vi.spyOn(apiClient, "getApi");
    renderHook(() => useSourceEvents({ token: "secret", ids: [] }), { wrapper: wrapper() });
    expect(spy).not.toHaveBeenCalled();
  });
});
```

- [ ] **Step 5: Run the test**

```bash
cd web && pnpm test -- --run src/features/signal-lab/api/useSignalPulseQueries.test.ts
```

Expected: 2 passed.

- [ ] **Step 6: Commit**

```bash
git add web/src/features/signal-lab/api/useSignalPulseQueries.ts web/src/features/signal-lab/api/useSignalPulseQueries.test.ts web/src/shared/query/queryKeys.ts
git commit -m "Add useSourceEvents hook for batch event lookup"
```

---

## Task 9: Frontend — `PulseHero` component

**Files:**
- Create: `web/src/features/signal-lab/ui/PulseDetail/PulseHero.tsx`
- Create: `web/src/features/signal-lab/ui/PulseDetail/PulseHero.module.css`
- Create: `web/src/features/signal-lab/ui/PulseDetail/PulseHero.test.tsx`

**Background:** Pure presentation. Consumes the `view.hero` slice + density + a small `actions` slot rendered by the parent (back link / venue links). 3-column grid in full density, stacked in compact.

- [ ] **Step 1: Write the failing test**

```typescript
import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { tittyPulseFixture, tittySourceEventsFixture, TITTY_NOW_MS } from "../../test/fixtures";
import { buildPulseDetailView } from "../../model/pulseDetail";

import { PulseHero } from "./PulseHero";

afterEach(() => cleanup());

const view = buildPulseDetailView({
  item: tittyPulseFixture,
  sourceEvents: tittySourceEventsFixture,
  now: TITTY_NOW_MS,
});

describe("PulseHero", () => {
  it("renders symbol, chain, and short address", () => {
    render(<PulseHero hero={view.hero} density="full" actions={null} />);
    expect(screen.getByText("$TITTY")).toBeInTheDocument();
    expect(screen.getByText(/solana/i)).toBeInTheDocument();
    expect(screen.getByText(/gTi4ZMMM/)).toBeInTheDocument();
  });

  it("renders all pills emitted by view-model", () => {
    render(<PulseHero hero={view.hero} density="full" actions={null} />);
    for (const pill of view.hero.pills) {
      expect(screen.getByText(pill.label)).toBeInTheDocument();
    }
  });

  it("renders 24 histogram bars", () => {
    const { container } = render(<PulseHero hero={view.hero} density="full" actions={null} />);
    expect(container.querySelectorAll("[data-bar]")).toHaveLength(24);
  });

  it("renders freshness rows with UTC time and relative age", () => {
    render(<PulseHero hero={view.hero} density="full" actions={null} />);
    const row = screen.getByText("decision_latest").closest("[data-freshness-row]");
    expect(row).not.toBeNull();
    expect(within(row!).getByText(/119m ago/)).toBeInTheDocument();
  });

  it("renders compact density without burst sparkline labels but keeps bars", () => {
    const { container } = render(<PulseHero hero={view.hero} density="compact" actions={null} />);
    expect(container.querySelector("[data-density='compact']")).not.toBeNull();
    // burst still present (just compact)
    expect(container.querySelectorAll("[data-bar]")).toHaveLength(24);
  });

  it("renders provided action slot", () => {
    render(
      <PulseHero
        hero={view.hero}
        density="full"
        actions={<a href="/signal-lab">← back to queue</a>}
      />,
    );
    expect(screen.getByText("← back to queue")).toBeInTheDocument();
  });
});
```

Save to `web/src/features/signal-lab/ui/PulseDetail/PulseHero.test.tsx`.

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd web && pnpm test -- --run src/features/signal-lab/ui/PulseDetail/PulseHero.test.tsx
```

Expected: FAIL — module not found.

- [ ] **Step 3: Implement `PulseHero.tsx`**

```tsx
import type { ReactNode } from "react";

import type { PulseDetailViewModel } from "../../model/pulseDetail";

import styles from "./PulseHero.module.css";

type Props = {
  hero: PulseDetailViewModel["hero"];
  density: "full" | "compact";
  actions: ReactNode;
};

export function PulseHero({ hero, density, actions }: Props) {
  return (
    <header className={styles.hero} data-density={density} aria-label="pulse identity and burst overview">
      <div className={styles.identity}>
        <h1 className={styles.symbol}>{hero.subject.symbol}</h1>
        <p className={styles.subjectSub}>
          {hero.subject.chain}
          {hero.subject.shortAddress ? ` · ${hero.subject.shortAddress}` : ""}
          {hero.subject.targetMarketType ? ` · ${hero.subject.targetMarketType}` : ""}
        </p>
        <div className={styles.pills}>
          {hero.pills.map((pill) => (
            <span key={pill.id} className={styles.pill} data-tone={pill.tone}>
              {pill.label}
            </span>
          ))}
        </div>
        <p className={styles.candidateId}>candidate · {hero.candidateIdShort}</p>
        {actions ? <div className={styles.actions}>{actions}</div> : null}
      </div>

      <div className={styles.burst}>
        <div className={styles.burstHead}>
          <span className={styles.kicker}>
            social burst · 24h · {hero.burstHistogram.bins.reduce((a, b) => a + b.count, 0)} mentions · {hero.burstHistogram.uniqueAuthors} authors
          </span>
        </div>
        <div className={styles.burstBars} aria-label="hourly mention histogram, last 24h">
          {hero.burstHistogram.bins.map((bin, idx) => {
            const isPeak = idx === hero.burstHistogram.peakBucketIndex && bin.count > 0;
            const isNow = idx === hero.burstHistogram.bins.length - 1;
            const max = Math.max(1, ...hero.burstHistogram.bins.map((b) => b.count));
            const height = bin.count > 0 ? Math.max(8, (bin.count / max) * 100) : 4;
            return (
              <span
                key={idx}
                data-bar
                data-has={bin.count > 0 ? "true" : "false"}
                data-peak={isPeak ? "true" : "false"}
                data-now={isNow ? "true" : "false"}
                className={styles.bar}
                style={{ height: `${height}%` }}
                title={`${bin.count} mentions`}
              />
            );
          })}
        </div>
      </div>

      <dl className={styles.freshness} aria-label="data freshness">
        <span className={styles.kicker}>data freshness · times shown in UTC</span>
        {hero.freshness.map((row) => (
          <div key={row.label} className={styles.freshnessRow} data-freshness-row data-tone={row.tone}>
            <dt>{row.label}</dt>
            <dd>{row.value}</dd>
          </div>
        ))}
      </dl>
    </header>
  );
}
```

- [ ] **Step 4: Implement `PulseHero.module.css`**

```css
.hero {
  display: grid;
  grid-template-columns: 280px 1fr 240px;
  gap: 14px;
  padding: 16px;
  border-bottom: 1px solid var(--line);
  background: rgba(18, 23, 19, 0.72);
}
.hero[data-density="compact"] {
  grid-template-columns: 1fr;
  gap: 10px;
}

.identity { display: grid; gap: 6px; min-width: 0; }
.symbol {
  margin: 0;
  font-family: var(--mono);
  font-size: 22px;
  letter-spacing: 0.01em;
  color: var(--bone);
}
.subjectSub {
  margin: 0;
  font-family: var(--mono);
  font-size: 11px;
  color: var(--ash);
}
.pills { display: flex; flex-wrap: wrap; gap: 6px; }
.pill {
  display: inline-flex;
  align-items: center;
  font-family: var(--mono);
  font-size: 10px;
  padding: 3px 9px;
  border: 1px solid var(--line);
  border-radius: 999px;
  background: var(--slab);
  color: var(--ash);
}
.pill[data-tone="opportunity"] { color: var(--opportunity-ink); border-color: var(--opportunity-line-strong); background: var(--opportunity-soft); }
.pill[data-tone="health"]      { color: var(--health-ink);      border-color: var(--health-line-strong);      background: var(--health-soft); }
.pill[data-tone="info"]        { color: var(--info-ink);        border-color: var(--info-line-strong);        background: var(--info-soft); }
.pill[data-tone="risk"]        { color: var(--risk-ink);        border-color: var(--risk-line-strong);        background: var(--risk-soft); }
.pill[data-tone="agent"]       { color: var(--agent-ink);       border-color: var(--agent-line);              background: var(--agent-soft); }

.candidateId { margin: 0; font-family: var(--mono); font-size: 10px; color: var(--dim); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.actions { display: flex; gap: 6px; flex-wrap: wrap; margin-top: 6px; }

.burst { display: grid; gap: 6px; min-width: 0; }
.burstHead { display: flex; justify-content: space-between; align-items: baseline; }
.kicker {
  font-family: var(--mono);
  font-size: 10px;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--dim);
}
.burstBars {
  position: relative;
  height: 56px;
  border: 1px solid var(--line);
  border-radius: var(--radius);
  background: var(--void);
  padding: 4px;
  display: grid;
  grid-template-columns: repeat(24, 1fr);
  gap: 2px;
  align-items: end;
}
.bar { background: var(--slab-3); border-radius: 1px; align-self: end; }
.bar[data-has="true"] { background: var(--opportunity-soft); }
.bar[data-peak="true"] { background: var(--opportunity); }
.bar[data-now="true"] { outline: 1px solid var(--opportunity-ink); }
.hero[data-density="compact"] .burstBars { height: 36px; }

.freshness { display: grid; gap: 4px; margin: 0; }
.freshnessRow {
  display: flex;
  justify-content: space-between;
  font-family: var(--mono);
  font-size: 11px;
  margin: 0;
}
.freshnessRow dt { color: var(--dim); margin: 0; }
.freshnessRow dd { margin: 0; color: var(--bone); }
.freshnessRow[data-tone="health"] dd { color: var(--health-ink); }
.freshnessRow[data-tone="warn"] dd { color: var(--opportunity-ink); }
.freshnessRow[data-tone="risk"] dd { color: var(--risk-ink); }
.freshnessRow[data-tone="info"] dd { color: var(--info-ink); }

.hero[data-density="compact"] .freshness {
  grid-template-columns: repeat(2, 1fr);
  column-gap: 12px;
}
```

- [ ] **Step 5: Run the test**

```bash
cd web && pnpm test -- --run src/features/signal-lab/ui/PulseDetail/PulseHero.test.tsx
```

Expected: PASS.

- [ ] **Step 6: Lint + typecheck**

```bash
cd web && pnpm lint && pnpm typecheck
```

Expected: clean.

- [ ] **Step 7: Commit**

```bash
git add web/src/features/signal-lab/ui/PulseDetail/PulseHero.tsx web/src/features/signal-lab/ui/PulseDetail/PulseHero.module.css web/src/features/signal-lab/ui/PulseDetail/PulseHero.test.tsx
git commit -m "Add PulseHero component with identity, burst histogram, freshness"
```

---

## Task 10: Frontend — `PulseTimeline` component

**Files:**
- Create: `web/src/features/signal-lab/ui/PulseDetail/PulseTimeline.tsx`
- Create: `web/src/features/signal-lab/ui/PulseDetail/PulseTimeline.module.css`
- Create: `web/src/features/signal-lab/ui/PulseDetail/PulseTimeline.test.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { tittyPulseFixture, tittySourceEventsFixture, TITTY_NOW_MS } from "../../test/fixtures";
import { buildPulseDetailView } from "../../model/pulseDetail";

import { PulseTimeline } from "./PulseTimeline";

afterEach(() => cleanup());

const view = buildPulseDetailView({
  item: tittyPulseFixture,
  sourceEvents: tittySourceEventsFixture,
  now: TITTY_NOW_MS,
});

describe("PulseTimeline", () => {
  it("renders 4 nodes in full density", () => {
    const { container } = render(<PulseTimeline timeline={view.timeline} density="full" />);
    expect(container.querySelectorAll("[data-node]")).toHaveLength(view.timeline.nodes.length);
  });

  it("shows market_anchor with risk tone when stale", () => {
    const { container } = render(<PulseTimeline timeline={view.timeline} density="full" />);
    const market = container.querySelector("[data-node='market_anchor']");
    expect(market?.getAttribute("data-tone")).toBe("risk");
  });

  it("renders absolute UTC timestamps", () => {
    render(<PulseTimeline timeline={view.timeline} density="full" />);
    expect(screen.getAllByText(/UTC/).length).toBeGreaterThanOrEqual(view.timeline.nodes.length);
  });

  it("stacks nodes vertically in compact density", () => {
    const { container } = render(<PulseTimeline timeline={view.timeline} density="compact" />);
    expect(container.querySelector("[data-density='compact']")).not.toBeNull();
  });
});
```

Save as `PulseTimeline.test.tsx`.

- [ ] **Step 2: Run the test to confirm it fails**

```bash
cd web && pnpm test -- --run src/features/signal-lab/ui/PulseDetail/PulseTimeline.test.tsx
```

Expected: FAIL — module not found.

- [ ] **Step 3: Implement `PulseTimeline.tsx`**

```tsx
import type { PulseDetailViewModel } from "../../model/pulseDetail";

import styles from "./PulseTimeline.module.css";

type Props = {
  timeline: PulseDetailViewModel["timeline"];
  density: "full" | "compact";
};

export function PulseTimeline({ timeline, density }: Props) {
  return (
    <section className={styles.section} data-density={density} aria-label="event timeline">
      <header className={styles.head}>
        <h2 className={styles.title}>event timeline</h2>
        <span className={styles.lead}>facts the agent saw, in order</span>
      </header>
      <ol className={styles.nodes}>
        {timeline.nodes.map((node) => (
          <li
            key={node.kind}
            className={styles.node}
            data-node={node.kind}
            data-tone={node.tone}
          >
            <p className={styles.nodeTag}>{node.title}</p>
            <p className={styles.nodeTimestamp}>
              {node.timestampLabel} <span className={styles.relative}>{node.relativeAgeLabel}</span>
            </p>
            <p className={styles.nodeMeta}>{node.meta}</p>
          </li>
        ))}
      </ol>
    </section>
  );
}
```

- [ ] **Step 4: Implement `PulseTimeline.module.css`**

```css
.section {
  display: grid;
  gap: 8px;
  padding: 14px 16px;
  border-bottom: 1px solid var(--line);
}
.head { display: flex; justify-content: space-between; align-items: baseline; }
.title { margin: 0; font-family: var(--mono); font-size: 12px; color: var(--bone); text-transform: uppercase; letter-spacing: 0.03em; }
.lead { font-family: var(--mono); font-size: 11px; color: var(--ash); }
.nodes {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 6px;
  list-style: none;
  margin: 0;
  padding: 0;
}
.section[data-density="compact"] .nodes { grid-template-columns: 1fr; }

.node {
  border: 1px solid var(--line);
  border-radius: var(--radius);
  padding: 9px;
  background: rgba(7, 9, 8, 0.62);
  display: grid;
  gap: 3px;
}
.node[data-tone="opportunity"] { border-color: var(--opportunity-line-strong); }
.node[data-tone="health"] { border-color: var(--health-line-strong); }
.node[data-tone="info"] { border-color: var(--info-line-strong); }
.node[data-tone="risk"] { border-color: var(--risk-line-strong); background: rgba(122, 44, 59, 0.12); }

.nodeTag { margin: 0; font-family: var(--mono); font-size: 11px; color: var(--bone); font-weight: 700; text-transform: uppercase; letter-spacing: 0.02em; }
.nodeTimestamp { margin: 0; font-family: var(--mono); font-size: 11px; color: var(--bone-2); }
.relative { color: var(--dim); margin-left: 4px; }
.nodeMeta { margin: 0; font-family: var(--sans); font-size: 11px; color: var(--ash); line-height: 1.4; }
```

- [ ] **Step 5: Run tests, lint, typecheck**

```bash
cd web && pnpm test -- --run src/features/signal-lab/ui/PulseDetail/PulseTimeline.test.tsx && pnpm lint && pnpm typecheck
```

Expected: green.

- [ ] **Step 6: Commit**

```bash
git add web/src/features/signal-lab/ui/PulseDetail/PulseTimeline.*
git commit -m "Add PulseTimeline component with 4-node period markers"
```

---

## Task 11: Frontend — `PulseFactorFamilies` component

**Files:**
- Create: `web/src/features/signal-lab/ui/PulseDetail/PulseFactorFamilies.tsx`
- Create: `web/src/features/signal-lab/ui/PulseDetail/PulseFactorFamilies.module.css`
- Create: `web/src/features/signal-lab/ui/PulseDetail/PulseFactorFamilies.test.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { tittyPulseFixture, tittySourceEventsFixture, TITTY_NOW_MS } from "../../test/fixtures";
import { buildPulseDetailView } from "../../model/pulseDetail";

import { PulseFactorFamilies } from "./PulseFactorFamilies";

afterEach(() => cleanup());
const view = buildPulseDetailView({
  item: tittyPulseFixture,
  sourceEvents: tittySourceEventsFixture,
  now: TITTY_NOW_MS,
});

describe("PulseFactorFamilies", () => {
  it("renders 4 family cards in canonical order", () => {
    const { container } = render(<PulseFactorFamilies families={view.families} density="full" />);
    const cards = container.querySelectorAll("[data-family]");
    expect(Array.from(cards).map((el) => el.getAttribute("data-family"))).toEqual([
      "social_heat",
      "social_propagation",
      "semantic_catalyst",
      "timing_risk",
    ]);
  });

  it("shows the score numerically", () => {
    render(<PulseFactorFamilies families={view.families} density="full" />);
    expect(screen.getByText("91")).toBeInTheDocument();
    expect(screen.getByText("85")).toBeInTheDocument();
    expect(screen.getByText("50")).toBeInTheDocument();
  });

  it("flags missing breakdown rows", () => {
    const { container } = render(<PulseFactorFamilies families={view.families} density="full" />);
    const timing = container.querySelector("[data-family='timing_risk']")!;
    expect(within(timing as HTMLElement).getAllByText(/n\/a/).length).toBeGreaterThan(0);
  });

  it("uses 2-col grid in full, 1-col in compact", () => {
    const { container } = render(<PulseFactorFamilies families={view.families} density="compact" />);
    expect(container.querySelector("[data-density='compact']")).not.toBeNull();
  });
});
```

- [ ] **Step 2: Run the test to confirm it fails**

```bash
cd web && pnpm test -- --run src/features/signal-lab/ui/PulseDetail/PulseFactorFamilies.test.tsx
```

Expected: FAIL.

- [ ] **Step 3: Implement `PulseFactorFamilies.tsx`**

```tsx
import type { FactorFamilyView } from "../../model/pulseDetail";

import styles from "./PulseFactorFamilies.module.css";

type Props = {
  families: FactorFamilyView[];
  density: "full" | "compact";
};

export function PulseFactorFamilies({ families, density }: Props) {
  return (
    <section className={styles.section} data-density={density} aria-label="factor families">
      <header className={styles.head}>
        <h2 className={styles.title}>factor families</h2>
      </header>
      <div className={styles.grid}>
        {families.map((family) => (
          <article
            key={family.id}
            className={styles.card}
            data-family={family.id}
            data-data-health={family.dataHealth}
          >
            <header className={styles.cardHead}>
              <span className={styles.name}>{family.name}</span>
              <span className={styles.score} data-tone={family.scoreTone}>
                {family.score}
              </span>
            </header>
            <p className={styles.rank}>{family.rankLabel}</p>
            <dl className={styles.breakdown}>
              {family.breakdown.map((row) => (
                <div key={row.label} className={styles.row} data-tone={row.tone}>
                  <dt>{row.label}</dt>
                  <dd>{row.value}</dd>
                </div>
              ))}
            </dl>
          </article>
        ))}
      </div>
    </section>
  );
}
```

- [ ] **Step 4: Implement `PulseFactorFamilies.module.css`**

```css
.section { display: grid; gap: 8px; padding: 14px 16px; border-bottom: 1px solid var(--line); }
.head { display: flex; justify-content: space-between; align-items: baseline; }
.title { margin: 0; font-family: var(--mono); font-size: 12px; color: var(--bone); text-transform: uppercase; letter-spacing: 0.03em; }

.grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
.section[data-density="compact"] .grid { grid-template-columns: 1fr; }

.card { border: 1px solid var(--line); border-radius: var(--radius); padding: 10px; background: rgba(7, 9, 8, 0.62); }
.cardHead { display: flex; justify-content: space-between; align-items: baseline; }
.name { font-family: var(--mono); font-size: 11px; color: var(--bone-2); text-transform: uppercase; letter-spacing: 0.02em; }
.score { font-family: var(--mono); font-size: 20px; color: var(--bone); }
.score[data-tone="health"] { color: var(--health-ink); }
.score[data-tone="info"] { color: var(--info-ink); }
.score[data-tone="risk"] { color: var(--risk-ink); }
.rank { margin: 4px 0 0; font-family: var(--mono); font-size: 10px; color: var(--ash); }
.breakdown { margin: 8px 0 0; display: grid; gap: 3px; }
.row { display: flex; justify-content: space-between; gap: 8px; font-family: var(--mono); font-size: 11px; }
.row dt { margin: 0; color: var(--ash); }
.row dd { margin: 0; color: var(--bone); }
.row[data-tone="warn"] dd { color: var(--opportunity-ink); }
.row[data-tone="risk"] dd { color: var(--risk-ink); }
.row[data-tone="health"] dd { color: var(--health-ink); }
```

- [ ] **Step 5: Run tests, lint, typecheck**

```bash
cd web && pnpm test -- --run src/features/signal-lab/ui/PulseDetail/PulseFactorFamilies.test.tsx && pnpm lint && pnpm typecheck
```

Expected: green.

- [ ] **Step 6: Commit**

```bash
git add web/src/features/signal-lab/ui/PulseDetail/PulseFactorFamilies.*
git commit -m "Add PulseFactorFamilies component with 4-family scorecard grid"
```

---

## Task 12: Frontend — `PulseMarketContext` component

**Files:**
- Create: `web/src/features/signal-lab/ui/PulseDetail/PulseMarketContext.tsx`
- Create: `web/src/features/signal-lab/ui/PulseDetail/PulseMarketContext.module.css`
- Create: `web/src/features/signal-lab/ui/PulseDetail/PulseMarketContext.test.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { tittyPulseFixture, tittySourceEventsFixture, TITTY_NOW_MS } from "../../test/fixtures";
import { buildPulseDetailView } from "../../model/pulseDetail";

import { PulseMarketContext } from "./PulseMarketContext";

afterEach(() => cleanup());

const view = buildPulseDetailView({
  item: tittyPulseFixture,
  sourceEvents: tittySourceEventsFixture,
  now: TITTY_NOW_MS,
});

describe("PulseMarketContext", () => {
  it("renders 4 metrics", () => {
    const { container } = render(<PulseMarketContext market={view.market} density="full" />);
    expect(container.querySelectorAll("[data-metric]")).toHaveLength(4);
  });

  it("renders thin liquidity warning", () => {
    const { container } = render(<PulseMarketContext market={view.market} density="full" />);
    expect(container.querySelector("[data-metric='liq']")?.getAttribute("data-tone")).toBe("warn");
  });

  it("renders volume-mcap ratio when risk", () => {
    render(<PulseMarketContext market={view.market} density="full" />);
    expect(screen.getByText(/13\.5× mcap/)).toBeInTheDocument();
  });

  it("renders stale notice", () => {
    render(<PulseMarketContext market={view.market} density="full" />);
    expect(screen.getByText(/event_anchor null/i)).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run the test to confirm it fails**

```bash
cd web && pnpm test -- --run src/features/signal-lab/ui/PulseDetail/PulseMarketContext.test.tsx
```

Expected: FAIL — module not found.

- [ ] **Step 3: Implement `PulseMarketContext.tsx`**

```tsx
import type { PulseDetailViewModel } from "../../model/pulseDetail";

import styles from "./PulseMarketContext.module.css";

type Props = {
  market: PulseDetailViewModel["market"];
  density: "full" | "compact";
};

export function PulseMarketContext({ market, density }: Props) {
  return (
    <section className={styles.section} data-density={density} aria-label="market context">
      <header className={styles.head}>
        <h2 className={styles.title}>market context</h2>
      </header>
      <ul className={styles.grid}>
        {market.metrics.map((metric) => (
          <li key={metric.id} className={styles.metric} data-metric={metric.id} data-tone={metric.tone}>
            <b>{metric.value}</b>
            <span>
              {metric.label}
              {metric.subValue ? ` · ${metric.subValue}` : ""}
            </span>
          </li>
        ))}
      </ul>
      {market.staleNotice ? <p className={styles.staleNotice}>{market.staleNotice}</p> : null}
    </section>
  );
}
```

- [ ] **Step 4: Implement `PulseMarketContext.module.css`**

```css
.section { display: grid; gap: 8px; padding: 14px 16px; border-bottom: 1px solid var(--line); }
.head { display: flex; justify-content: space-between; align-items: baseline; }
.title { margin: 0; font-family: var(--mono); font-size: 12px; color: var(--bone); text-transform: uppercase; letter-spacing: 0.03em; }

.grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; list-style: none; margin: 0; padding: 0; }
.section[data-density="compact"] .grid { grid-template-columns: repeat(2, 1fr); }

.metric { border: 1px solid var(--line); border-radius: var(--radius); padding: 9px 10px; background: rgba(7, 9, 8, 0.62); display: grid; gap: 4px; }
.metric[data-tone="warn"] { border-color: var(--opportunity-line-strong); background: var(--opportunity-soft); }
.metric[data-tone="risk"] { border-color: var(--risk-line-strong); background: var(--risk-soft); }
.metric b { font-family: var(--mono); font-size: 16px; color: var(--bone); }
.metric[data-tone="risk"] b { color: var(--risk-ink); }
.metric[data-tone="warn"] b { color: var(--opportunity-ink); }
.metric span { font-family: var(--mono); font-size: 10px; color: var(--dim); text-transform: lowercase; }

.staleNotice { margin: 0; font-family: var(--mono); font-size: 10px; color: var(--risk-ink); }
```

- [ ] **Step 5: Run tests, lint, typecheck**

```bash
cd web && pnpm test -- --run src/features/signal-lab/ui/PulseDetail/PulseMarketContext.test.tsx && pnpm lint && pnpm typecheck
```

Expected: green.

- [ ] **Step 6: Commit**

```bash
git add web/src/features/signal-lab/ui/PulseDetail/PulseMarketContext.*
git commit -m "Add PulseMarketContext component with 4-metric grid and stale notice"
```

---

## Task 13: Frontend — `PulseEvidenceList` component (toolbar, groups, concentration bar)

**Files:**
- Create: `web/src/features/signal-lab/ui/PulseDetail/PulseEvidenceList.tsx`
- Create: `web/src/features/signal-lab/ui/PulseDetail/PulseEvidenceList.module.css`
- Create: `web/src/features/signal-lab/ui/PulseDetail/PulseEvidenceList.test.tsx`

**Background:** Largest leaf component. Local state for `view`/`handle`/`type`/`sort` filters and group expansion. Filtering happens here, not in the view-model, because filtering is interactive. The view-model gives us the canonical, unfiltered groups; this component derives a filtered render on demand.

- [ ] **Step 1: Write the failing test**

```tsx
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { tittyPulseFixture, tittySourceEventsFixture, TITTY_NOW_MS } from "../../test/fixtures";
import { buildPulseDetailView } from "../../model/pulseDetail";

import { PulseEvidenceList } from "./PulseEvidenceList";

afterEach(() => cleanup());

const view = buildPulseDetailView({
  item: tittyPulseFixture,
  sourceEvents: tittySourceEventsFixture,
  now: TITTY_NOW_MS,
});

describe("PulseEvidenceList", () => {
  it("shows toolbar counts", () => {
    render(<PulseEvidenceList evidence={view.evidence} density="full" />);
    expect(screen.getByText(/all 5/i)).toBeInTheDocument();
    expect(screen.getByText(/cited 5/i)).toBeInTheDocument();
  });

  it("renders 5 evidence rows by default", () => {
    const { container } = render(<PulseEvidenceList evidence={view.evidence} density="full" />);
    expect(container.querySelectorAll("[data-evidence-row]")).toHaveLength(5);
  });

  it("renders author concentration legend", () => {
    render(<PulseEvidenceList evidence={view.evidence} density="full" />);
    expect(screen.getByText(/cache100x/)).toBeInTheDocument();
  });

  it("toggles cited view when tab clicked", () => {
    const { container } = render(<PulseEvidenceList evidence={view.evidence} density="full" />);
    fireEvent.click(screen.getByText(/cited 5/i));
    expect(
      Array.from(container.querySelectorAll("[data-evidence-row]")).every(
        (row) => row.getAttribute("data-cited") === "true",
      ),
    ).toBe(true);
  });

  it("filters by author when chip clicked", () => {
    const { container } = render(<PulseEvidenceList evidence={view.evidence} density="full" />);
    fireEvent.click(screen.getByText("@cache100x"));
    const rows = container.querySelectorAll("[data-evidence-row]");
    expect(Array.from(rows).every((row) => row.getAttribute("data-handle") === "cache100x")).toBe(
      true,
    );
  });

  it("shows abstain callout when emitted", () => {
    const abstain = {
      ...view.evidence,
      abstainCallout: "agent abstained — showing all source events for context",
    };
    render(<PulseEvidenceList evidence={abstain} density="full" />);
    expect(screen.getByText(/agent abstained/i)).toBeInTheDocument();
  });

  it("collapses groups with defaultExpanded=false", () => {
    const grouped = {
      ...view.evidence,
      groups: [
        { ...view.evidence.groups[0], defaultExpanded: false, id: "post_burst" as const, title: "post-burst" },
      ],
    };
    const { container } = render(<PulseEvidenceList evidence={grouped} density="full" />);
    expect(container.querySelector("[data-group-id='post_burst'][data-expanded='false']")).not.toBeNull();
    // body rows should not be rendered when collapsed
    expect(container.querySelectorAll("[data-evidence-row]")).toHaveLength(0);
  });
});
```

- [ ] **Step 2: Run the test to confirm it fails**

```bash
cd web && pnpm test -- --run src/features/signal-lab/ui/PulseDetail/PulseEvidenceList.test.tsx
```

Expected: FAIL — module not found.

- [ ] **Step 3: Implement `PulseEvidenceList.tsx`**

```tsx
import { useMemo, useState } from "react";

import type {
  EvidenceAuthorChip,
  EvidenceGroup,
  EvidenceRow,
  EvidenceView,
} from "../../model/pulseDetail";

import styles from "./PulseEvidenceList.module.css";

type Props = {
  evidence: EvidenceView;
  density: "full" | "compact";
};

type ViewTab = "all" | "cited";

export function PulseEvidenceList({ evidence, density }: Props) {
  const [view, setView] = useState<ViewTab>("all");
  const [handleFilter, setHandleFilter] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<Record<string, boolean>>(() =>
    Object.fromEntries(evidence.groups.map((g) => [g.id, g.defaultExpanded])),
  );

  const filteredGroups = useMemo(() => {
    return evidence.groups
      .map((group) => ({
        ...group,
        rows: group.rows.filter((row) => {
          if (view === "cited" && !row.cited) return false;
          if (handleFilter && row.handle !== handleFilter) return false;
          return true;
        }),
      }))
      .filter((group) => group.rows.length > 0);
  }, [evidence.groups, view, handleFilter]);

  return (
    <section className={styles.section} data-density={density} aria-label="evidence events">
      <header className={styles.head}>
        <h2 className={styles.title}>
          evidence events · {evidence.totalCount} source / {evidence.citedCount} agent-cited
        </h2>
      </header>

      {evidence.abstainCallout ? (
        <p className={styles.callout}>{evidence.abstainCallout}</p>
      ) : null}

      <div className={styles.toolbar}>
        <div className={styles.tabs}>
          <button
            type="button"
            className={styles.tab}
            data-active={view === "all" ? "true" : "false"}
            onClick={() => setView("all")}
          >
            ● all {evidence.totalCount}
          </button>
          <button
            type="button"
            className={styles.tab}
            data-active={view === "cited" ? "true" : "false"}
            disabled={evidence.citedCount === 0}
            onClick={() => setView("cited")}
          >
            ★ cited {evidence.citedCount}
          </button>
        </div>
        {evidence.authorChips.length > 0 ? (
          <div className={styles.chips}>
            {evidence.authorChips.map((chip) => (
              <button
                key={chip.handle}
                type="button"
                className={styles.chip}
                data-active={handleFilter === chip.handle ? "true" : "false"}
                data-tag={chip.authorTag}
                onClick={() =>
                  setHandleFilter((current) => (current === chip.handle ? null : chip.handle))
                }
              >
                @{chip.handle} {chip.postCount}
              </button>
            ))}
            {evidence.totalUniqueAuthors > evidence.authorChips.length ? (
              <span className={styles.chipMore}>
                +{evidence.totalUniqueAuthors - evidence.authorChips.length} more
              </span>
            ) : null}
          </div>
        ) : null}
      </div>

      <div className={styles.groups}>
        {filteredGroups.map((group) => (
          <GroupBlock
            key={group.id}
            group={group}
            isExpanded={expanded[group.id] ?? group.defaultExpanded}
            onToggle={() =>
              setExpanded((prev) => ({ ...prev, [group.id]: !(prev[group.id] ?? group.defaultExpanded) }))
            }
          />
        ))}
      </div>

      {evidence.concentration.segments.length > 1 ? (
        <ConcentrationBar concentration={evidence.concentration} />
      ) : null}
    </section>
  );
}

function GroupBlock({
  group,
  isExpanded,
  onToggle,
}: {
  group: EvidenceGroup;
  isExpanded: boolean;
  onToggle: () => void;
}) {
  return (
    <article className={styles.group} data-group-id={group.id} data-expanded={isExpanded ? "true" : "false"}>
      <button type="button" className={styles.groupHead} onClick={onToggle}>
        <span className={styles.groupTitle}>
          {isExpanded ? "▾" : "▸"} {group.title}
        </span>
        <span className={styles.groupRange}>{group.rangeLabel}</span>
        <span className={styles.groupStats}>
          {group.rows.length} events · ★ {group.citedCount} cited · {group.uniqueAuthors} authors
        </span>
      </button>
      {isExpanded ? (
        <ul className={styles.rows}>
          {group.rows.map((row) => (
            <RowBlock key={row.eventId} row={row} />
          ))}
        </ul>
      ) : null}
    </article>
  );
}

function RowBlock({ row }: { row: EvidenceRow }) {
  return (
    <li
      className={styles.row}
      data-evidence-row
      data-handle={row.handle}
      data-cited={row.cited ? "true" : "false"}
      data-empty={row.isEmptyBody ? "true" : "false"}
      data-tag={row.authorTag}
    >
      <span className={styles.ts}>{row.timestampLabel}</span>
      <span className={styles.author}>
        <b>@{row.handle}</b>
        <span>
          {row.followers != null ? `${formatFollowers(row.followers)} · ` : ""}
          {row.channel} · {row.action}
          {row.cohortPosition ? ` · ${row.cohortPosition}` : ""}
        </span>
      </span>
      <span className={styles.body}>
        {row.body ? row.body : <em>(empty repost · no body text)</em>}
      </span>
      <span className={styles.star} aria-hidden="true">
        {row.cited ? "★" : ""}
      </span>
    </li>
  );
}

function ConcentrationBar({ concentration }: { concentration: EvidenceView["concentration"] }) {
  return (
    <aside className={styles.concentration} aria-label="author concentration bar">
      <header className={styles.concentrationHead}>
        <span>author concentration · top author share {concentration.topAuthorShare.toFixed(2)}</span>
        <span>{concentration.segments.length} unique authors</span>
      </header>
      <div className={styles.bar} role="img" aria-label="author distribution">
        {concentration.segments.map((segment) => (
          <span
            key={segment.handle}
            className={styles.segment}
            data-tone={segment.tone}
            style={{ flex: segment.count }}
            title={`@${segment.handle} · ${segment.count} posts (${Math.round(segment.share * 100)}%)`}
          />
        ))}
      </div>
      <p className={styles.legend}>
        {concentration.segments.slice(0, 3).map((segment, idx) => (
          <span key={segment.handle} data-tone={segment.tone}>
            {idx > 0 ? " · " : ""}■ @{segment.handle} {segment.count}/{sumCount(concentration)} (
            {Math.round(segment.share * 100)}%)
          </span>
        ))}
        {concentration.segments.length > 3 ? ` · +${concentration.segments.length - 3} more` : ""}
      </p>
    </aside>
  );
}

function sumCount(concentration: EvidenceView["concentration"]): number {
  return concentration.segments.reduce((acc, seg) => acc + seg.count, 0);
}

function formatFollowers(value: number): string {
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}M`;
  if (value >= 1_000) return `${(value / 1_000).toFixed(1)}K`;
  return String(value);
}
```

- [ ] **Step 4: Implement `PulseEvidenceList.module.css`**

```css
.section { display: grid; gap: 8px; padding: 14px 16px; border-bottom: 1px solid var(--line); }
.head { display: flex; justify-content: space-between; align-items: baseline; }
.title { margin: 0; font-family: var(--mono); font-size: 12px; color: var(--bone); text-transform: uppercase; letter-spacing: 0.03em; }

.callout { margin: 0; padding: 8px 12px; border: 1px solid var(--agent-line); background: var(--agent-soft); color: var(--agent-ink); font-family: var(--mono); font-size: 11px; border-radius: var(--radius); }

.toolbar {
  position: sticky;
  top: 0;
  z-index: 4;
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: center;
  padding: 6px 0;
  background: rgba(18,23,19,0.92);
  backdrop-filter: blur(6px);
}
.tabs { display: flex; gap: 6px; }
.tab {
  font-family: var(--mono); font-size: 10px;
  border: 1px solid var(--line); background: var(--void); color: var(--ash);
  padding: 4px 10px; border-radius: 999px; cursor: pointer;
}
.tab[data-active="true"] { border-color: var(--opportunity-line-strong); background: var(--opportunity-soft); color: var(--opportunity-ink); }
.tab[disabled] { opacity: 0.4; cursor: not-allowed; }

.chips { display: flex; gap: 6px; flex-wrap: wrap; }
.chip {
  font-family: var(--mono); font-size: 10px;
  border: 1px solid var(--line); background: var(--void); color: var(--ash);
  padding: 4px 8px; border-radius: 999px; cursor: pointer;
}
.chip[data-active="true"] { border-color: var(--info-line-strong); background: var(--info-soft); color: var(--info-ink); }
.chip[data-tag="spam_suspect"] { color: var(--risk-ink); }
.chip[data-tag="kol_signal"] { color: var(--opportunity-ink); }
.chip[data-tag="watched"] { color: var(--health-ink); }
.chipMore { font-family: var(--mono); font-size: 10px; color: var(--dim); padding: 4px 8px; }

.groups { display: grid; gap: 6px; }
.group { border: 1px solid var(--line-soft); border-radius: var(--radius); }
.groupHead {
  display: grid;
  grid-template-columns: 1fr auto auto;
  gap: 12px;
  align-items: baseline;
  padding: 8px 10px;
  width: 100%;
  background: rgba(18,23,19,0.55);
  border: 0;
  cursor: pointer;
  color: inherit;
  text-align: left;
}
.groupHead:hover { background: rgba(18,23,19,0.85); }
.groupTitle { font-family: var(--mono); font-size: 11px; color: var(--bone); text-transform: uppercase; letter-spacing: 0.02em; }
.groupRange { font-family: var(--mono); font-size: 10px; color: var(--ash); }
.groupStats { font-family: var(--mono); font-size: 10px; color: var(--dim); }

.rows { list-style: none; margin: 0; padding: 6px 10px 10px; display: grid; gap: 4px; }
.row {
  display: grid;
  grid-template-columns: 100px 160px 1fr 24px;
  gap: 10px;
  align-items: baseline;
  border: 1px solid var(--line);
  border-radius: var(--radius);
  background: rgba(7,9,8,0.62);
  padding: 7px 10px;
}
.row[data-cited="true"] { border-color: var(--agent-line); background: var(--agent-soft); }
.row[data-empty="true"] { opacity: 0.62; }
.ts { font-family: var(--mono); font-size: 10px; color: var(--dim); }
.author { display: grid; gap: 2px; min-width: 0; }
.author b { font-family: var(--mono); font-size: 11px; color: var(--bone); overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.author span { font-family: var(--mono); font-size: 9px; color: var(--dim); }
.row[data-tag="spam_suspect"] .author span { color: var(--risk-ink); }
.row[data-tag="kol_signal"] .author span { color: var(--opportunity-ink); }
.row[data-tag="watched"] .author span { color: var(--health-ink); }
.body { font-family: var(--sans); font-size: 12px; color: var(--bone-2); line-height: 1.4; overflow: hidden; text-overflow: ellipsis; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; }
.body em { color: var(--dim); font-style: italic; }
.star { font-family: var(--mono); font-size: 14px; color: var(--agent-ink); text-align: right; }

.concentration { margin-top: 6px; border: 1px solid var(--risk-line-strong); border-radius: var(--radius); padding: 9px 11px; background: var(--risk-soft); display: grid; gap: 6px; }
.concentrationHead { display: flex; justify-content: space-between; font-family: var(--mono); font-size: 10px; color: var(--risk-ink); text-transform: uppercase; }
.bar { display: flex; gap: 2px; height: 18px; }
.segment { height: 100%; border-radius: 2px; background: var(--info); }
.segment[data-tone="risk"] { background: var(--risk); }
.segment[data-tone="opportunity"] { background: var(--opportunity); }
.segment[data-tone="health"] { background: var(--health); }
.segment[data-tone="info"] { background: var(--info); }
.legend { margin: 0; font-family: var(--mono); font-size: 10px; color: var(--ash); }
.legend span[data-tone="risk"] { color: var(--risk-ink); }
.legend span[data-tone="opportunity"] { color: var(--opportunity-ink); }
.legend span[data-tone="health"] { color: var(--health-ink); }
.legend span[data-tone="info"] { color: var(--info-ink); }
```

- [ ] **Step 5: Run tests, lint, typecheck**

```bash
cd web && pnpm test -- --run src/features/signal-lab/ui/PulseDetail/PulseEvidenceList.test.tsx && pnpm lint && pnpm typecheck
```

Expected: green.

- [ ] **Step 6: Commit**

```bash
git add web/src/features/signal-lab/ui/PulseDetail/PulseEvidenceList.*
git commit -m "Add PulseEvidenceList with toolbar, groups, and concentration bar"
```

---

## Task 14: Frontend — `PulseAgentRail` component (mismatch + 3 stages + replay)

**Files:**
- Create: `web/src/features/signal-lab/ui/PulseDetail/PulseAgentRail.tsx`
- Create: `web/src/features/signal-lab/ui/PulseDetail/PulseAgentRail.module.css`
- Create: `web/src/features/signal-lab/ui/PulseDetail/PulseAgentRail.test.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { tittyPulseFixture, tittySourceEventsFixture, TITTY_NOW_MS } from "../../test/fixtures";
import { buildPulseDetailView } from "../../model/pulseDetail";

import { PulseAgentRail } from "./PulseAgentRail";

afterEach(() => cleanup());

const view = buildPulseDetailView({
  item: tittyPulseFixture,
  sourceEvents: tittySourceEventsFixture,
  now: TITTY_NOW_MS,
});

describe("PulseAgentRail", () => {
  it("renders mismatch banner for high gate / low agent", () => {
    render(<PulseAgentRail agent={view.agent} density="full" />);
    expect(screen.getByText(/score gate/i)).toBeInTheDocument();
    expect(screen.getByText(/agent:.*0\.35/i)).toBeInTheDocument();
  });

  it("renders all 3 stage cards", () => {
    const { container } = render(<PulseAgentRail agent={view.agent} density="full" />);
    expect(container.querySelector("[data-stage='analyst']")).not.toBeNull();
    expect(container.querySelector("[data-stage='critic']")).not.toBeNull();
    expect(container.querySelector("[data-stage='judge']")).not.toBeNull();
  });

  it("shows critic ceiling delta from analyst", () => {
    render(<PulseAgentRail agent={view.agent} density="full" />);
    const critic = screen.getByTestId("stage-critic");
    expect(within(critic).getByText(/0\.45/)).toBeInTheDocument();
    expect(within(critic).getByText(/↓/)).toBeInTheDocument();
  });

  it("renders replay versions in collapsed details", () => {
    render(<PulseAgentRail agent={view.agent} density="full" />);
    expect(screen.getByText(/pulse-decision-harness-v1/)).toBeInTheDocument();
    expect(screen.getByText(/pulse-run:/)).toBeInTheDocument();
  });

  it("shows research-only gate variant when kind=research_only", () => {
    const research = {
      ...view.agent,
      kind: "research_only" as const,
      analyst: null,
      critic: null,
      judge: null,
      researchOnlyGate: { status: "ok", abstainReason: "no_target_resolved" },
    };
    const { container } = render(<PulseAgentRail agent={research} density="full" />);
    expect(container.querySelector("[data-stage='research_only_gate']")).not.toBeNull();
    expect(container.querySelector("[data-stage='analyst']")).toBeNull();
  });

  it("compact density collapses stages into accordion with judge expanded", () => {
    const { container } = render(<PulseAgentRail agent={view.agent} density="compact" />);
    expect(container.querySelector("[data-density='compact']")).not.toBeNull();
    const analyst = container.querySelector("[data-stage='analyst']");
    expect(analyst?.getAttribute("data-collapsed")).toBe("true");
    const judge = container.querySelector("[data-stage='judge']");
    expect(judge?.getAttribute("data-collapsed")).toBe("false");
  });
});
```

- [ ] **Step 2: Run the test to confirm it fails**

```bash
cd web && pnpm test -- --run src/features/signal-lab/ui/PulseDetail/PulseAgentRail.test.tsx
```

Expected: FAIL.

- [ ] **Step 3: Implement `PulseAgentRail.tsx`**

```tsx
import { useState } from "react";

import type {
  AgentRailView,
  AnalystView,
  CriticView,
  JudgeView,
} from "../../model/pulseDetail";

import styles from "./PulseAgentRail.module.css";

type Props = {
  agent: AgentRailView;
  density: "full" | "compact";
};

export function PulseAgentRail({ agent, density }: Props) {
  return (
    <aside className={styles.rail} data-density={density} aria-label="agent decision rail">
      <header className={styles.head}>
        <h2 className={styles.title}>agent decision rail</h2>
        <span className={styles.meta}>
          {agent.model} · {agent.kind === "stages" ? "3 stages" : "gate-only"} ·{" "}
          {(agent.totalLatencyMs / 1000).toFixed(1)}s
        </span>
      </header>

      {agent.mismatch ? (
        <section className={styles.mismatch} aria-label="gate-vs-agent mismatch">
          <p className={styles.kicker}>gate vs agent · disagreement</p>
          <p className={styles.mismatchRow}>
            <span className={styles.lhs}>{agent.mismatch.gateLabel}</span>{" "}
            <span className={styles.arrow}>→</span>{" "}
            <span className={styles.rhs}>{agent.mismatch.agentLabel}</span>
          </p>
          <p className={styles.mismatchNote}>{agent.mismatch.note}</p>
        </section>
      ) : null}

      {agent.kind === "research_only" && agent.researchOnlyGate ? (
        <article className={styles.stage} data-stage="research_only_gate">
          <header className={styles.stageHead}>
            <strong>pre-LLM gate (deterministic)</strong>
            <span className={styles.meta}>status {agent.researchOnlyGate.status}</span>
          </header>
          <p className={styles.summary}>
            abstain_reason: <code>{agent.researchOnlyGate.abstainReason || "(unset)"}</code>
          </p>
        </article>
      ) : (
        <>
          <StageBlock
            id="analyst"
            heading="stage 1 · analyst"
            stage={agent.analyst}
            density={density}
            initiallyCollapsed={density === "compact"}
            renderBody={(s) => <AnalystBody analyst={s} />}
          />
          <StageBlock
            id="critic"
            heading="stage 2 · critic"
            stage={agent.critic}
            density={density}
            initiallyCollapsed={density === "compact"}
            renderBody={(s) => <CriticBody critic={s} />}
          />
          <StageBlock
            id="judge"
            heading="stage 3 · judge · final"
            stage={agent.judge}
            density={density}
            initiallyCollapsed={false /* judge always default-open */}
            renderBody={(s) => <JudgeBody judge={s} />}
          />
        </>
      )}

      <details className={styles.replay}>
        <summary>replay · versions · raw payloads</summary>
        <dl className={styles.versions}>
          <Row label="pulse_version" value={agent.replay.pulseVersion} />
          <Row label="gate_version" value={agent.replay.gateVersion} />
          <Row label="prompt_version" value={agent.replay.promptVersion} />
          <Row label="schema_version" value={agent.replay.schemaVersion} />
          <Row label="run_id" value={agent.replay.runId} />
          <Row label="candidate_id" value={agent.replay.candidateId} />
        </dl>
      </details>
    </aside>
  );
}

function StageBlock<S extends AnalystView | CriticView | JudgeView>({
  id,
  heading,
  stage,
  density,
  initiallyCollapsed,
  renderBody,
}: {
  id: string;
  heading: string;
  stage: S;
  density: "full" | "compact";
  initiallyCollapsed: boolean;
  renderBody: (stage: NonNullable<S>) => JSX.Element;
}) {
  const [collapsed, setCollapsed] = useState(initiallyCollapsed);
  return (
    <article
      className={styles.stage}
      data-stage={id}
      data-collapsed={collapsed ? "true" : "false"}
      data-testid={`stage-${id}`}
    >
      <button
        type="button"
        className={styles.stageHead}
        onClick={() => setCollapsed((v) => !v)}
        aria-expanded={!collapsed}
      >
        <strong>{collapsed && density === "compact" ? `▸ ${heading}` : heading}</strong>
        <span className={styles.meta}>
          {stage ? `${(stage.latencyMs / 1000).toFixed(1)}s · ${stage.model} · ${stage.status}` : "skipped"}
        </span>
      </button>
      {!collapsed && stage ? renderBody(stage as NonNullable<S>) : null}
      {!stage ? <p className={styles.skipped}>(stage skipped or unavailable)</p> : null}
    </article>
  );
}

function AnalystBody({ analyst }: { analyst: NonNullable<AnalystView> }) {
  return (
    <>
      <div className={styles.kpis}>
        <span className={styles.kpi}>
          recommendation <b>{analyst.recommendation}</b>
        </span>
        <span className={styles.kpi}>
          conf <b data-tone="info">{formatConf(analyst.confidence)}</b>
        </span>
      </div>
      <p className={styles.summary}>{analyst.summary || "(no summary)"}</p>
      <p className={styles.subLabel}>evidence ({analyst.evidence.length})</p>
      <ul className={styles.list}>
        {analyst.evidence.length > 0 ? (
          analyst.evidence.map((entry, idx) => <li key={idx}>{entry}</li>)
        ) : (
          <li className={styles.empty}>(no entries)</li>
        )}
      </ul>
    </>
  );
}

function CriticBody({ critic }: { critic: NonNullable<CriticView> }) {
  return (
    <>
      <div className={styles.kpis}>
        <span className={styles.kpi}>
          should_abstain <b>{critic.shouldAbstain ? "true" : "false"}</b>
        </span>
        <span className={styles.kpi}>
          confidence ceiling <b data-tone="warn">{formatConf(critic.confidenceCeiling)}</b>
          {critic.ceilingDeltaFromAnalyst != null ? (
            <span className={styles.delta}> ↓ {Math.abs(critic.ceilingDeltaFromAnalyst).toFixed(2)}</span>
          ) : null}
        </span>
      </div>
      <p className={styles.subLabel}>weaknesses ({critic.weaknesses.length})</p>
      <ul className={styles.list} data-tone="warn">
        {critic.weaknesses.length > 0
          ? critic.weaknesses.map((w, idx) => <li key={idx}>{w}</li>)
          : <li className={styles.empty}>(no entries)</li>}
      </ul>
      <p className={styles.subLabel}>missing-fact impacts ({critic.missingFactImpacts.length})</p>
      <ul className={styles.list} data-tone="risk">
        {critic.missingFactImpacts.length > 0
          ? critic.missingFactImpacts.map((m, idx) => <li key={idx}>{m}</li>)
          : <li className={styles.empty}>(no entries)</li>}
      </ul>
    </>
  );
}

function JudgeBody({ judge }: { judge: NonNullable<JudgeView> }) {
  return (
    <>
      <div className={styles.kpis}>
        <span className={styles.kpi}>route <b data-tone="info">{judge.route}</b></span>
        <span className={styles.kpi}>recommendation <b data-tone="agent">{judge.recommendation}</b></span>
        <span className={styles.kpi}>
          confidence <b data-tone="risk">{formatConf(judge.confidence)}</b>
          {judge.belowCeiling ? <span className={styles.delta}> (under ceiling)</span> : null}
        </span>
        <span className={styles.kpi}>abstain_reason <b>{judge.abstainReason ?? "null"}</b></span>
      </div>
      <p className={styles.summary}>{judge.summary || "(no summary)"}</p>
      <p className={styles.subLabel}>residual risks ({judge.residualRisks.length})</p>
      <ul className={styles.list} data-tone="risk">
        {judge.residualRisks.length > 0
          ? judge.residualRisks.map((r, idx) => <li key={idx}>{r}</li>)
          : <li className={styles.empty}>(no entries)</li>}
      </ul>
      <p className={styles.subLabel}>invalidation conditions ({judge.invalidationConditions.length})</p>
      <ul className={styles.list} data-tone="warn">
        {judge.invalidationConditions.length > 0
          ? judge.invalidationConditions.map((c, idx) => <li key={idx}>{c}</li>)
          : <li className={styles.empty}>(no entries)</li>}
      </ul>
    </>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className={styles.version}>
      <dt>{label}</dt>
      <dd>{value}</dd>
    </div>
  );
}

function formatConf(value: number | null): string {
  if (value === null) return "n/a";
  return value.toFixed(2);
}
```

- [ ] **Step 4: Implement `PulseAgentRail.module.css`**

```css
.rail { display: grid; gap: 10px; padding: 16px; background: rgba(7,9,8,0.4); align-content: start; }
.rail[data-density="compact"] {
  border-top: 1px solid var(--line);
  background: rgba(7,9,8,0.55);
}
.head {
  display: flex; justify-content: space-between; align-items: baseline;
  border-bottom: 1px solid var(--line);
  padding-bottom: 10px;
}
.title { margin: 0; font-family: var(--mono); font-size: 12px; color: var(--agent-ink); text-transform: uppercase; letter-spacing: 0.03em; }
.meta { font-family: var(--mono); font-size: 10px; color: var(--dim); }
.kicker { margin: 0; font-family: var(--mono); font-size: 9px; color: var(--dim); text-transform: uppercase; }

.mismatch { border: 1px solid var(--line); border-radius: var(--radius); padding: 9px 11px; background: rgba(7,9,8,0.62); display: grid; gap: 4px; }
.mismatchRow { margin: 0; font-family: var(--mono); font-size: 11px; }
.lhs { color: var(--opportunity-ink); }
.rhs { color: var(--risk-ink); }
.arrow { color: var(--dim); }
.mismatchNote { margin: 0; font-family: var(--sans); font-size: 11px; color: var(--ash); }

.stage { border-left: 3px solid var(--line-strong); padding: 8px 10px; background: rgba(7,9,8,0.62); border-radius: 0 var(--radius) var(--radius) 0; display: grid; gap: 6px; }
.stage[data-stage="analyst"] { border-left-color: var(--info); }
.stage[data-stage="critic"] { border-left-color: var(--opportunity); }
.stage[data-stage="judge"] { border-left-color: var(--agent); }
.stage[data-stage="research_only_gate"] { border-left-color: var(--info); }
.stageHead { display: flex; justify-content: space-between; align-items: baseline; border: 0; background: transparent; color: inherit; padding: 0; cursor: pointer; font: inherit; }
.stageHead strong { font-family: var(--mono); font-size: 11px; color: var(--bone); text-transform: uppercase; letter-spacing: 0.02em; }

.kpis { display: flex; flex-wrap: wrap; gap: 8px; }
.kpi { font-family: var(--mono); font-size: 10px; color: var(--ash); }
.kpi b { color: var(--bone); }
.kpi b[data-tone="info"] { color: var(--info-ink); }
.kpi b[data-tone="warn"] { color: var(--opportunity-ink); }
.kpi b[data-tone="risk"] { color: var(--risk-ink); }
.kpi b[data-tone="agent"] { color: var(--agent-ink); }
.delta { color: var(--dim); margin-left: 4px; }

.summary { margin: 0; font-family: var(--sans); font-size: 12px; color: var(--bone-2); line-height: 1.45; }
.subLabel { margin: 4px 0 0; font-family: var(--mono); font-size: 9px; color: var(--dim); text-transform: uppercase; }
.list { margin: 2px 0 0; padding-left: 16px; font-size: 11px; color: var(--bone-2); display: grid; gap: 3px; }
.list[data-tone="warn"] li { color: var(--opportunity-ink); }
.list[data-tone="risk"] li { color: var(--risk-ink); }
.empty { color: var(--dim); font-style: italic; }
.skipped { margin: 0; font-family: var(--mono); font-size: 10px; color: var(--dim); }

.replay { border-top: 1px solid var(--line); padding-top: 10px; margin-top: 4px; }
.replay summary { cursor: pointer; font-family: var(--mono); font-size: 10px; color: var(--ash); text-transform: uppercase; }
.versions { display: grid; gap: 4px; margin: 8px 0 0; }
.version { display: grid; grid-template-columns: 130px 1fr; gap: 8px; font-family: var(--mono); font-size: 10px; color: var(--ash); }
.version dt { margin: 0; color: var(--dim); }
.version dd { margin: 0; color: var(--bone); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
```

- [ ] **Step 5: Run tests, lint, typecheck**

```bash
cd web && pnpm test -- --run src/features/signal-lab/ui/PulseDetail/PulseAgentRail.test.tsx && pnpm lint && pnpm typecheck
```

Expected: green.

- [ ] **Step 6: Commit**

```bash
git add web/src/features/signal-lab/ui/PulseDetail/PulseAgentRail.*
git commit -m "Add PulseAgentRail with mismatch banner, 3 stages, and replay"
```

---

## Task 15: Frontend — `PulseDetailView` orchestrator + integration test

**Files:**
- Create: `web/src/features/signal-lab/ui/PulseDetail/PulseDetailView.tsx`
- Create: `web/src/features/signal-lab/ui/PulseDetail/PulseDetailView.module.css`
- Create: `web/src/features/signal-lab/ui/PulseDetail/PulseDetailView.test.tsx`
- Create: `web/src/features/signal-lab/ui/PulseDetail/index.ts`

**Background:** Pure composition. Accepts the raw `SignalPulseItem`, `SocialEventDetail[]`, `density`, `now`, and an `actions` slot (back link / venue links). Calls `buildPulseDetailView` once, passes slices to children. No routing, no data fetching.

- [ ] **Step 1: Write the failing integration test**

```tsx
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { tittyPulseFixture, tittySourceEventsFixture, TITTY_NOW_MS } from "../../test/fixtures";

import { PulseDetailView } from "./PulseDetailView";

afterEach(() => cleanup());

describe("PulseDetailView · TITTY full mode", () => {
  it("renders all 6 regions with real data", () => {
    const { container } = render(
      <PulseDetailView
        item={tittyPulseFixture}
        sourceEvents={tittySourceEventsFixture}
        density="full"
        now={TITTY_NOW_MS}
        actions={<a href="/signal-lab">← back to queue</a>}
      />,
    );

    // Hero
    expect(screen.getByText("$TITTY")).toBeInTheDocument();
    expect(screen.getByText(/gate-agent mismatch/i)).toBeInTheDocument();

    // Timeline
    expect(container.querySelector("[data-node='market_anchor']")).not.toBeNull();

    // Families
    expect(container.querySelector("[data-family='social_heat']")).not.toBeNull();

    // Market
    expect(container.querySelector("[data-metric='liq']")?.getAttribute("data-tone")).toBe("warn");

    // Evidence
    expect(container.querySelectorAll("[data-evidence-row]")).toHaveLength(5);

    // Agent
    expect(container.querySelector("[data-stage='judge']")).not.toBeNull();

    // back-to-queue link rendered via actions slot
    expect(screen.getByText("← back to queue")).toBeInTheDocument();
  });
});

describe("PulseDetailView · compact mode", () => {
  it("forwards density to all regions", () => {
    const { container } = render(
      <PulseDetailView
        item={tittyPulseFixture}
        sourceEvents={tittySourceEventsFixture}
        density="compact"
        now={TITTY_NOW_MS}
        actions={null}
      />,
    );
    const compactSections = container.querySelectorAll("[data-density='compact']");
    expect(compactSections.length).toBeGreaterThanOrEqual(5);
  });
});
```

- [ ] **Step 2: Run the test to confirm it fails**

```bash
cd web && pnpm test -- --run src/features/signal-lab/ui/PulseDetail/PulseDetailView.test.tsx
```

Expected: FAIL.

- [ ] **Step 3: Implement `PulseDetailView.tsx`**

```tsx
import type { ReactNode } from "react";

import type { SignalPulseItem, SocialEventDetail } from "@lib/types";

import { buildPulseDetailView } from "../../model/pulseDetail";

import { PulseAgentRail } from "./PulseAgentRail";
import styles from "./PulseDetailView.module.css";
import { PulseEvidenceList } from "./PulseEvidenceList";
import { PulseFactorFamilies } from "./PulseFactorFamilies";
import { PulseHero } from "./PulseHero";
import { PulseMarketContext } from "./PulseMarketContext";
import { PulseTimeline } from "./PulseTimeline";

type Props = {
  item: SignalPulseItem;
  sourceEvents: SocialEventDetail[];
  density: "full" | "compact";
  now: number;
  actions: ReactNode;
};

export function PulseDetailView({ item, sourceEvents, density, now, actions }: Props) {
  const view = buildPulseDetailView({ item, sourceEvents, now });
  return (
    <article
      className={styles.case}
      data-density={density}
      aria-label={`Pulse detail case ${view.hero.subject.symbol}`}
    >
      <PulseHero hero={view.hero} density={density} actions={actions} />

      <div className={styles.body}>
        <main className={styles.main}>
          <PulseTimeline timeline={view.timeline} density={density} />
          <PulseFactorFamilies families={view.families} density={density} />
          <PulseMarketContext market={view.market} density={density} />
          <PulseEvidenceList evidence={view.evidence} density={density} />
        </main>
        <PulseAgentRail agent={view.agent} density={density} />
      </div>
    </article>
  );
}
```

- [ ] **Step 4: Implement `PulseDetailView.module.css`**

```css
.case {
  display: grid;
  border: 1px solid var(--line);
  border-radius: var(--radius);
  background:
    linear-gradient(180deg, rgba(241,234,214,0.032), rgba(241,234,214,0)), var(--slab);
  box-shadow: var(--shadow-elevated);
  overflow: hidden;
  min-width: 0;
}

.body { display: grid; grid-template-columns: 1.55fr 1fr; }
.case[data-density="compact"] .body { grid-template-columns: 1fr; }

.main { border-right: 1px solid var(--line); min-width: 0; display: grid; }
.case[data-density="compact"] .main { border-right: 0; }
```

- [ ] **Step 5: Write `index.ts`**

```typescript
export { PulseDetailView } from "./PulseDetailView";
export type { PulseDetailViewModel } from "../../model/pulseDetail";
```

- [ ] **Step 6: Run tests, lint, typecheck**

```bash
cd web && pnpm test -- --run src/features/signal-lab/ui/PulseDetail/ && pnpm lint && pnpm typecheck
```

Expected: green.

- [ ] **Step 7: Commit**

```bash
git add web/src/features/signal-lab/ui/PulseDetail/PulseDetailView.* web/src/features/signal-lab/ui/PulseDetail/index.ts
git commit -m "Add PulseDetailView orchestrator composing hero / timeline / families / market / evidence / rail"
```

---

## Task 16: Frontend — Route topology change (flatten `/signal-lab/pulse/:id`)

**Files:**
- Modify: `web/src/routes/AppRoutes.tsx`
- Modify: `web/src/routes/signal-lab.pulse.route.tsx`
- Modify: `web/src/features/signal-lab/ui/SignalLabPage.tsx`

**Background:** Today `pulse/:candidateId` is a child of the `signal-lab` route, rendered inside `SignalLabPage`'s `<Outlet />`. We hoist it to a sibling of `signal-lab` so the dedicated route renders standalone. SignalLabPage drops the `isPulseRoute` branch and the queue right-pane always renders inline `PulseDetailView` (compact density) when an item is selected.

- [ ] **Step 1: Rewrite `signal-lab.pulse.route.tsx`**

Replace the entire file with:

```tsx
import { getAuthToken } from "@lib/api/client";
import { PanelSkeleton, RouteStatePanel } from "@shared/ui/RemoteState";
import { Link, useParams } from "react-router-dom";

import { useSignalPulseCandidate, useSourceEvents } from "../features/signal-lab/api/useSignalPulseQueries";
import { PulseDetailView } from "../features/signal-lab/ui/PulseDetail";

export function SignalLabPulseRoute() {
  const { candidateId } = useParams<{ candidateId: string }>();
  const token = getAuthToken() ?? "";
  const pulseQuery = useSignalPulseCandidate({ token, candidateId: candidateId ?? null });
  const ids = pulseQuery.data?.data?.source_event_ids ?? [];
  const eventsQuery = useSourceEvents({ token, ids });

  if (pulseQuery.isLoading) {
    return <PanelSkeleton label="loading pulse detail" />;
  }
  if (pulseQuery.isError || !pulseQuery.data?.data) {
    return (
      <RouteStatePanel title="Pulse 不存在或已被屏蔽">
        检查链接，或回到 Signal Pulse 队列选择其他候选。
      </RouteStatePanel>
    );
  }
  return (
    <section style={{ padding: "16px", maxWidth: 1320, margin: "0 auto" }}>
      <PulseDetailView
        item={pulseQuery.data.data}
        sourceEvents={eventsQuery.data ?? []}
        density="full"
        now={Date.now()}
        actions={<Link to="/signal-lab">← back to queue</Link>}
      />
    </section>
  );
}
```

- [ ] **Step 2: Hoist the route in `AppRoutes.tsx`**

Change the existing `Route path="signal-lab"` block in `web/src/routes/AppRoutes.tsx` (around line 240). Remove the nested child route, and add a new top-level sibling route under the same `<Route element={cockpitShellElement}>`:

```tsx
        <Route
          path="signal-lab"
          element={
            <SignalLabRoute
              selectedAccountEventId={selection.selectedAccountEventId}
              overviewData={signalLabOverviewData}
              onSelectAccountEvent={selection.selectAccountEvent}
            />
          }
        />
        <Route path="signal-lab/pulse/:candidateId" element={<SignalLabPulseRoute />} />
```

(Note: the `<Route path="signal-lab/pulse/:candidateId" />` is now a sibling of `signal-lab`, not nested.)

- [ ] **Step 3: Strip the isPulseRoute branch from `SignalLabPage.tsx`**

In `web/src/features/signal-lab/ui/SignalLabPage.tsx`:
- Remove the `Outlet` import.
- Remove `signalLab.isPulseRoute` reference.
- Replace the right-pane block with the always-inline inspector:

```tsx
      <aside className="signal-lab-inspector-pane">
        {inlinePulseItem ? (
          <InlinePulseInspector item={inlinePulseItem} token={getAuthToken() ?? ""} />
        ) : (
          <RemoteState.Empty title="No selected Signal Pulse case." />
        )}
      </aside>
```

Add an `InlinePulseInspector` helper to the bottom of the same file:

```tsx
function InlinePulseInspector({
  item,
  token,
}: {
  item: SignalPulseItem;
  token: string;
}) {
  const eventsQuery = useSourceEvents({ token, ids: item.source_event_ids });
  return (
    <PulseDetailView
      item={item}
      sourceEvents={eventsQuery.data ?? []}
      density="compact"
      now={Date.now()}
      actions={
        <Link to={`/signal-lab/pulse/${encodeURIComponent(item.candidate_id)}`}>
          Open in full view ↗
        </Link>
      }
    />
  );
}
```

Add imports at top:

```tsx
import { getAuthToken } from "@lib/api/client";
import { useSourceEvents } from "../api/useSignalPulseQueries";
import { PulseDetailView } from "./PulseDetail";
import type { SignalPulseItem } from "@lib/types";
```

- [ ] **Step 4: Typecheck and run all signal-lab tests**

```bash
cd web && pnpm typecheck && pnpm test -- --run src/features/signal-lab
```

Expected: green.

- [ ] **Step 5: Manual smoke**

Start dev server:

```bash
cd web && pnpm dev
```

Open:
- `http://localhost:5173/signal-lab` — queue renders, click a candidate → inline `PulseDetailView` (compact) shows in right pane
- `http://localhost:5173/signal-lab/pulse/pulse-fa2a12fedd9332271732110ed8bd7b1b49065282` — standalone full-mode page

If both work end-to-end (Hero / Timeline / Families / Market / Evidence / Rail visible), continue.

- [ ] **Step 6: Commit**

```bash
git add web/src/routes/AppRoutes.tsx web/src/routes/signal-lab.pulse.route.tsx web/src/features/signal-lab/ui/SignalLabPage.tsx
git commit -m "Hoist /signal-lab/pulse/:id to top-level route and wire inline compact mode"
```

---

## Task 17: Frontend — Hard cut: delete `SignalLabInspector`, `pulseCase`, legacy CSS

**Files:**
- Delete: `web/src/features/signal-lab/ui/SignalLabInspector.tsx`
- Delete: `web/src/features/signal-lab/ui/SignalLabInspector.test.tsx`
- Delete: `web/src/features/signal-lab/ui/SignalLabPulse.tsx` (verify unused first)
- Delete: `web/src/features/signal-lab/ui/PulseDetailPage.tsx`
- Delete: `web/src/features/signal-lab/model/pulseCase.ts`
- Modify: `web/src/features/signal-lab/ui/signalLab.module.css`
- Modify: `web/src/features/signal-lab/index.ts`

- [ ] **Step 1: Verify nothing imports the soon-to-delete files**

```bash
grep -rn "SignalLabInspector\|pulseCase\|SignalLabPulse\b\|PulseDetailPage" web/src --include="*.tsx" --include="*.ts"
```

Expected: any remaining matches should be the new code or the test you're deleting. Adjust imports if anything else surfaces.

- [ ] **Step 2: Delete legacy files**

```bash
git rm web/src/features/signal-lab/ui/SignalLabInspector.tsx \
       web/src/features/signal-lab/ui/SignalLabInspector.test.tsx \
       web/src/features/signal-lab/ui/PulseDetailPage.tsx \
       web/src/features/signal-lab/model/pulseCase.ts
```

For `SignalLabPulse.tsx`: confirm it's unreferenced and delete:

```bash
grep -rn "SignalLabPulse\b" web/src --include="*.tsx" --include="*.ts"
# If only its own file appears, delete it:
git rm web/src/features/signal-lab/ui/SignalLabPulse.tsx
```

- [ ] **Step 3: Strip `signal-pulse-*` classes from `signalLab.module.css`**

```bash
grep -n "signal-pulse-\|pulse-debug" web/src/features/signal-lab/ui/signalLab.module.css
```

Remove every block that begins with one of those selectors. Use editor (Edit tool) to delete each block precisely. Verify:

```bash
grep -n "signal-pulse-\|pulse-debug" web/src/features/signal-lab/ui/signalLab.module.css
```

Expected: no matches.

- [ ] **Step 4: Update `signal-lab/index.ts` barrel**

```typescript
export { SignalLabPage } from "./ui/SignalLabPage";
export { useSignalLabPage } from "./useSignalLabPage";
export { PulseDetailView } from "./ui/PulseDetail";
export { useSignalPulseCandidate, useSignalPulseList, useSourceEvents } from "./api/useSignalPulseQueries";
```

(Removed exports: `SignalLabInspector`, `buildPulseCaseView`, etc.)

- [ ] **Step 5: Run typecheck + lint + full test suite**

```bash
cd web && pnpm typecheck && pnpm lint && pnpm test
```

Expected: all green. If any error references the removed exports, update the offending import.

- [ ] **Step 6: Verify no signal-pulse globals leak**

```bash
grep -rn "signal-pulse-case\|signal-pulse-memo\|pulse-debug" web/src
```

Expected: 0 matches.

- [ ] **Step 7: Verify the hard-cut guarantee — components stay decoupled**

```bash
grep -rn "react-router-dom\|@tanstack/react-query\|getApi\b" web/src/features/signal-lab/ui/PulseDetail
```

Expected: 0 matches (PulseDetail components must be pure presentation — routing and data fetching belong to the route container and the inline wrapper).

- [ ] **Step 8: Commit**

```bash
git add -u
git commit -m "Delete legacy SignalLabInspector and signal-pulse-* CSS"
```

---

## Task 18: E2E — `pulse-detail.spec.ts`

**Files:**
- Create: `web/e2e/golden-paths/pulse-detail.spec.ts`
- Modify: `web/e2e/support/mockApi.ts`

**Background:** Cover both render paths (dedicated route + queue inline compact) with mocked API responses including `stages` and `/api/social-events/by-ids`.

- [ ] **Step 1: Extend `mockApi.ts` with stages and by-ids**

```bash
grep -n "signal-lab/pulse\|social-events" web/e2e/support/mockApi.ts
```

Inspect the existing mock for `/api/signal-lab/pulse/...`. Extend its response to include a `stages` object matching the schema from Task 5. Then add a new route handler:

```typescript
await page.route("**/api/social-events/by-ids*", async (route) => {
  await route.fulfill({
    contentType: "application/json",
    body: JSON.stringify({
      ok: true,
      data: {
        events: [
          {
            event_id: "evt-1",
            timestamp_ms: 1778723098000,
            source_provider: "gmgn",
            channel: "twitter_monitor_basic",
            action: "tweet",
            author_handle: "moontoklisting",
            author_name: "Moontok Listing Alert",
            author_followers: 48771,
            author_watched: false,
            text_clean: "TITTY listed at MC $94K · LIQ $27K",
            canonical_url: null,
          },
        ],
        not_found: [],
      },
    }),
  });
});
```

Plug it into the existing `installMockApi` function.

- [ ] **Step 2: Write the spec**

```typescript
import { expect, test } from "@playwright/test";

import { installMockApi } from "../support/mockApi";

test("dedicated pulse route shows the new redesign with all 6 regions", async ({ page }) => {
  await installMockApi(page);
  await page.goto("/signal-lab/pulse/pulse-fa2a12fedd9332271732110ed8bd7b1b49065282");

  await expect(page.getByText("$TITTY")).toBeVisible();
  await expect(page.getByText(/gate-agent mismatch/i)).toBeVisible();
  await expect(page.locator("[data-node='market_anchor']")).toBeVisible();
  await expect(page.locator("[data-family='social_heat']")).toBeVisible();
  await expect(page.locator("[data-metric='liq']")).toHaveAttribute("data-tone", "warn");
  await expect(page.locator("[data-evidence-row]")).toHaveCount(1);
  await expect(page.locator("[data-stage='judge']")).toBeVisible();
  await expect(page.getByText("← back to queue")).toBeVisible();
});

test("queue inline render uses compact density", async ({ page }) => {
  await installMockApi(page);
  await page.goto("/signal-lab?window=4h&scope=matched");

  await page.getByRole("button", { name: /open pulse case/i }).first().click();
  await expect(page.locator("[data-density='compact']").first()).toBeVisible();
  await expect(page.getByText(/Open in full view/i)).toBeVisible();
});

test("evidence toolbar toggles all vs cited", async ({ page }) => {
  await installMockApi(page);
  await page.goto("/signal-lab/pulse/pulse-fa2a12fedd9332271732110ed8bd7b1b49065282");

  const citedTab = page.getByRole("button", { name: /★ cited/i });
  await citedTab.click();
  await expect(page.locator("[data-evidence-row][data-cited='true']").first()).toBeVisible();
});
```

- [ ] **Step 3: Run the e2e**

```bash
cd web && pnpm test:e2e -- pulse-detail.spec.ts
```

Expected: all 3 tests pass. If they fail because the mock signal-lab list payload doesn't include the candidate, extend `mockApi.ts` accordingly until green.

- [ ] **Step 4: Commit**

```bash
git add web/e2e/golden-paths/pulse-detail.spec.ts web/e2e/support/mockApi.ts
git commit -m "Add pulse-detail e2e covering full and compact modes"
```

---

## Task 19: Final verification

- [ ] **Step 1: Full backend test sweep**

```bash
uv run pytest tests/unit/test_signal_pulse_service.py tests/integration/test_api_http.py -v
```

Expected: all green.

- [ ] **Step 2: Full frontend unit suite**

```bash
cd web && pnpm test -- --run
```

Expected: all green.

- [ ] **Step 3: Typecheck + lint**

```bash
cd web && pnpm typecheck && pnpm lint
```

Expected: clean.

- [ ] **Step 4: Full e2e**

```bash
cd web && pnpm test:e2e
```

Expected: existing golden paths + new `pulse-detail.spec.ts` all pass.

- [ ] **Step 5: Manual smoke against real backend (with a live $TITTY-style pulse)**

```bash
make up                 # or whatever starts the stack locally
open http://localhost:8765/signal-lab/pulse/pulse-fa2a12fedd9332271732110ed8bd7b1b49065282
```

Verify in the browser:
- Hero shows `$TITTY`, `solana`, three+ pills including `gate-agent mismatch` and `market data stale`
- Burst histogram has visible bars near the right edge (peak), no broken rendering
- Timeline `market_anchor` cell has red border (risk tone)
- 4 family cards rendered with scores `91 / 85 / 50 / 0`; semantic + timing show `n/a (missing)` rows
- Market grid: liquidity warn-bordered, volume risk-bordered with `13.5× mcap` subtext, stale notice line below
- 5 evidence rows all marked ★, author chips show `@cache100x 3` / `@moontoklisting 1` / `@qkl2058 1`
- Author concentration bar rendered, cache100x segment is red
- Agent rail: gate-vs-agent mismatch banner; Analyst conf 0.82; Critic ceiling 0.45 with ↓; Judge conf 0.35; replay section lists `pulse-decision-harness-v1` and `pulse-run:7d250fd8...`
- Visit `http://localhost:8765/signal-lab` (no pulse id) → queue + right-pane compact inspector still renders

- [ ] **Step 6: Move the spec to `completed/`**

```bash
git mv docs/superpowers/specs/active/2026-05-14-pulse-detail-redesign-cn.md docs/superpowers/specs/completed/
```

(Only after the user signs off on the manual smoke.)

- [ ] **Step 7: Final commit**

```bash
git add -u
git commit -m "Mark pulse-detail redesign spec complete"
```

- [ ] **Step 8: Plan handoff**

Notify the user the plan is fully executed; reference this plan file for the audit trail.

---

## Self-Review Notes (post-write)

**Spec coverage check:**
- Spec G1 (delete old) — Task 17.
- Spec G2 (shared `PulseDetailView`) — Tasks 9–15.
- Spec G3 (dedicated route flattening + back link) — Task 16.
- Spec G4 (main column order Hero → Timeline → Families → Market → Evidence) — Task 15 orchestrator order.
- Spec G5 (3 agent stages + mismatch) — Task 14.
- Spec G6 (Evidence row schema, grouping, author chips, concentration) — Tasks 7 + 13.
- Spec G7 (absolute UTC time everywhere) — Task 4 + view-model usage in Task 7.
- Spec G8 (abstain / risk_rejected / missing-data use same skeleton) — Tasks 7 (`abstainCallout`, `kind=research_only`) + 13 (callout render) + 14 (research_only_gate variant).
- Spec G9 (1 new endpoint + 1 payload extension; no schema change) — Tasks 1–3.
- Spec G10 (component-level tests + $TITTY snapshot fixture) — Tasks 6 + every component task.

**Type consistency:** `density` is `"full" | "compact"` everywhere. View-model exports `PulseDetailViewModel` consumed by all leaf components. `Tone` union shared from `pulseDetail.ts`.

**Decoupling guarantee:** PulseDetail components never import `react-router-dom`, `@tanstack/react-query`, or `@lib/api/client` — enforced by Task 17 grep check. Route container (`SignalLabPulseRoute`) and inline wrapper (`InlinePulseInspector`) own data fetching and routing.

**Hard-cut:** Old inspector + its CSS + its model file all removed in Task 17, same PR scope.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/active/2026-05-14-pulse-detail-redesign-plan-cn.md`. Two execution options:

1. **Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration. Use `superpowers:subagent-driven-development`.
2. **Inline Execution** — Execute tasks in this session using `superpowers:executing-plans`, batch execution with checkpoints.

Which approach?
