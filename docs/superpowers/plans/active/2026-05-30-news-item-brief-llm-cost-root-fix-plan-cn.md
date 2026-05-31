# News Item Brief LLM Cost Root Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 根治 `news_item_brief` unchanged item 重复 LLM 调用、provider quota retry storm、以及 `brief_input` failed dirty queue 常驻问题。

**Architecture:** 这是 hard cut，不保留 runtime legacy hash fallback。News brief 的唯一身份是 semantic material payload hash；dirty target 只做 wake hint，处理后必须 done/terminalize/evict；provider quota/balance 是共享 execution plane 的 lane/provider backpressure，不是 item-level failure。
Story 是本地 page read-model context，不是 6551/OpenNews provider truth，也不是 `news_item_brief` 的 LLM input identity。

**Tech Stack:** Python 3.13, Pydantic v2, psycopg/PostgreSQL, existing LiteLLM-native `AgentExecutionGateway`, pytest, ruff, existing `worker_queue_terminal_events`.

---

## Owning Spec

- `docs/superpowers/specs/active/2026-05-30-news-item-brief-llm-cost-root-fix-cn.md`

## Hard-Cut Rules

- [ ] Do not keep runtime legacy hash compatibility branches.
- [ ] Do not compare old `request_json.packet` hashes in `_current_brief_is_fresh`.
- [ ] Do not let `fetched_at_ms`, `updated_at_ms`, lease owner, attempt count, dirty target timestamps, run ids, UUIDs, or generated timestamps enter LLM semantic input identity.
- [ ] Do not keep `news_story_projection`, `news_story_updated`, story dirty targets, story API routes, or story read-model schema in the active runtime.
- [ ] Do not write item-level failed current briefs for provider-wide quota/balance/auth/config outages.
- [ ] Do not leave unchanged failed `brief_input` rows in the hot dirty queue forever.
- [ ] Do not add runtime hash backfill or dual-hash compatibility code in this plan; old ready current briefs refresh once under rollout RPM control.

## File Structure

### News Brief Semantic Identity

- Modify: `src/parallax/domains/news_intel/types/news_item_brief.py`
  - Remove `fetched_at_ms` from `NewsItemBriefNewsItem`.
- Modify: `src/parallax/domains/news_intel/services/news_item_brief_input.py`
  - Add `news_item_brief_material_input_payload(packet)` and `news_item_brief_material_input_hash(packet)`.
  - Build `packet.input_hash` from the material payload helper.
- Modify: `src/parallax/domains/news_intel/services/news_item_brief_runtime.py`
  - Use the same material payload helper for `AgentStageSpec.input_payload`.
- Modify: `tests/unit/domains/news_intel/test_news_item_brief_input.py`
  - Prove volatile fetch metadata does not change hash.
- Modify: `tests/unit/domains/news_intel/test_news_item_brief_runtime.py`
  - Prove provider-visible stage payload excludes `fetched_at_ms`.

### Freshness And Candidate Loading

- Modify: `src/parallax/domains/news_intel/repositories/news_repository.py`
  - Remove `items.updated_at_ms`, projection-only `stories.updated_at_ms`, story joins, and story member timestamps from brief `source_updated_at_ms`.
  - Prefer item processed/material timestamps and child material rows.
- Modify: `src/parallax/domains/news_intel/runtime/news_item_brief_worker.py`
  - Make freshness an exact semantic hash + version match.
  - Treat terminal failed current brief as fresh only when its terminal marker and input hash match.
- Modify: `src/parallax/platform/config/settings.py` and `src/parallax/app/runtime/worker_manifest.py`
  - Remove `news_story_projection` and all `news_story_updated` wake inputs.
- Modify: `tests/unit/domains/news_intel/test_news_item_brief_worker.py`
  - Prove volatile source watermark does not trigger provider call.
- Modify: `tests/integration/domains/news_intel/test_news_item_agent_brief_repository.py`
  - Prove pure refetch metadata does not advance material freshness.

### Dirty Target Terminalization

- Modify: `src/parallax/domains/news_intel/repositories/news_projection_dirty_target_repository.py`
  - Add `terminalize_targets(...)` for claimed dirty targets.
  - Delete the hot dirty row and write `worker_queue_terminal_events`.
- Modify: `src/parallax/domains/news_intel/runtime/news_item_brief_worker.py`
  - Do not upsert failed current on retryable provider/model/domain failures.
  - Terminalize after bounded attempts using `attempt_count + attempted_now >= max_attempts`.
  - Upsert failed current only for terminal item-level failure, with `brief_json.terminal = true`.
  - Before provider call, skip provider when the current brief is a matching terminal failure for the same semantic hash.
- Modify: `tests/integration/domains/news_intel/test_news_projection_dirty_target_repository.py`
  - Prove terminalization removes hot row and writes terminal event.
- Modify: `tests/unit/domains/news_intel/test_news_item_brief_worker.py`
  - Prove max-attempt failure terminalizes and unchanged re-enqueue does not call provider.

### Shared Provider Quota Backpressure

- Modify: `src/parallax/platform/agent_execution.py`
  - Add `AgentExecutionErrorClass.QUOTA_EXHAUSTED = "quota_exhausted"`.
- Modify: `src/parallax/integrations/model_execution/execution_gateway.py`
  - Classify balance/quota/auth/config errors from exception type, HTTP code, provider body, and message text.
  - Mark quota/balance/auth/config as `execution_started=False`.
  - Open lane circuit immediately for quota/balance/auth/config classes.
- Modify: `src/parallax/domains/news_intel/runtime/news_item_brief_worker.py`
  - Add quota to no-start backpressure set and `backpressure_quota_exhausted` notes.
- Modify: `src/parallax/domains/narrative_intel/runtime/mention_semantics_worker.py`
  - Add quota to no-start backpressure set.
- Modify: `src/parallax/domains/narrative_intel/runtime/token_discussion_digest_worker.py`
  - Add quota to no-start backpressure set.
- Modify: `src/parallax/domains/pulse_lab/services/pulse_candidate_job_service.py`
  - Add quota to no-start backpressure set and provider cooldown reason.
- Modify: `src/parallax/integrations/model_execution/pulse_decision_agent_client.py`
  - Add quota to stage no-start set.
- Modify: `tests/unit/integrations/model_execution/test_agent_execution_gateway.py`
  - Prove `Insufficient Balance` becomes `QUOTA_EXHAUSTED` and opens circuit.

### Cross-Agent Guardrails

- Modify: `tests/architecture/test_agent_execution_plane_contracts.py`
  - Reject runtime legacy hash fallback names.
  - Reject News brief semantic packet fields that include `fetched_at_ms`.
- Create: `tests/architecture/test_agent_input_identity_contracts.py`
  - Reject known LLM lanes that hash claimed DB rows with lease/attempt metadata.
  - Specifically protect Narrative mention semantics before it is re-enabled.

### Deployment Refresh Policy

- No code changes for historical hash compatibility.
- Rollout controls the one-time refresh cost: keep `news_item_brief` disabled or low-RPM until stale old-hash current rows have either refreshed once or been skipped because their semantic packet already matches.

## Pre-Flight

- [ ] **Step 1: Confirm this is the active hard-cut plan**

Run:

```bash
sed -n '1,120p' docs/superpowers/specs/active/2026-05-30-news-item-brief-llm-cost-root-fix-cn.md
```

Expected: status says hard-cut implementation required; hard-cut rules mention no runtime compatibility and dirty target terminalization.

- [ ] **Step 2: Confirm live config paths before real-data diagnostics**

Run:

```bash
uv run parallax config
```

Expected: `config_path=/Users/qinghuan/.parallax/config.yaml` and `workers_config_path=/Users/qinghuan/.parallax/workers.yaml`; no secret values printed.

- [ ] **Step 3: Capture baseline cost and backlog**

Run:

```bash
uv run parallax ops worker-status
```

Expected: output includes `news_item_brief` queue health. Save due count, running count, and last error buckets in the verification artifact.

- [ ] **Step 4: Run focused baseline tests**

Run:

```bash
uv run pytest \
  tests/unit/domains/news_intel/test_news_item_brief_input.py \
  tests/unit/domains/news_intel/test_news_item_brief_runtime.py \
  tests/unit/domains/news_intel/test_news_item_brief_worker.py \
  tests/unit/integrations/model_execution/test_agent_execution_gateway.py \
  tests/integration/domains/news_intel/test_news_projection_dirty_target_repository.py \
  -q
```

Expected: baseline result is recorded. Existing failures must be listed before implementation.

## Task 1: Failing Tests For Semantic Identity And No Runtime Compatibility

**Files:**
- Modify: `tests/unit/domains/news_intel/test_news_item_brief_input.py`
- Modify: `tests/unit/domains/news_intel/test_news_item_brief_runtime.py`
- Modify: `tests/architecture/test_agent_execution_plane_contracts.py`
- Create: `tests/architecture/test_agent_input_identity_contracts.py`

- [ ] **Step 1: Add packet hash test that ignores `fetched_at_ms`**

Append to `tests/unit/domains/news_intel/test_news_item_brief_input.py`:

```python
def test_packet_hash_ignores_fetched_at_ms() -> None:
    base_item = {
        "news_item_id": "item-fetch-time",
        "title": "BTC ETF flow update",
        "summary": "ETF inflows changed market attention.",
        "body_text": "ETF inflows changed market attention.",
        "canonical_url": "https://example.com/btc-etf-flow",
        "published_at_ms": 1_779_000_000_000,
        "fetched_at_ms": 1_779_000_010_000,
        "content_hash": "sha256:btc-etf-flow",
    }
    first = build_news_item_brief_input_packet(
        item=base_item,
        token_mentions=[],
        fact_candidates=[],
        agent_config=_agent_config(),
    )
    second = build_news_item_brief_input_packet(
        item={**base_item, "fetched_at_ms": 1_779_000_090_000},
        token_mentions=[],
        fact_candidates=[],
        agent_config=_agent_config(),
    )

    assert first.input_hash == second.input_hash
    assert "fetched_at_ms" not in first.model_dump(mode="json")["news_item"]
```

- [ ] **Step 2: Add stage payload test that excludes `fetched_at_ms`**

Append to `tests/unit/domains/news_intel/test_news_item_brief_runtime.py`:

```python
from parallax.domains.news_intel.services.news_item_brief_input import (
    build_news_item_brief_input_packet,
)
from parallax.domains.news_intel.services.news_item_brief_runtime import (
    build_news_item_brief_stage,
)
from parallax.domains.news_intel.types.news_item_brief import NewsItemBriefAgentConfig


def test_stage_payload_uses_material_packet_without_fetch_time() -> None:
    packet = build_news_item_brief_input_packet(
        item={
            "news_item_id": "item-stage",
            "title": "Stage payload",
            "summary": "Stage payload summary.",
            "published_at_ms": 1_779_000_000_000,
            "fetched_at_ms": 1_779_000_010_000,
            "content_hash": "sha256:stage",
        },
        token_mentions=[],
        fact_candidates=[],
        agent_config=NewsItemBriefAgentConfig(
            model="test-model",
            artifact_version_hash="artifact-v1",
            prompt_version="prompt-v1",
            schema_version="schema-v1",
            validator_version="validator-v1",
            guardrail_version="guardrail-v1",
        ),
    )

    stage = build_news_item_brief_stage(packet=packet, run_id="run-1")

    assert stage.input_hash == packet.input_hash
    assert "fetched_at_ms" not in stage.input_payload["news_item"]
```

- [ ] **Step 3: Add architecture guard against runtime legacy hash fallback**

Append to `tests/architecture/test_agent_execution_plane_contracts.py`:

```python
def test_news_item_brief_has_no_runtime_legacy_hash_fallback() -> None:
    forbidden = (
        "legacy_hash",
        "legacy input_hash",
        "request_json.packet",
        "historical packet",
        "old_hash",
    )
    paths = [
        "src/parallax/domains/news_intel/runtime/news_item_brief_worker.py",
        "src/parallax/domains/news_intel/services/news_item_brief_input.py",
    ]
    for path in paths:
        text = Path(path).read_text(encoding="utf-8")
        lowered = text.lower()
        for token in forbidden:
            assert token not in lowered, f"{path} contains runtime compatibility token {token!r}"
```

If `Path` is not already imported in the file, add:

```python
from pathlib import Path
```

- [ ] **Step 4: Add News input identity architecture test**

Create `tests/architecture/test_agent_input_identity_contracts.py`:

```python
from __future__ import annotations

from pathlib import Path


def test_news_brief_semantic_packet_excludes_fetch_time() -> None:
    type_text = Path("src/parallax/domains/news_intel/types/news_item_brief.py").read_text(
        encoding="utf-8"
    )
    assert "fetched_at_ms" not in type_text


def test_news_brief_input_builder_does_not_read_fetch_time() -> None:
    builder_text = Path(
        "src/parallax/domains/news_intel/services/news_item_brief_input.py"
    ).read_text(encoding="utf-8")
    assert "fetched_at_ms" not in builder_text
```

- [ ] **Step 5: Run failing tests**

Run:

```bash
uv run pytest \
  tests/unit/domains/news_intel/test_news_item_brief_input.py::test_packet_hash_ignores_fetched_at_ms \
  tests/unit/domains/news_intel/test_news_item_brief_runtime.py::test_stage_payload_uses_material_packet_without_fetch_time \
  tests/architecture/test_agent_input_identity_contracts.py \
  -q
```

Expected: FAIL because `fetched_at_ms` still exists and stage payload still uses the full packet.

- [ ] **Step 6: Commit failing tests**

Run:

```bash
git add tests/unit/domains/news_intel/test_news_item_brief_input.py \
  tests/unit/domains/news_intel/test_news_item_brief_runtime.py \
  tests/architecture/test_agent_execution_plane_contracts.py \
  tests/architecture/test_agent_input_identity_contracts.py
git commit -m "test: pin news item brief semantic identity hard cut"
```

## Task 2: Implement Semantic Material Payload Hard Cut

**Files:**
- Modify: `src/parallax/domains/news_intel/types/news_item_brief.py`
- Modify: `src/parallax/domains/news_intel/services/news_item_brief_input.py`
- Modify: `src/parallax/domains/news_intel/services/news_item_brief_runtime.py`
- Modify: `tests/unit/domains/news_intel/test_news_item_brief_input.py`

- [ ] **Step 1: Remove `fetched_at_ms` from `NewsItemBriefNewsItem`**

In `src/parallax/domains/news_intel/types/news_item_brief.py`, change:

```python
class NewsItemBriefNewsItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    news_item_id: str = Field(min_length=1, max_length=160)
    title: str = Field(default="", max_length=500)
    summary: str = Field(default="", max_length=2000)
    body_excerpt: str = Field(default="", max_length=2000)
    canonical_url: str = Field(default="", max_length=2000)
    published_at_ms: int = Field(default=0, ge=0)
    content_hash: str = Field(default="", max_length=160)
    source: NewsItemBriefSource = Field(default_factory=NewsItemBriefSource)
```

- [ ] **Step 2: Add material payload/hash helpers**

In `src/parallax/domains/news_intel/services/news_item_brief_input.py`, add near the builder:

```python
def news_item_brief_material_input_payload(packet: NewsItemBriefInputPacket) -> dict[str, Any]:
    return packet.model_dump(
        mode="json",
        exclude={
            "input_hash",
        },
    )


def news_item_brief_material_input_hash(packet: NewsItemBriefInputPacket) -> str:
    return json_sha256(news_item_brief_material_input_payload(packet))
```

Keep this helper boring on purpose: volatile fields are removed at the type/builder boundary, so the hash helper stays easy to audit.

- [ ] **Step 3: Stop passing `fetched_at_ms` into the news item model**

In `build_news_item_brief_input_packet`, remove:

```python
fetched_at_ms=_optional_int(item.get("fetched_at_ms")),
```

Then change the return hash line to:

```python
return packet.model_copy(update={"input_hash": news_item_brief_material_input_hash(packet)})
```

- [ ] **Step 4: Use material payload in stage runtime**

In `src/parallax/domains/news_intel/services/news_item_brief_runtime.py`, import:

```python
from parallax.domains.news_intel.services.news_item_brief_input import (
    news_item_brief_material_input_payload,
)
```

Change `AgentStageSpec` construction:

```python
input_payload=news_item_brief_material_input_payload(packet),
```

- [ ] **Step 5: Export helper functions**

At the bottom of `news_item_brief_input.py`, update `__all__`:

```python
__all__ = [
    "BODY_EXCERPT_MAX_CHARS",
    "build_news_item_brief_input_packet",
    "news_item_brief_material_input_hash",
    "news_item_brief_material_input_payload",
]
```

- [ ] **Step 6: Update existing input tests that compare full packet hash**

Replace assertions like:

```python
assert packet.input_hash == json_sha256(packet.model_dump(mode="json", exclude={"input_hash"}))
```

with:

```python
from parallax.domains.news_intel.services.news_item_brief_input import (
    news_item_brief_material_input_payload,
)

assert packet.input_hash == json_sha256(news_item_brief_material_input_payload(packet))
```

- [ ] **Step 7: Run semantic identity tests**

Run:

```bash
uv run pytest \
  tests/unit/domains/news_intel/test_news_item_brief_input.py \
  tests/unit/domains/news_intel/test_news_item_brief_runtime.py \
  -q
```

Expected: PASS.

- [ ] **Step 8: Commit semantic identity hard cut**

Run:

```bash
git add src/parallax/domains/news_intel/types/news_item_brief.py \
  src/parallax/domains/news_intel/services/news_item_brief_input.py \
  src/parallax/domains/news_intel/services/news_item_brief_runtime.py \
  tests/unit/domains/news_intel/test_news_item_brief_input.py \
  tests/unit/domains/news_intel/test_news_item_brief_runtime.py
git commit -m "fix: hard cut news brief semantic input hash"
```

## Task 3: Fix Material Freshness And Worker Skip Gate

**Files:**
- Modify: `src/parallax/domains/news_intel/repositories/news_repository.py`
- Modify: `src/parallax/domains/news_intel/runtime/news_item_brief_worker.py`
- Modify: `tests/unit/domains/news_intel/test_news_item_brief_worker.py`
- Modify: `tests/integration/domains/news_intel/test_news_item_agent_brief_repository.py`

- [ ] **Step 1: Add worker test for volatile freshness**

Append to `tests/unit/domains/news_intel/test_news_item_brief_worker.py`:

```python
def test_worker_skips_fresh_current_even_when_source_updated_is_noisy() -> None:
    asyncio.run(_test_worker_skips_fresh_current_even_when_source_updated_is_noisy())


async def _test_worker_skips_fresh_current_even_when_source_updated_is_noisy() -> None:
    candidate = _candidate()
    provider = FakeBriefProvider(payload=_ready_payload())
    packet = provider.packet_for_candidate(candidate)
    candidate["source_updated_at_ms"] = NOW_MS + 60_000
    candidate["current_brief"] = {
        "news_item_id": candidate["item"]["news_item_id"],
        "status": "ready",
        "input_hash": packet.input_hash,
        "artifact_version_hash": provider.artifact_version_hash,
        "prompt_version": packet.prompt_version,
        "schema_version": packet.schema_version,
        "validator_version": packet.validator_version,
        "computed_at_ms": NOW_MS - 60_000,
        "brief_json": _ready_payload(),
    }
    db = FakeDB([candidate])
    worker = _worker(db=db, provider=provider)

    result = await worker.run_once()

    assert provider.execution_calls == 0
    assert db.news.runs == []
    assert db.news.briefs == []
    assert len(db.dirty.done) == 1
    assert result.skipped == 1
```

Add this helper to `FakeBriefProvider`:

```python
def packet_for_candidate(self, candidate: dict[str, Any]):
    from parallax.domains.news_intel.runtime.news_item_brief_worker import _packet_from_candidate
    from parallax.domains.news_intel.types.news_item_brief import default_news_item_brief_agent_config

    return _packet_from_candidate(
        candidate,
        agent_config=default_news_item_brief_agent_config(
            model=self.model,
            artifact_version_hash=self.artifact_version_hash,
        ),
    )
```

- [ ] **Step 2: Change freshness gate to exact semantic identity**

In `src/parallax/domains/news_intel/runtime/news_item_brief_worker.py`, replace `_current_brief_is_fresh` with:

```python
def _current_brief_is_fresh(
    candidate: Mapping[str, Any],
    *,
    packet: NewsItemBriefInputPacket,
    agent_config: NewsItemBriefAgentConfig,
) -> bool:
    current = _optional_dict(candidate.get("current_brief"))
    if current is None:
        return False
    status = str(current.get("status") or "")
    if status == "failed" and not _current_brief_is_terminal_failure(current):
        return False
    if status not in {"ready", "insufficient", "failed"}:
        return False
    if str(current.get("input_hash") or "") != packet.input_hash:
        return False
    if str(current.get("artifact_version_hash") or "") != agent_config.artifact_version_hash:
        return False
    if str(current.get("prompt_version") or "") != agent_config.prompt_version:
        return False
    if str(current.get("schema_version") or "") != agent_config.schema_version:
        return False
    if str(current.get("validator_version") or "") != agent_config.validator_version:
        return False
    return True
```

Add helper:

```python
def _current_brief_is_terminal_failure(current: Mapping[str, Any]) -> bool:
    brief = _optional_dict(current.get("brief_json"))
    return bool(brief and brief.get("terminal") is True)
```

- [ ] **Step 3: Remove volatile source freshness inputs from repository query**

In `load_items_for_brief_targets`, change the `GREATEST` expression from:

```sql
GREATEST(
  items.updated_at_ms,
  COALESCE(stories.updated_at_ms, 0),
  COALESCE(mention_updates.updated_at_ms, 0),
  COALESCE(fact_updates.updated_at_ms, 0),
  COALESCE(context_updates.updated_at_ms, 0)
) AS source_updated_at_ms
```

to:

```sql
GREATEST(
  COALESCE(items.processed_at_ms, items.created_at_ms, 0),
  COALESCE(mention_updates.updated_at_ms, 0),
  COALESCE(fact_updates.updated_at_ms, 0),
  COALESCE(context_updates.updated_at_ms, 0)
) AS source_updated_at_ms
```

`processed_at_ms` exists in the News schema and is written by `NewsRepository.mark_item_processed`; do not use `items.updated_at_ms` or projection timestamps in this expression.

- [ ] **Step 4: Add repository integration test**

Append to `tests/integration/domains/news_intel/test_news_item_agent_brief_repository.py` a focused test:

```python
def test_brief_target_material_watermark_ignores_refetch_updated_at(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repo = NewsRepository(conn)
        now = 1_779_000_000_000
        news_item_id = _insert_source_provider_and_item(
            repo,
            suffix="refetch-watermark",
            processed=True,
            now_ms=now,
        )
        first = repo.load_items_for_brief_targets(news_item_ids=[news_item_id])[0]
        item = conn.execute(
            "SELECT * FROM news_items WHERE news_item_id = %s",
            (news_item_id,),
        ).fetchone()

        repo.upsert_canonical_news_item(
            provider_item_id=item["provider_item_id"],
            canonical_url=item["canonical_url"],
            title=item["title"],
            summary=item["summary"],
            body_text=item["body_text"],
            language=item["language"],
            published_at_ms=item["published_at_ms"],
            fetched_at_ms=now + 60_000,
            content_hash=item["content_hash"],
            title_fingerprint=item["title_fingerprint"],
            now_ms=now + 60_000,
            provider_signal=item["provider_signal_json"] or {},
            provider_token_impacts=item["provider_token_impacts_json"] or [],
            commit=True,
        )
        second = repo.load_items_for_brief_targets(news_item_ids=[news_item_id])[0]
    finally:
        conn.close()

    assert second["source_updated_at_ms"] == first["source_updated_at_ms"]
```

- [ ] **Step 5: Run freshness tests**

Run:

```bash
uv run pytest \
  tests/unit/domains/news_intel/test_news_item_brief_worker.py::test_worker_skips_fresh_current_even_when_source_updated_is_noisy \
  tests/integration/domains/news_intel/test_news_item_agent_brief_repository.py::test_brief_target_material_watermark_ignores_refetch_updated_at \
  -q
```

Expected: PASS.

- [ ] **Step 6: Commit freshness hard cut**

Run:

```bash
git add src/parallax/domains/news_intel/repositories/news_repository.py \
  src/parallax/domains/news_intel/runtime/news_item_brief_worker.py \
  tests/unit/domains/news_intel/test_news_item_brief_worker.py \
  tests/integration/domains/news_intel/test_news_item_agent_brief_repository.py
git commit -m "fix: use semantic freshness for news item briefs"
```

## Task 4: Terminalize Failed Dirty Targets And Remove Permanent Failed Queue

**Files:**
- Modify: `src/parallax/domains/news_intel/repositories/news_projection_dirty_target_repository.py`
- Modify: `src/parallax/domains/news_intel/runtime/news_item_brief_worker.py`
- Modify: `tests/integration/domains/news_intel/test_news_projection_dirty_target_repository.py`
- Modify: `tests/unit/domains/news_intel/test_news_item_brief_worker.py`

- [ ] **Step 1: Add dirty target repository terminalization method**

In `news_projection_dirty_target_repository.py`, import:

```python
from contextlib import nullcontext

from parallax.platform.db.queue_terminal import terminalize_source_row
```

Add method:

```python
def terminalize_targets(
    self,
    keys: Iterable[Mapping[str, Any]],
    *,
    worker_name: str,
    final_reason: str,
    final_reason_bucket: str,
    now_ms: int,
    semantic_payload_hash: str | None = None,
    commit: bool = True,
) -> int:
    records = _key_records(keys)
    if not records:
        return 0
    terminalized = 0
    transaction_factory = getattr(self.conn, "transaction", None)
    transaction = transaction_factory() if callable(transaction_factory) else nullcontext()
    with transaction:
        for record in records:
            target_key = _terminal_target_key(record, semantic_payload_hash=semantic_payload_hash)
            terminalize_source_row(
                self.conn,
                worker_name=worker_name,
                source_table="news_projection_dirty_targets",
                target_key=target_key,
                source_row=record,
                final_status="terminal",
                final_reason=final_reason,
                final_reason_bucket=final_reason_bucket,
                now_ms=int(now_ms),
                attempt_count=int(record["attempt_count"]),
                payload_hash=str(semantic_payload_hash or record["payload_hash"]),
                commit=False,
            )
        terminalized = self.mark_done(records, now_ms=now_ms, commit=False)
    if commit:
        self.conn.commit()
    return terminalized
```

Add helper:

```python
def _terminal_target_key(record: Mapping[str, Any], *, semantic_payload_hash: str | None) -> str:
    return "|".join(
        [
            str(record["projection_name"]),
            str(record["target_kind"]),
            str(record["target_id"]),
            str(record["window"]),
            str(semantic_payload_hash or record["payload_hash"]),
        ]
    )
```

Also import `nullcontext` from `contextlib`.

- [ ] **Step 2: Add repository integration test**

Add import to `tests/integration/domains/news_intel/test_news_projection_dirty_target_repository.py`:

```python
from tests.postgres_test_utils import reset_postgres_schema as migrate
```

Append to `tests/integration/domains/news_intel/test_news_projection_dirty_target_repository.py`:

```python
def test_terminalize_targets_deletes_hot_row_and_records_terminal_event(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repo = NewsProjectionDirtyTargetRepository(conn)
        now = 1_779_000_000_000
        repo.enqueue_targets(
            [{"projection_name": "brief_input", "target_kind": "news_item", "target_id": "item-terminal"}],
            reason="unit",
            now_ms=now,
        )
        claimed = repo.claim_due(limit=1, lease_ms=60_000, now_ms=now, lease_owner="worker:test")

        count = repo.terminalize_targets(
            claimed,
            worker_name="news_item_brief",
            final_reason="domain_validation_failed",
            final_reason_bucket="domain_validation_failed",
            semantic_payload_hash="semantic-hash-1",
            now_ms=now + 1,
        )

        row = conn.execute(
            """
            SELECT *
            FROM worker_queue_terminal_events
            WHERE worker_name = 'news_item_brief'
              AND source_table = 'news_projection_dirty_targets'
              AND target_key LIKE '%semantic-hash-1'
            """
        ).fetchone()
        depth = repo.queue_depth(now_ms=now + 1, projection_name="brief_input")
    finally:
        conn.close()

    assert count == 1
    assert depth == 0
    assert row is not None
    assert row["final_reason_bucket"] == "domain_validation_failed"
```

- [ ] **Step 3: Stop writing failed current for retryable failures**

In `NewsItemBriefWorker._record_provider_failure`, remove `_upsert_failed_current(...)` from the retryable path. The method should insert the failed run audit, then return an outcome that carries retry metadata:

```python
return _CandidateOutcome(
    notes={"failed": 1},
    current_updates=0,
    retry_ms=self._retry_ms(),
    retry_reason=_provider_error_class(error),
    retry_attempt_limited=resolved_execution_started,
    retry_counts_attempt=resolved_execution_started,
    terminal_run_id=run_id,
    terminal_errors=[{"code": _provider_error_class(error), "message": str(error)[:500]}],
)
```

In the validation failure path, delete the immediate `_upsert_failed_current(...)` call and return:

```python
return _CandidateOutcome(
    notes={"failed": 1, "validation_failed": 1},
    current_updates=0,
    retry_ms=self._retry_ms(),
    retry_reason="domain_validation_failed",
    retry_attempt_limited=True,
    retry_counts_attempt=True,
    terminal_run_id=run_id,
    terminal_errors=validation.errors,
)
```

- [ ] **Step 4: Add terminal current payload helper**

Replace `_failed_brief` with:

```python
def _failed_brief(errors: list[dict[str, str]], *, terminal: bool = False, terminal_reason: str = "") -> dict[str, Any]:
    reason = "; ".join(str(error.get("message") or error.get("code") or "")[:120] for error in errors[:3])
    suffix = f"原因：{reason}" if reason else "已记录失败原因。"
    payload = {
        "status": "failed",
        "direction": "neutral",
        "decision_class": "discard",
        "summary_zh": "",
        "market_read_zh": "",
        "bull_view": {"strength": "absent", "thesis_zh": "", "evidence_refs": []},
        "bear_view": {"strength": "absent", "thesis_zh": "", "evidence_refs": []},
        "affected_assets": [],
        "watch_triggers": [],
        "invalidation_conditions": [],
        "data_gaps": [
            {
                "description_zh": f"新闻条目智能摘要不可发布，{suffix}",
                "severity": "high",
            }
        ],
        "evidence_refs": [],
    }
    if terminal:
        payload["terminal"] = True
        payload["terminal_reason"] = terminal_reason
    return payload
```

- [ ] **Step 5: Terminalize after bounded attempts**

Add terminal current state support and pass the semantic packet into completion so terminal events are keyed by material hash.

Add:

```python
def _upsert_terminal_failed_current(
    self,
    *,
    run_id: str,
    packet: NewsItemBriefInputPacket,
    agent_config: NewsItemBriefAgentConfig,
    errors: list[dict[str, str]],
    terminal_reason: str,
    computed_at_ms: int,
) -> None:
    self._upsert_current(
        run_id=run_id,
        packet=packet,
        agent_config=agent_config,
        payload=_failed_brief(errors, terminal=True, terminal_reason=terminal_reason),
        computed_at_ms=computed_at_ms,
    )
```

Extend `_CandidateOutcome.__init__`:

```python
class _CandidateOutcome:
    def __init__(
        self,
        *,
        notes: Mapping[str, int],
        current_updates: int,
        retry_ms: int | None = None,
        retry_reason: str = "",
        retry_attempt_limited: bool = False,
        retry_counts_attempt: bool = True,
        terminal_run_id: str = "",
        terminal_errors: list[dict[str, str]] | None = None,
    ) -> None:
        self.notes = dict(notes)
        self.current_updates = int(current_updates)
        self.retry_ms = int(retry_ms) if retry_ms is not None else None
        self.retry_reason = retry_reason or "agent_brief_retry"
        self.retry_attempt_limited = bool(retry_attempt_limited)
        self.retry_counts_attempt = bool(retry_counts_attempt)
        self.terminal_run_id = str(terminal_run_id or "")
        self.terminal_errors = list(terminal_errors or [])
```

Add terminalization helper:

```python
def _terminalize_claimed_target(
    self,
    target: Mapping[str, Any],
    *,
    outcome: _CandidateOutcome,
    packet: NewsItemBriefInputPacket,
    now_ms: int,
) -> None:
    with self._repository_session() as repos:
        repos.news_projection_dirty_targets.terminalize_targets(
            [target],
            worker_name=self.name,
            final_reason=outcome.retry_reason,
            final_reason_bucket=outcome.retry_reason,
            now_ms=now_ms,
            semantic_payload_hash=packet.input_hash,
        )
```

Change the call site in `run_once`:

```python
await asyncio.to_thread(
    self._complete_claimed_target,
    target,
    outcome=outcome,
    packet=packet,
    agent_config=agent_config,
    now_ms=now,
)
```

Change `_complete_claimed_target`:

```python
def _complete_claimed_target(
    self,
    target: Mapping[str, Any],
    *,
    outcome: _CandidateOutcome,
    packet: NewsItemBriefInputPacket,
    agent_config: NewsItemBriefAgentConfig,
    now_ms: int,
) -> None:
    if outcome.retry_ms is None:
        self._mark_targets_done([target], now_ms=now_ms)
        return
    attempted_now = 1 if outcome.retry_counts_attempt else 0
    attempt_after_failure = int(target.get("attempt_count") or 0) + attempted_now
    if not outcome.retry_attempt_limited or attempt_after_failure < self._max_attempts():
        self._mark_targets_error(
            [target],
            error=outcome.retry_reason,
            retry_ms=outcome.retry_ms,
            now_ms=now_ms,
            count_attempt=outcome.retry_counts_attempt,
        )
        return
    if outcome.terminal_run_id and outcome.terminal_errors:
        self._upsert_terminal_failed_current(
            run_id=outcome.terminal_run_id,
            packet=packet,
            agent_config=agent_config,
            errors=outcome.terminal_errors,
            terminal_reason=outcome.retry_reason,
            computed_at_ms=now_ms,
        )
    self._terminalize_claimed_target(target, outcome=outcome, packet=packet, now_ms=now_ms)
```

- [ ] **Step 6: Add worker tests for terminalization**

Append to `tests/unit/domains/news_intel/test_news_item_brief_worker.py`:

```python
def test_worker_terminalizes_after_max_attempts_without_permanent_dirty_failure() -> None:
    asyncio.run(_test_worker_terminalizes_after_max_attempts_without_permanent_dirty_failure())


async def _test_worker_terminalizes_after_max_attempts_without_permanent_dirty_failure() -> None:
    target = _dirty_target(attempt_count=2)
    db = FakeDB([_candidate()], targets=[target])
    provider = FakeBriefProvider(brief_error=RuntimeError("provider bad output"))
    worker = _worker(db=db, provider=provider, settings=SimpleNamespace(batch_size=1, max_attempts=3))

    result = await worker.run_once()

    assert provider.execution_calls == 1
    assert db.dirty.errors == []
    assert len(db.dirty.terminalized) == 1
    assert db.dirty.done == []
    assert result.failed == 1
```

Extend `FakeDirtyTargets` with `terminalized: list[dict[str, Any]]` and a `terminalize_targets(...)` method that appends calls and returns `len(keys)`.

- [ ] **Step 7: Run terminalization tests**

Run:

```bash
uv run pytest \
  tests/integration/domains/news_intel/test_news_projection_dirty_target_repository.py::test_terminalize_targets_deletes_hot_row_and_records_terminal_event \
  tests/unit/domains/news_intel/test_news_item_brief_worker.py::test_worker_terminalizes_after_max_attempts_without_permanent_dirty_failure \
  -q
```

Expected: PASS.

- [ ] **Step 8: Commit dirty target terminalization**

Run:

```bash
git add src/parallax/domains/news_intel/repositories/news_projection_dirty_target_repository.py \
  src/parallax/domains/news_intel/runtime/news_item_brief_worker.py \
  tests/integration/domains/news_intel/test_news_projection_dirty_target_repository.py \
  tests/unit/domains/news_intel/test_news_item_brief_worker.py
git commit -m "fix: terminalize failed news brief dirty targets"
```

## Task 5: Shared Quota Exhausted Backpressure

**Files:**
- Modify: `src/parallax/platform/agent_execution.py`
- Modify: `src/parallax/integrations/model_execution/execution_gateway.py`
- Modify: `src/parallax/domains/news_intel/runtime/news_item_brief_worker.py`
- Modify: `src/parallax/domains/narrative_intel/runtime/mention_semantics_worker.py`
- Modify: `src/parallax/domains/narrative_intel/runtime/token_discussion_digest_worker.py`
- Modify: `src/parallax/domains/pulse_lab/services/pulse_candidate_job_service.py`
- Modify: `src/parallax/integrations/model_execution/pulse_decision_agent_client.py`
- Modify: `tests/unit/integrations/model_execution/test_agent_execution_gateway.py`
- Modify: `tests/unit/domains/news_intel/test_news_item_brief_worker.py`

- [ ] **Step 1: Add enum value**

In `src/parallax/platform/agent_execution.py`:

```python
class AgentExecutionErrorClass(StrEnum):
    CANCELLED = "cancelled"
    CAPACITY_DENIED = "capacity_denied"
    CIRCUIT_OPEN = "circuit_open"
    TIMEOUT = "timeout"
    RATE_LIMITED = "rate_limited"
    QUOTA_EXHAUSTED = "quota_exhausted"
    TRANSPORT_ERROR = "transport_error"
    PROVIDER_ERROR = "provider_error"
    SCHEMA_INVALID = "schema_invalid"
    DOMAIN_VALIDATION_FAILED = "domain_validation_failed"
    DETERMINISTIC_NO_INPUT = "deterministic_no_input"
```

- [ ] **Step 2: Add gateway classification tests**

Append to `tests/unit/integrations/model_execution/test_agent_execution_gateway.py`:

```python
def test_insufficient_balance_is_quota_exhausted_no_start_and_opens_circuit() -> None:
    async def scenario() -> None:
        completions = FakeJsonCompletions(exception=RuntimeError("OpenAIException - Insufficient Balance"))
        gateway = _gateway(
            llm_gateway=FakeLLMGateway(completions=completions),
            policy=_policy(failure_threshold=1),
        )

        with pytest.raises(AgentExecutionError) as err:
            await gateway.execute(_spec())

        assert err.value.error_class is AgentExecutionErrorClass.QUOTA_EXHAUSTED
        assert err.value.execution_started is False
        assert len(completions.calls) == 1

        denied = gateway.try_reserve("test.lane")
        assert denied.acquired is False
        assert denied.reason is AgentExecutionErrorClass.CIRCUIT_OPEN

    asyncio.run(scenario())
```

- [ ] **Step 3: Implement provider error classification**

In `execution_gateway.py`, replace `_classify_provider_error` with:

```python
def _classify_provider_error(exc: Exception) -> AgentExecutionErrorClass:
    name = type(exc).__name__.lower()
    text = f"{name} {exc}".lower()
    quota_markers = (
        "insufficient balance",
        "insufficient_quota",
        "quota exceeded",
        "quota_exceeded",
        "billing",
        "payment required",
        "402",
        "account balance",
        "no credit",
    )
    auth_markers = (
        "invalid api key",
        "unauthorized",
        "authentication",
        "permission denied",
        "401",
        "403",
    )
    if any(marker in text for marker in quota_markers + auth_markers):
        return AgentExecutionErrorClass.QUOTA_EXHAUSTED
    if "ratelimit" in name or "rate_limit" in name or "rate limit" in text:
        return AgentExecutionErrorClass.RATE_LIMITED
    if "timeout" in name or "transport" in name or "connection" in name:
        return AgentExecutionErrorClass.TRANSPORT_ERROR
    return AgentExecutionErrorClass.PROVIDER_ERROR
```

In the provider exception path, set:

```python
execution_started = error_class not in {AgentExecutionErrorClass.QUOTA_EXHAUSTED}
```

Use that variable in both `_failed_audit(..., execution_started=execution_started)` and `AgentExecutionError(..., execution_started=execution_started)`.

Add this method on `AgentExecutionGateway`:

```python
def open_lane_circuit(self, lane: str) -> None:
    now = time.monotonic()
    lane_state = self._lane_state(lane)
    breaker = lane_state.policy.circuit_breaker
    lane_state.failure_timestamps.append(now)
    lane_state.circuit_open_until = max(
        lane_state.circuit_open_until,
        now + float(breaker.open_seconds),
    )
```

Then replace the current unconditional `self.record_lane_failure(stage.lane)` in the provider exception path with:

```python
if error_class is AgentExecutionErrorClass.QUOTA_EXHAUSTED:
    self.open_lane_circuit(stage.lane)
else:
    self.record_lane_failure(stage.lane)
```

- [ ] **Step 4: Add quota to no-start sets**

In News `_is_no_start_backpressure_error` and `_backpressure_outcome_for_reason`, include:

```python
if reason == AgentExecutionErrorClass.QUOTA_EXHAUSTED:
    return "backpressure_quota_exhausted"
```

and:

```python
AgentExecutionErrorClass.QUOTA_EXHAUSTED
```

in the no-start set.

In Narrative and Pulse no-start helpers, add `"quota_exhausted"` or `AgentExecutionErrorClass.QUOTA_EXHAUSTED` to the existing sets.

- [ ] **Step 5: Add News worker quota test**

Append to `tests/unit/domains/news_intel/test_news_item_brief_worker.py`:

```python
def test_worker_quota_exhausted_does_not_write_failed_current_or_attempt() -> None:
    asyncio.run(_test_worker_quota_exhausted_does_not_write_failed_current_or_attempt())


async def _test_worker_quota_exhausted_does_not_write_failed_current_or_attempt() -> None:
    db = FakeDB([_candidate()])
    provider = FakeBriefProvider(
        brief_error=AgentExecutionError(
            AgentExecutionErrorClass.QUOTA_EXHAUSTED,
            "Insufficient Balance",
            execution_started=False,
        )
    )
    worker = _worker(db=db, provider=provider)

    result = await worker.run_once()

    assert provider.execution_calls == 1
    assert db.news.runs == []
    assert db.news.briefs == []
    assert len(db.dirty.errors) == 1
    assert db.dirty.error_kwargs[-1]["count_attempt"] is False
    assert result.notes["backpressure_quota_exhausted"] == 1
```

- [ ] **Step 6: Run quota tests**

Run:

```bash
uv run pytest \
  tests/unit/integrations/model_execution/test_agent_execution_gateway.py::test_insufficient_balance_is_quota_exhausted_no_start_and_opens_circuit \
  tests/unit/domains/news_intel/test_news_item_brief_worker.py::test_worker_quota_exhausted_does_not_write_failed_current_or_attempt \
  -q
```

Expected: PASS.

- [ ] **Step 7: Commit quota backpressure**

Run:

```bash
git add src/parallax/platform/agent_execution.py \
  src/parallax/integrations/model_execution/execution_gateway.py \
  src/parallax/domains/news_intel/runtime/news_item_brief_worker.py \
  src/parallax/domains/narrative_intel/runtime/mention_semantics_worker.py \
  src/parallax/domains/narrative_intel/runtime/token_discussion_digest_worker.py \
  src/parallax/domains/pulse_lab/services/pulse_candidate_job_service.py \
  src/parallax/integrations/model_execution/pulse_decision_agent_client.py \
  tests/unit/integrations/model_execution/test_agent_execution_gateway.py \
  tests/unit/domains/news_intel/test_news_item_brief_worker.py
git commit -m "fix: classify llm quota exhaustion as backpressure"
```

## Task 6: Cross-Agent Identity Guard And Narrative Hash Cleanup

**Files:**
- Modify: `src/parallax/domains/narrative_intel/runtime/mention_semantics_worker.py`
- Modify: `tests/architecture/test_agent_input_identity_contracts.py`
- Create: `tests/unit/domains/narrative_intel/test_mention_semantics_input_identity.py`

- [ ] **Step 1: Add semantic row helper for Narrative mention semantics**

In `mention_semantics_worker.py`, add:

```python
def _mention_semantics_input_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "event_id": str(row.get("event_id") or ""),
            "target_type": str(row.get("target_type") or ""),
            "target_id": str(row.get("target_id") or ""),
            "text_clean": str(row.get("text_clean") or row.get("text") or ""),
            "text_fingerprint": str(row.get("text_fingerprint") or ""),
        }
        for row in rows
    ]
```

Change:

```python
input_hash = _hash_json(rows)
```

to:

```python
input_hash = _hash_json(_mention_semantics_input_rows(rows))
```

- [ ] **Step 2: Add unit test for Narrative hash stability**

Create `tests/unit/domains/narrative_intel/test_mention_semantics_input_identity.py`:

```python
from __future__ import annotations

from parallax.domains.narrative_intel.runtime.mention_semantics_worker import (
    _hash_json,
    _mention_semantics_input_rows,
)


def test_mention_semantics_input_hash_ignores_claim_metadata() -> None:
    row = {
        "event_id": "event-1",
        "target_type": "asset",
        "target_id": "asset:btc",
        "text_clean": "BTC ETF flows accelerated.",
        "text_fingerprint": "text-hash",
        "lease_owner": "worker-a",
        "attempt_count": 1,
    }
    changed_claim = {**row, "lease_owner": "worker-b", "attempt_count": 4}

    assert _hash_json(_mention_semantics_input_rows([row])) == _hash_json(
        _mention_semantics_input_rows([changed_claim])
    )
```

- [ ] **Step 3: Add architecture guard for Narrative direct row hashing**

Append to `tests/architecture/test_agent_input_identity_contracts.py`:

```python
def test_narrative_mention_semantics_does_not_hash_claimed_rows_directly() -> None:
    text = Path("src/parallax/domains/narrative_intel/runtime/mention_semantics_worker.py").read_text(
        encoding="utf-8"
    )
    assert "input_hash = _hash_json(rows)" not in text
    assert "input_hash = _hash_json(_mention_semantics_input_rows(rows))" in text
```

- [ ] **Step 4: Run cross-agent guard tests**

Run:

```bash
uv run pytest \
  tests/unit/domains/narrative_intel/test_mention_semantics_input_identity.py \
  tests/architecture/test_agent_input_identity_contracts.py \
  -q
```

Expected: PASS.

- [ ] **Step 5: Commit cross-agent guard**

Run:

```bash
git add src/parallax/domains/narrative_intel/runtime/mention_semantics_worker.py \
  tests/unit/domains/narrative_intel/test_mention_semantics_input_identity.py \
  tests/architecture/test_agent_input_identity_contracts.py
git commit -m "test: guard agent input hashes against claim metadata"
```

## Final Verification

- [ ] **Run focused News and gateway suites**

```bash
uv run pytest \
  tests/unit/domains/news_intel/test_news_item_brief_input.py \
  tests/unit/domains/news_intel/test_news_item_brief_runtime.py \
  tests/unit/domains/news_intel/test_news_item_brief_worker.py \
  tests/unit/integrations/model_execution/test_agent_execution_gateway.py \
  tests/integration/domains/news_intel/test_news_projection_dirty_target_repository.py \
  tests/integration/domains/news_intel/test_news_item_agent_brief_repository.py \
  -q
```

Expected: PASS.

- [ ] **Run architecture guards**

```bash
uv run pytest \
  tests/architecture/test_agent_execution_plane_contracts.py \
  tests/architecture/test_agent_input_identity_contracts.py \
  tests/architecture/test_projection_worker_idle_cost_contract.py \
  -q
```

Expected: PASS.

- [ ] **Run lint**

```bash
uv run ruff check .
```

Expected: PASS.

- [ ] **Run live-safe diagnostics**

```bash
uv run parallax config
uv run parallax ops worker-status
```

Expected:

- config paths point to `/Users/qinghuan/.parallax/...`;
- no secrets printed;
- `news_item_brief` due backlog is visible;
- after worker dry run or controlled run, unchanged targets are marked done/terminalized without provider-started run growth.

## Acceptance Mapping

- AC1: `test_packet_hash_ignores_fetched_at_ms`
- AC2: `test_worker_skips_fresh_current_even_when_source_updated_is_noisy`
- AC3: existing material-change packet hash tests plus repository material watermark test
- AC4: `test_insufficient_balance_is_quota_exhausted_no_start_and_opens_circuit`
- AC5: live-safe diagnostics compare actual runs/hour to eligible news/hour after deploy
- AC6: worker volatile metadata tests assert no new run ledger rows
- AC7: material update worker/repository tests assert one new run/update
- AC8: terminalization worker/repository tests
- AC9: quota circuit test plus worker quota no-current-write test
- AC10: architecture no-legacy-hash-fallback test

## Rollout

1. Keep `news_item_brief` disabled or lane RPM very low until Task 1-6 are merged.
2. Enable `news_item_brief` under low RPM for one worker interval so old-hash current rows refresh under a bounded cost envelope.
3. Verify unchanged dirty targets are marked done/terminalized without provider-started run growth.
4. Restore normal RPM only after token/hour is near one-brief-per-eligible-item behavior.

## Rollback

1. Disable `news_item_brief` in operator `workers.yaml` if provider-started run growth returns.
2. Leave deterministic News workers running: `news_fetch`, `news_item_process`, `news_page_projection`, `news_source_quality_projection`.
3. Do not revert DB terminal events; they are audit facts. Use explicit terminal retry tooling if an operator needs to resurrect a target.
4. If quota classification causes false circuit-open, lower circuit open duration or fix classifier markers, then restart process to clear in-memory circuit.

## Completion Gate

- [ ] All final verification commands pass.
- [ ] No runtime legacy hash fallback exists.
- [ ] No `fetched_at_ms` in News brief model-visible semantic packet.
- [ ] No unchanged due `brief_input` failed queue remains hot after worker pass.
- [ ] Provider quota/balance outage produces backpressure/circuit, not item-level failed current churn.
- [ ] Cross-agent architecture guard protects Narrative before re-enable.
