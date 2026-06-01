# News Intel KISS Simplification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Hard-cut News Intel to a simpler chain: fetch facts, deterministically process items, optionally brief processed items, and project the public page row without duplicate admission paths or source-quality hot-path coupling.

**Architecture:** Keep the existing five-worker inventory and the single physical `news_projection_dirty_targets` table. Add one semantic scheduling adapter that owns dirty-target strings and source-quality refresh sentinel details; workers talk in page reproject, item brief, and source-quality refresh terms. Do not add compatibility aliases, dual signatures, old projection fallbacks, new workers, new tables, new LLM lanes, or story projection code.

**Tech Stack:** Python 3, PostgreSQL/Alembic, `uv`, pytest architecture tests, Parallax worker runtime, React/TypeScript model updates if public News row shape changes.

---

## Hard-Cut Rules

- No compatibility code: no import alias from `news_item_brief_runtime.py`, no dual old/new policy signatures, no duplicated dirty-target enqueue helpers left beside the semantic adapter, no frontend fallback that accepts both old and new signal shapes.
- Keep the worker set unchanged: `news_fetch`, `news_item_process`, `news_item_brief`, `news_page_projection`, `news_source_quality_projection`.
- Keep the single physical `news_projection_dirty_targets` table.
- Raw dirty projection strings may appear only in:
  - `src/parallax/domains/news_intel/repositories/news_projection_dirty_target_repository.py`
  - `src/parallax/domains/news_intel/runtime/news_projection_work.py`
  - Alembic migrations
  - queue-health or ops adapter code that immediately translates CLI input into semantic calls
  - adapter-focused tests
- Fetch must not import or call `news_item_agent_policy`.
- Fetch/process/brief must not accept or store `source_quality_windows`.
- Source quality windows are read only by `NewsSourceQualityProjectionWorker`.
- `news_item_brief_runtime.py` is deleted and replaced by `news_item_brief_stage.py`.

## File Map

- Create `src/parallax/domains/news_intel/runtime/news_projection_work.py`
  - Own semantic enqueue, claim, queue-depth, target-id extraction, mark-done, mark-error, terminalize helpers.
  - Own physical dirty projection strings and private source-quality refresh sentinel window.
- Modify `src/parallax/domains/news_intel/runtime/news_fetch_worker.py`
  - Remove fetch-to-brief admission.
  - Remove source-quality windows constructor state.
  - Decouple OpenNews fetch horizon from agent brief age.
  - Mark parents with new context for deterministic reprocessing instead of direct brief enqueue.
- Modify `src/parallax/domains/news_intel/runtime/news_item_process_worker.py`
  - Make processed item admission the only normal runtime creator of item brief work.
  - Use processed state: classification, token mentions, fact candidates, and context.
  - Remove source-quality per-window fanout.
- Modify `src/parallax/domains/news_intel/runtime/news_item_brief_worker.py`
  - Use semantic brief claim/queue helpers.
  - Recheck the new processed-state admission policy.
  - Dirty only page rows after current brief writes.
  - Remove unused `_upsert_failed_current` if still unused after edits.
- Modify `src/parallax/domains/news_intel/runtime/news_page_projection_worker.py`
  - Use semantic page claim and target-id helpers.
- Modify `src/parallax/domains/news_intel/runtime/news_source_quality_projection_worker.py`
  - Use semantic source-quality claim helpers.
  - Expand source refresh intents into configured windows inside this worker.
  - Keep future per-window rescheduling owned here.
- Modify `src/parallax/app/runtime/worker_factories/news_intel.py`
  - Stop passing `source_quality_windows` into fetch/process/brief constructors.
- Modify `src/parallax/app/runtime/worker_manifest.py`
  - Update News input-contract wording away from raw projection strings where possible.
  - Reduce source-quality wake inputs to the source refresh wake path.
- Modify `src/parallax/platform/config/settings.py`
  - Update default `news_source_quality_projection.wakes_on` to `("news_item_written",)`.
  - Keep `news_source_quality_projection.windows` as the single window owner.
- Modify `src/parallax/app/runtime/projection_dirty_targets.py`
  - Keep CLI choices if the public ops command still exposes them, but translate immediately into semantic scheduling functions.
  - Remove direct policy calls using raw provider-only row shape.
- Modify `src/parallax/domains/news_intel/services/news_item_agent_policy.py`
  - Replace mapping-only eligibility with a processed-state signature.
- Rename `src/parallax/domains/news_intel/services/news_item_brief_runtime.py` to `src/parallax/domains/news_intel/services/news_item_brief_stage.py`
  - Update `src/parallax/integrations/model_execution/news_item_brief_agent_client.py`.
  - Rename `tests/unit/domains/news_intel/test_news_item_brief_runtime.py`.
- Modify `src/parallax/domains/news_intel/services/news_page_projection.py`
  - Hard-cut `signal` into an explicit envelope with `display_signal`, `provider_signal`, `agent_signal`, and `alert_eligibility`.
- Modify `src/parallax/domains/news_intel/repositories/news_repository.py`
  - Add a bounded method for context-driven deterministic reprocessing.
  - Add processed fields needed by ops repair or brief admission queries.
  - Remove serving-table use of dead `source_watermark_ms` fields.
- Create `src/parallax/platform/db/alembic/versions/20260601_0141_news_intel_kiss_simplification.py`
  - Drop `source_watermark_ms` from `news_page_rows` and `news_source_quality_rows`.
  - Do not touch `news_projection_dirty_targets.source_watermark_ms`.
- Modify docs:
  - `docs/ARCHITECTURE.md`
  - `docs/WORKERS.md`
  - `docs/CONTRACTS.md`
  - `src/parallax/domains/news_intel/ARCHITECTURE.md`
  - `docs/superpowers/specs/active/2026-06-01-news-intel-kiss-simplification-cn.md` only if implementation forces a spec clarification.

## Task 1: Lock The KISS Architecture Contracts

**Files:**
- Create: `tests/architecture/test_news_intel_kiss_simplification.py`
- Modify: `tests/architecture/test_runtime_performance_architecture_hard_cut.py`
- Test: `tests/architecture/test_news_intel_kiss_simplification.py`

- [ ] **Step 1: Add failing architecture tests**

Create `tests/architecture/test_news_intel_kiss_simplification.py`:

```python
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src" / "parallax"

ALLOWED_DIRTY_STRING_FILES = {
    "src/parallax/domains/news_intel/repositories/news_projection_dirty_target_repository.py",
    "src/parallax/domains/news_intel/runtime/news_projection_work.py",
    "src/parallax/app/runtime/projection_dirty_targets.py",
}

RAW_PROJECTION_STRINGS = {"brief_input", "page", "source_quality"}


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def _rel(path: Path) -> str:
    return str(path.relative_to(ROOT))


def test_news_fetch_has_no_agent_brief_admission_dependency() -> None:
    source = _read("src/parallax/domains/news_intel/runtime/news_fetch_worker.py")
    tree = ast.parse(source)
    imports = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        and node.module == "parallax.domains.news_intel.services.news_item_agent_policy"
    ]
    assert imports == []
    assert "brief_input" not in source
    assert "news_item_agent_brief_eligibility" not in source
    assert "NEWS_ITEM_AGENT_BRIEF_MAX_PUBLISHED_AGE_MS" not in source


def test_fetch_process_brief_constructors_do_not_accept_source_quality_windows() -> None:
    paths = [
        "src/parallax/domains/news_intel/runtime/news_fetch_worker.py",
        "src/parallax/domains/news_intel/runtime/news_item_process_worker.py",
        "src/parallax/domains/news_intel/runtime/news_item_brief_worker.py",
        "src/parallax/app/runtime/worker_factories/news_intel.py",
    ]
    offenders = [path for path in paths if "source_quality_windows" in _read(path)]
    assert offenders == []


def test_news_runtime_workers_do_not_use_raw_dirty_projection_strings() -> None:
    offenders: list[str] = []
    for path in (SRC / "domains/news_intel/runtime").glob("news_*worker.py"):
        rel = _rel(path)
        if rel in ALLOWED_DIRTY_STRING_FILES:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and node.value in RAW_PROJECTION_STRINGS:
                offenders.append(f"{rel}:{node.lineno}:{node.value}")
    assert offenders == []


def test_news_item_brief_stage_adapter_has_hard_cut_name() -> None:
    old_path = SRC / "domains/news_intel/services/news_item_brief_runtime.py"
    new_path = SRC / "domains/news_intel/services/news_item_brief_stage.py"
    assert not old_path.exists()
    assert new_path.exists()


def test_news_has_single_item_brief_llm_lane() -> None:
    lane_names: set[str] = set()
    for path in SRC.rglob("*.py"):
        if "alembic" in path.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Assign):
                continue
            if not isinstance(node.value, ast.Constant) or not isinstance(node.value.value, str):
                continue
            if not node.value.value.startswith("news."):
                continue
            if any(isinstance(target, ast.Name) and target.id.endswith("_LANE") for target in node.targets):
                lane_names.add(node.value.value)
    assert sorted(lane_names) == ["news.item_brief"]
```

- [ ] **Step 2: Replace the old provider-signal hot-path test**

In `tests/architecture/test_runtime_performance_architecture_hard_cut.py`, replace `test_opennews_provider_signal_never_reenters_news_brief_input_hot_path` with:

```python
def test_opennews_provider_signal_does_not_enter_fetch_brief_hot_path() -> None:
    fetch_worker = _read("src/parallax/domains/news_intel/runtime/news_fetch_worker.py")

    assert "news_item_agent_brief_eligibility" not in fetch_worker
    assert "brief_input" not in fetch_worker
    assert "NEWS_ITEM_AGENT_BRIEF_MAX_PUBLISHED_AGE_MS" not in fetch_worker
```

- [ ] **Step 3: Run architecture tests and confirm they fail**

Run:

```bash
uv run pytest tests/architecture/test_news_intel_kiss_simplification.py tests/architecture/test_runtime_performance_architecture_hard_cut.py::test_opennews_provider_signal_does_not_enter_fetch_brief_hot_path -q
```

Expected: FAIL on current code because fetch imports the agent policy, runtime workers use raw dirty strings, constructors accept `source_quality_windows`, and the old brief runtime file exists.

- [ ] **Step 4: Commit the failing contracts**

```bash
git add tests/architecture/test_news_intel_kiss_simplification.py tests/architecture/test_runtime_performance_architecture_hard_cut.py
git commit -m "test: lock news intel kiss architecture contracts"
```

## Task 2: Add Semantic News Projection Work Adapter

**Files:**
- Create: `src/parallax/domains/news_intel/runtime/news_projection_work.py`
- Create: `tests/unit/domains/news_intel/test_news_projection_work.py`
- Keep worker call sites unchanged until this adapter test is green.

- [ ] **Step 1: Write adapter unit tests**

Create `tests/unit/domains/news_intel/test_news_projection_work.py`:

```python
from __future__ import annotations

from parallax.domains.news_intel.runtime.news_projection_work import (
    claim_item_brief_work,
    claim_page_projection_work,
    claim_source_quality_work,
    enqueue_item_brief_work,
    enqueue_page_reprojection,
    enqueue_source_quality_refresh,
    page_news_item_ids,
    source_quality_windows_for_claimed,
)


NOW_MS = 1_800_000


class FakeDirtyTargets:
    def __init__(self) -> None:
        self.enqueued: list[dict[str, object]] = []
        self.claim_calls: list[dict[str, object]] = []
        self.claim_rows: list[dict[str, object]] = []

    def enqueue_targets(self, targets, *, reason, now_ms, due_at_ms=None, commit=True):
        self.enqueued.extend(dict(target) for target in targets)
        self.reason = reason
        self.now_ms = now_ms
        self.due_at_ms = due_at_ms
        self.commit = commit
        return len(self.enqueued)

    def claim_due(self, **kwargs):
        self.claim_calls.append(dict(kwargs))
        return list(self.claim_rows)


class FakeRepos:
    def __init__(self) -> None:
        self.news_projection_dirty_targets = FakeDirtyTargets()


def test_enqueue_page_reprojection_hides_page_projection_name() -> None:
    repos = FakeRepos()

    count = enqueue_page_reprojection(
        repos,
        news_item_ids=["news-1", "news-1", ""],
        reason="news_item_processed",
        now_ms=NOW_MS,
        commit=False,
    )

    assert count == 1
    assert repos.news_projection_dirty_targets.enqueued == [
        {"projection_name": "page", "target_kind": "news_item", "target_id": "news-1"}
    ]


def test_enqueue_item_brief_work_sets_priority_by_item_id() -> None:
    repos = FakeRepos()

    count = enqueue_item_brief_work(
        repos,
        news_item_ids=["news-1", "news-2"],
        priority_by_news_item_id={"news-1": 7},
        reason="news_item_processed",
        now_ms=NOW_MS,
        commit=False,
    )

    assert count == 2
    assert repos.news_projection_dirty_targets.enqueued == [
        {"projection_name": "brief_input", "target_kind": "news_item", "target_id": "news-1", "priority": 7},
        {"projection_name": "brief_input", "target_kind": "news_item", "target_id": "news-2"},
    ]


def test_source_quality_refresh_is_source_scoped_not_window_fanout() -> None:
    repos = FakeRepos()

    count = enqueue_source_quality_refresh(
        repos,
        source_ids=["source-1", "source-1", "source-2"],
        reason="news_fetch_run_finished",
        now_ms=NOW_MS,
        commit=False,
    )

    assert count == 2
    assert repos.news_projection_dirty_targets.enqueued == [
        {"projection_name": "source_quality", "target_kind": "source", "target_id": "source-1", "window": "_refresh"},
        {"projection_name": "source_quality", "target_kind": "source", "target_id": "source-2", "window": "_refresh"},
    ]


def test_claim_helpers_filter_by_semantic_work_type() -> None:
    repos = FakeRepos()
    repos.news_projection_dirty_targets.claim_rows = [
        {"projection_name": "page", "target_kind": "news_item", "target_id": "news-1", "window": ""}
    ]

    claimed = claim_page_projection_work(
        repos,
        limit=10,
        lease_ms=30_000,
        now_ms=NOW_MS,
        lease_owner="worker",
        commit=False,
    )

    assert claimed[0]["target_id"] == "news-1"
    assert repos.news_projection_dirty_targets.claim_calls[0]["projection_name"] == "page"

    repos.news_projection_dirty_targets.claim_rows = []
    claim_item_brief_work(repos, limit=1, lease_ms=30_000, now_ms=NOW_MS, lease_owner="worker", commit=False)
    claim_source_quality_work(repos, limit=1, lease_ms=30_000, now_ms=NOW_MS, lease_owner="worker", commit=False)
    assert repos.news_projection_dirty_targets.claim_calls[1]["projection_name"] == "brief_input"
    assert repos.news_projection_dirty_targets.claim_calls[2]["projection_name"] == "source_quality"


def test_page_ids_and_source_quality_refresh_expansion() -> None:
    page_rows = [
        {"projection_name": "page", "target_kind": "news_item", "target_id": "news-1", "window": ""},
        {"projection_name": "source_quality", "target_kind": "source", "target_id": "source-1", "window": "24h"},
    ]
    source_rows = [
        {"projection_name": "source_quality", "target_kind": "source", "target_id": "source-1", "window": "_refresh"},
        {"projection_name": "source_quality", "target_kind": "source", "target_id": "source-1", "window": "24h"},
    ]

    assert page_news_item_ids(page_rows) == ["news-1"]
    assert source_quality_windows_for_claimed(source_rows, configured_windows=("24h", "7d")) == [
        ("source-1", "24h"),
        ("source-1", "7d"),
    ]
```

- [ ] **Step 2: Run adapter tests and confirm they fail**

Run:

```bash
uv run pytest tests/unit/domains/news_intel/test_news_projection_work.py -q
```

Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement the adapter**

Create `src/parallax/domains/news_intel/runtime/news_projection_work.py` with:

```python
from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from typing import Any

PAGE_PROJECTION = "page"
ITEM_BRIEF_INPUT = "brief_input"
SOURCE_QUALITY = "source_quality"
SOURCE_QUALITY_REFRESH_WINDOW = "_refresh"


def enqueue_page_reprojection(
    repos: Any,
    *,
    news_item_ids: Iterable[str],
    reason: str,
    now_ms: int,
    source_watermark_ms_by_news_item_id: Mapping[str, int] | None = None,
    commit: bool = True,
) -> int:
    watermarks = dict(source_watermark_ms_by_news_item_id or {})
    targets = [
        _news_item_target(PAGE_PROJECTION, news_item_id, watermarks=watermarks)
        for news_item_id in _unique(news_item_ids)
    ]
    return _enqueue(repos, targets, reason=reason, now_ms=now_ms, commit=commit)


def enqueue_item_brief_work(
    repos: Any,
    *,
    news_item_ids: Iterable[str],
    reason: str,
    now_ms: int,
    priority_by_news_item_id: Mapping[str, int] | None = None,
    source_watermark_ms_by_news_item_id: Mapping[str, int] | None = None,
    commit: bool = True,
) -> int:
    priorities = dict(priority_by_news_item_id or {})
    watermarks = dict(source_watermark_ms_by_news_item_id or {})
    targets: list[dict[str, Any]] = []
    for news_item_id in _unique(news_item_ids):
        target = _news_item_target(ITEM_BRIEF_INPUT, news_item_id, watermarks=watermarks)
        if news_item_id in priorities:
            target["priority"] = int(priorities[news_item_id])
        targets.append(target)
    return _enqueue(repos, targets, reason=reason, now_ms=now_ms, commit=commit)


def enqueue_source_quality_refresh(
    repos: Any,
    *,
    source_ids: Iterable[str],
    reason: str,
    now_ms: int,
    due_at_ms: int | None = None,
    commit: bool = True,
) -> int:
    targets = [
        {
            "projection_name": SOURCE_QUALITY,
            "target_kind": "source",
            "target_id": source_id,
            "window": SOURCE_QUALITY_REFRESH_WINDOW,
        }
        for source_id in _unique(source_ids)
    ]
    if not targets:
        return 0
    return int(
        repos.news_projection_dirty_targets.enqueue_targets(
            targets,
            reason=reason,
            now_ms=now_ms,
            due_at_ms=due_at_ms,
            commit=commit,
        )
    )


def enqueue_source_quality_windows(
    repos: Any,
    *,
    source_windows: Iterable[tuple[str, str]],
    reason: str,
    now_ms: int,
    due_at_ms: int | None = None,
    source_watermark_ms_by_source_window: Mapping[tuple[str, str], int] | None = None,
    commit: bool = True,
) -> int:
    watermarks = dict(source_watermark_ms_by_source_window or {})
    targets = [
        {
            "projection_name": SOURCE_QUALITY,
            "target_kind": "source",
            "target_id": source_id,
            "window": window,
            "source_watermark_ms": int(watermarks.get((source_id, window), 0)),
        }
        for source_id, window in _unique_pairs(source_windows)
    ]
    if not targets:
        return 0
    return int(
        repos.news_projection_dirty_targets.enqueue_targets(
            targets,
            reason=reason,
            now_ms=now_ms,
            due_at_ms=due_at_ms,
            commit=commit,
        )
    )


def claim_page_projection_work(repos: Any, **kwargs: Any) -> list[dict[str, Any]]:
    return _claim(repos, projection_name=PAGE_PROJECTION, **kwargs)


def claim_item_brief_work(repos: Any, **kwargs: Any) -> list[dict[str, Any]]:
    return _claim(repos, projection_name=ITEM_BRIEF_INPUT, **kwargs)


def claim_source_quality_work(repos: Any, **kwargs: Any) -> list[dict[str, Any]]:
    return _claim(repos, projection_name=SOURCE_QUALITY, **kwargs)


def queue_item_brief_depth(repos: Any, *, now_ms: int) -> int:
    return int(repos.news_projection_dirty_targets.queue_depth(now_ms=now_ms, projection_name=ITEM_BRIEF_INPUT))


def mark_work_done(repos: Any, targets: Iterable[Mapping[str, Any]], *, now_ms: int, commit: bool = True) -> int:
    return int(repos.news_projection_dirty_targets.mark_done(targets, now_ms=now_ms, commit=commit))


def mark_work_error(
    repos: Any,
    targets: Iterable[Mapping[str, Any]],
    *,
    error: Exception | str,
    retry_ms: int,
    now_ms: int,
    count_attempt: bool = True,
    commit: bool = True,
) -> int:
    return int(
        repos.news_projection_dirty_targets.mark_error(
            targets,
            error=str(error),
            retry_ms=retry_ms,
            now_ms=now_ms,
            count_attempt=count_attempt,
            commit=commit,
        )
    )


def terminalize_work(repos: Any, targets: Iterable[Mapping[str, Any]], **kwargs: Any) -> int:
    return int(repos.news_projection_dirty_targets.terminalize_targets(targets, **kwargs))


def page_news_item_ids(rows: Iterable[Mapping[str, Any]]) -> list[str]:
    return _target_ids(rows, projection_name=PAGE_PROJECTION, target_kind="news_item", require_empty_window=True)


def item_brief_news_item_ids(rows: Iterable[Mapping[str, Any]]) -> list[str]:
    return _target_ids(rows, projection_name=ITEM_BRIEF_INPUT, target_kind="news_item", require_empty_window=True)


def source_quality_windows_for_claimed(
    rows: Iterable[Mapping[str, Any]],
    *,
    configured_windows: Sequence[str],
) -> list[tuple[str, str]]:
    configured = tuple(_unique(str(window).strip().lower() for window in configured_windows if str(window).strip()))
    result: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for row in rows:
        if str(row.get("projection_name") or "") != SOURCE_QUALITY:
            continue
        if str(row.get("target_kind") or "") != "source":
            continue
        source_id = str(row.get("target_id") or "")
        window = str(row.get("window") or "").strip().lower()
        windows = configured if window == SOURCE_QUALITY_REFRESH_WINDOW else (window,)
        for resolved_window in windows:
            key = (source_id, resolved_window)
            if source_id and resolved_window and key not in seen:
                seen.add(key)
                result.append(key)
    return result


def _claim(repos: Any, *, projection_name: str, **kwargs: Any) -> list[dict[str, Any]]:
    return list(repos.news_projection_dirty_targets.claim_due(projection_name=projection_name, **kwargs))


def _enqueue(repos: Any, targets: list[dict[str, Any]], *, reason: str, now_ms: int, commit: bool) -> int:
    if not targets:
        return 0
    return int(repos.news_projection_dirty_targets.enqueue_targets(targets, reason=reason, now_ms=now_ms, commit=commit))


def _news_item_target(
    projection_name: str,
    news_item_id: str,
    *,
    watermarks: Mapping[str, int],
) -> dict[str, Any]:
    target: dict[str, Any] = {"projection_name": projection_name, "target_kind": "news_item", "target_id": news_item_id}
    if news_item_id in watermarks:
        target["source_watermark_ms"] = int(watermarks[news_item_id])
    return target


def _target_ids(
    rows: Iterable[Mapping[str, Any]],
    *,
    projection_name: str,
    target_kind: str,
    require_empty_window: bool,
) -> list[str]:
    return _unique(
        str(row.get("target_id") or "")
        for row in rows
        if str(row.get("projection_name") or "") == projection_name
        and str(row.get("target_kind") or "") == target_kind
        and (not require_empty_window or str(row.get("window") or "") == "")
    )


def _unique(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        item = str(value or "")
        if not item or item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


def _unique_pairs(values: Iterable[tuple[str, str]]) -> list[tuple[str, str]]:
    seen: set[tuple[str, str]] = set()
    result: list[tuple[str, str]] = []
    for source_id, window in values:
        key = (str(source_id or ""), str(window or "").strip().lower())
        if not key[0] or not key[1] or key in seen:
            continue
        seen.add(key)
        result.append(key)
    return result
```

- [ ] **Step 4: Run adapter tests**

Run:

```bash
uv run pytest tests/unit/domains/news_intel/test_news_projection_work.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit adapter**

```bash
git add src/parallax/domains/news_intel/runtime/news_projection_work.py tests/unit/domains/news_intel/test_news_projection_work.py
git commit -m "feat: add semantic news projection work adapter"
```

## Task 3: Remove Fetch-To-Brief And Decouple Fetch Horizon

**Files:**
- Modify: `src/parallax/domains/news_intel/runtime/news_fetch_worker.py`
- Modify: `src/parallax/domains/news_intel/repositories/news_repository.py`
- Modify: `tests/unit/domains/news_intel/test_news_workers.py`

- [ ] **Step 1: Update fetch worker tests**

In `tests/unit/domains/news_intel/test_news_workers.py`, replace the fetch test that currently expects fetch to enqueue `brief_input` with:

```python
def test_news_fetch_worker_does_not_enqueue_brief_input_from_provider_signal() -> None:
    db = FakeDb()
    db.repo.claimed_sources = [_source_row("source-1")]
    db.feed_result.observations = [
        _provider_observation(
            source_item_key="item-1",
            title="Binance lists EXAMPLE token",
            provider_signal={"source": "provider", "status": "ready", "score": 95},
            provider_token_impacts=[{"symbol": "EXAMPLE", "score": 95}],
        )
    ]
    worker = _news_fetch_worker(db=db)

    result = worker.run_once_sync(now_ms=1_800_000)

    assert result.processed == 1
    assert all(target["projection_name"] != "brief_input" for target in db.dirty_targets.enqueued)
    assert {"projection_name": "page", "target_kind": "news_item", "target_id": "news-item-1"} in db.dirty_targets.enqueued
```

Add a context reprocess expectation near the context-observation fetch test:

```python
def test_news_fetch_context_update_marks_parent_for_reprocessing_not_brief_input() -> None:
    db = FakeDb()
    db.repo.claimed_sources = [_source_row("source-1")]
    db.feed_result.observations = [
        _provider_observation(source_item_key="parent-1", title="ETF inflow update")
    ]
    db.feed_result.context_observations = [
        _context_observation(parent_source_item_key="parent-1", context_item_id="ctx-1")
    ]
    worker = _news_fetch_worker(db=db)

    worker.run_once_sync(now_ms=1_800_000)

    assert db.repo.reprocess_news_item_ids == ["news-item-1"]
    assert all(target["projection_name"] != "brief_input" for target in db.dirty_targets.enqueued)
```

Add fetch horizon tests:

```python
def test_opennews_fetch_since_uses_cursor_overlap_not_agent_brief_age() -> None:
    since_ms = _source_fetch_since_ms(
        source={
            "provider_type": "opennews",
            "fetch_policy_json": {"rest_overlap_ms": 900_000},
        },
        source_cursor={"high_watermark_ms": 10_000_000},
        now_ms=20_000_000,
    )

    assert since_ms == 9_100_000


def test_opennews_first_fetch_since_uses_optional_fetch_policy_catchup_only() -> None:
    assert _source_fetch_since_ms(
        source={"provider_type": "opennews", "fetch_policy_json": {"max_initial_fetch_age_ms": 3_600_000}},
        source_cursor={},
        now_ms=20_000_000,
    ) == 16_400_000
    assert _source_fetch_since_ms(
        source={"provider_type": "opennews", "fetch_policy_json": {}},
        source_cursor={},
        now_ms=20_000_000,
    ) is None
```

Update fake repository with:

```python
def mark_news_items_for_reprocessing(self, *, news_item_ids, now_ms, commit=True):
    self.reprocess_news_item_ids.extend(str(item) for item in news_item_ids)
    return len(news_item_ids)
```

- [ ] **Step 2: Run targeted tests and confirm they fail**

Run:

```bash
uv run pytest tests/unit/domains/news_intel/test_news_workers.py::test_news_fetch_worker_does_not_enqueue_brief_input_from_provider_signal tests/unit/domains/news_intel/test_news_workers.py::test_news_fetch_context_update_marks_parent_for_reprocessing_not_brief_input tests/unit/domains/news_intel/test_news_workers.py::test_opennews_fetch_since_uses_cursor_overlap_not_agent_brief_age tests/unit/domains/news_intel/test_news_workers.py::test_opennews_first_fetch_since_uses_optional_fetch_policy_catchup_only -q
```

Expected: FAIL because fetch still enqueues brief work and uses the agent age constant.

- [ ] **Step 3: Add repository reprocess method**

In `src/parallax/domains/news_intel/repositories/news_repository.py`, add:

```python
    def mark_news_items_for_reprocessing(
        self,
        *,
        news_item_ids: Sequence[str],
        now_ms: int,
        commit: bool = True,
    ) -> int:
        scoped_ids = [str(item) for item in news_item_ids if str(item or "")]
        if not scoped_ids:
            return 0
        cursor = self.conn.execute(
            """
            UPDATE news_items
               SET lifecycle_status = 'raw',
                   updated_at_ms = GREATEST(updated_at_ms, %s)
             WHERE news_item_id = ANY(%s::text[])
               AND lifecycle_status = 'processed'
            """,
            (int(now_ms), scoped_ids),
        )
        if commit:
            self.conn.commit()
        return int(getattr(cursor, "rowcount", 0) or 0)
```

- [ ] **Step 4: Rewrite fetch worker imports and constructor**

In `src/parallax/domains/news_intel/runtime/news_fetch_worker.py`:

- Delete the import from `news_item_agent_policy`.
- Add:

```python
from parallax.domains.news_intel.runtime.news_projection_work import (
    enqueue_page_reprojection,
    enqueue_source_quality_refresh,
)
```

Change `__init__` to remove `source_quality_windows` and `self.source_quality_windows`.

- [ ] **Step 5: Replace fetch dirty target helpers**

In `NewsFetchWorker.run_once_sync`, replace `_enqueue_news_item_dirty_targets(... projection_names=("page",) ...)` with:

```python
metadata_dirty_count = enqueue_page_reprojection(
    repos,
    news_item_ids=changed_item_ids,
    reason="source_metadata_changed",
    now_ms=now,
    commit=False,
)
enqueue_source_quality_refresh(
    repos,
    source_ids=changed_source_ids,
    reason="source_metadata_changed",
    now_ms=now,
    commit=False,
)
```

In `_fetch_source`, replace both `_enqueue_source_quality_dirty_targets(...)` calls with:

```python
enqueue_source_quality_refresh(
    repos,
    source_ids=[source_id],
    reason="news_fetch_run_finished",
    now_ms=now_ms,
    commit=False,
)
```

In `_persist_entries`, delete `brief_dirty_news_item_ids`, `brief_ineligible_news_item_ids`, and the eligibility call. At the end of provider item persistence, use:

```python
enqueue_page_reprojection(
    repos,
    news_item_ids=dirty_news_item_ids,
    reason="news_item_written",
    now_ms=fetched_at_ms,
    commit=False,
)
```

For context parents:

```python
if context_parent_ids:
    repository.mark_news_items_for_reprocessing(
        news_item_ids=context_parent_ids,
        now_ms=fetched_at_ms,
        commit=False,
    )
    enqueue_page_reprojection(
        repos,
        news_item_ids=context_parent_ids,
        reason="news_context_written",
        now_ms=fetched_at_ms,
        commit=False,
    )
```

Delete `_enqueue_news_item_dirty_targets`, `_enqueue_source_quality_dirty_targets`, and `_source_quality_windows`.

- [ ] **Step 6: Replace OpenNews since calculation**

In `news_fetch_worker.py`, add helpers:

```python
def _source_fetch_since_ms(
    *,
    source: Mapping[str, Any],
    source_cursor: Mapping[str, Any],
    now_ms: int,
) -> int | None:
    if str(source.get("provider_type") or "").strip().lower() != "opennews":
        return None
    cursor_high_watermark_ms = _cursor_high_watermark_ms(source_cursor)
    if cursor_high_watermark_ms is not None:
        return max(0, cursor_high_watermark_ms - _fetch_policy_overlap_ms(source, source_cursor))
    max_initial_fetch_age_ms = _fetch_policy_int(source, "max_initial_fetch_age_ms")
    if max_initial_fetch_age_ms is None:
        max_initial_fetch_age_ms = _fetch_policy_int(source, "max_catchup_age_ms")
    if max_initial_fetch_age_ms is None:
        return None
    return max(0, int(now_ms) - max_initial_fetch_age_ms)


def _fetch_policy_overlap_ms(source: Mapping[str, Any], source_cursor: Mapping[str, Any]) -> int:
    value = _fetch_policy_int(source, "rest_overlap_ms")
    if value is None:
        value = _fetch_policy_int(source, "overlap_ms")
    if value is None:
        try:
            value = int(source_cursor.get("overlap_ms") or 0)
        except (TypeError, ValueError):
            value = 0
    return max(0, int(value or 0))


def _fetch_policy_int(source: Mapping[str, Any], key: str) -> int | None:
    raw = source.get("fetch_policy_json")
    policy = dict(raw) if isinstance(raw, Mapping) else {}
    value = policy.get(key)
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None
```

- [ ] **Step 7: Run fetch tests**

Run:

```bash
uv run pytest tests/unit/domains/news_intel/test_news_workers.py -q
```

Expected: PASS after fake updates are aligned.

- [ ] **Step 8: Commit fetch simplification**

```bash
git add src/parallax/domains/news_intel/runtime/news_fetch_worker.py src/parallax/domains/news_intel/repositories/news_repository.py tests/unit/domains/news_intel/test_news_workers.py
git commit -m "refactor: remove fetch brief admission"
```

## Task 4: Make Processed Item Admission The Single Brief Owner

**Files:**
- Modify: `src/parallax/domains/news_intel/services/news_item_agent_policy.py`
- Modify: `src/parallax/domains/news_intel/runtime/news_item_process_worker.py`
- Modify: `src/parallax/domains/news_intel/runtime/news_item_brief_worker.py`
- Modify: `src/parallax/app/runtime/projection_dirty_targets.py`
- Modify: `tests/unit/domains/news_intel/test_news_workers.py`
- Modify: `tests/unit/domains/news_intel/test_news_item_brief_worker.py`
- Create or modify: `tests/unit/domains/news_intel/test_news_item_agent_policy.py`

- [ ] **Step 1: Add policy tests for processed-state admission**

Create or update `tests/unit/domains/news_intel/test_news_item_agent_policy.py`:

```python
from __future__ import annotations

from parallax.domains.news_intel.services.news_item_agent_policy import (
    news_item_agent_brief_eligibility,
    news_item_agent_brief_priority,
)


NOW_MS = 10_000_000


def _item(**overrides):
    item = {
        "news_item_id": "news-1",
        "published_at_ms": NOW_MS - 60_000,
        "lifecycle_status": "processed",
        "content_class": "exchange_listing",
        "content_classification_json": {"policy_version": "news_content_classification_v1"},
        "provider_signal_json": {"source": "provider", "status": "ready", "score": 91},
    }
    item.update(overrides)
    return item


def test_brief_eligibility_requires_processed_item_state() -> None:
    result = news_item_agent_brief_eligibility(
        item=_item(lifecycle_status="raw"),
        token_mentions=[{"resolution_status": "known_symbol"}],
        fact_candidates=[],
        context_items=[],
        now_ms=NOW_MS,
    )

    assert result.eligible is False
    assert result.reason == "item_not_processed"


def test_brief_eligibility_requires_processed_market_context() -> None:
    result = news_item_agent_brief_eligibility(
        item=_item(),
        token_mentions=[],
        fact_candidates=[],
        context_items=[],
        now_ms=NOW_MS,
    )

    assert result.eligible is False
    assert result.reason == "no_processed_market_context"


def test_brief_eligibility_accepts_provider_score_after_processing() -> None:
    result = news_item_agent_brief_eligibility(
        item=_item(),
        token_mentions=[{"resolution_status": "known_symbol"}],
        fact_candidates=[],
        context_items=[],
        now_ms=NOW_MS,
    )

    assert result.eligible is True
    assert result.reason == "eligible"


def test_brief_priority_uses_provider_score_and_processed_context() -> None:
    priority = news_item_agent_brief_priority(
        item=_item(),
        token_mentions=[{"resolution_status": "known_symbol"}],
        fact_candidates=[],
        context_items=[{"context_item_id": "ctx-1"}],
    )

    assert priority == 4
```

- [ ] **Step 2: Run policy tests and confirm they fail**

Run:

```bash
uv run pytest tests/unit/domains/news_intel/test_news_item_agent_policy.py -q
```

Expected: FAIL because the policy still accepts only one mapping and uses raw provider score.

- [ ] **Step 3: Replace policy signature and rules**

In `news_item_agent_policy.py`, change the public functions to:

```python
def news_item_agent_brief_eligibility(
    *,
    item: Mapping[str, Any],
    token_mentions: Sequence[Mapping[str, Any]],
    fact_candidates: Sequence[Mapping[str, Any]],
    context_items: Sequence[Mapping[str, Any]],
    now_ms: int,
    max_published_age_ms: int = NEWS_ITEM_AGENT_BRIEF_MAX_PUBLISHED_AGE_MS,
) -> NewsItemAgentBriefEligibility:
    if str(item.get("lifecycle_status") or "").strip().lower() != "processed":
        return NewsItemAgentBriefEligibility(eligible=False, reason="item_not_processed")
    if not _mapping(item.get("content_classification_json")):
        return NewsItemAgentBriefEligibility(eligible=False, reason="classification_missing")
    if str(item.get("content_class") or "").strip().lower() == "low_signal":
        return NewsItemAgentBriefEligibility(eligible=False, reason="low_signal_content")

    provider_signal = _mapping(item.get("provider_signal_json"))
    if str(provider_signal.get("source") or "").strip().lower() != "provider":
        return NewsItemAgentBriefEligibility(eligible=False, reason="source_not_provider_signal")
    score = _optional_int(provider_signal.get("score"))
    if score is None or score < NEWS_ITEM_AGENT_BRIEF_MIN_PROVIDER_SCORE:
        return NewsItemAgentBriefEligibility(eligible=False, reason="below_score_threshold")
    if not _has_processed_market_context(
        token_mentions=token_mentions,
        fact_candidates=fact_candidates,
        context_items=context_items,
    ):
        return NewsItemAgentBriefEligibility(eligible=False, reason="no_processed_market_context")

    published_at_ms = _optional_int(item.get("published_at_ms"))
    if published_at_ms is None:
        return NewsItemAgentBriefEligibility(eligible=False, reason="published_at_missing")
    age_ms = int(now_ms) - int(published_at_ms)
    if age_ms < 0:
        return NewsItemAgentBriefEligibility(eligible=False, reason="published_in_future")
    if age_ms > max(0, int(max_published_age_ms)):
        return NewsItemAgentBriefEligibility(eligible=False, reason="published_too_old")
    return NewsItemAgentBriefEligibility(eligible=True, reason="eligible")
```

Add:

```python
def news_item_agent_brief_priority(
    *,
    item: Mapping[str, Any],
    token_mentions: Sequence[Mapping[str, Any]],
    fact_candidates: Sequence[Mapping[str, Any]],
    context_items: Sequence[Mapping[str, Any]],
) -> int:
    provider_signal = _mapping(item.get("provider_signal_json"))
    score = _optional_int(provider_signal.get("score"))
    priority = 100 - score if score is not None else 100
    if str(item.get("content_class") or "") in {"exchange_listing", "security_hack", "regulation"}:
        priority -= 5
    if _has_processed_market_context(
        token_mentions=token_mentions,
        fact_candidates=fact_candidates,
        context_items=context_items,
    ):
        priority -= 1
    return max(0, min(100, priority))
```

Add helper:

```python
def _has_processed_market_context(
    *,
    token_mentions: Sequence[Mapping[str, Any]],
    fact_candidates: Sequence[Mapping[str, Any]],
    context_items: Sequence[Mapping[str, Any]],
) -> bool:
    if context_items:
        return True
    for mention in token_mentions:
        if str(mention.get("resolution_status") or "") not in {"non_crypto", "nil", ""}:
            return True
    for candidate in fact_candidates:
        if str(candidate.get("validation_status") or candidate.get("status") or "") != "rejected":
            return True
    return False
```

Import `Sequence` from `collections.abc`. Remove positional-call support.

- [ ] **Step 4: Update item process admission**

In `news_item_process_worker.py`, delete constructor `source_quality_windows`, `self.source_quality_windows`, `_source_quality_windows`, and `_dirty_targets_for_processed_item`.

Add imports:

```python
from parallax.domains.news_intel.runtime.news_projection_work import (
    enqueue_item_brief_work,
    enqueue_page_reprojection,
)
```

After `mark_item_processed`, replace direct dirty-target enqueue with:

```python
processed_item = {
    **item_payload,
    "lifecycle_status": "processed",
    "content_class": classification.content_class,
    "content_tags_json": classification.content_tags,
    "content_classification_json": classification.classification_payload,
}
enqueue_page_reprojection(
    repos,
    news_item_ids=[news_item_id],
    reason="news_item_processed",
    now_ms=now,
    commit=False,
)
eligibility = news_item_agent_brief_eligibility(
    item=processed_item,
    token_mentions=[_object_payload(mention) for mention in mentions],
    fact_candidates=[_object_payload(candidate) for candidate in candidates],
    context_items=[],
    now_ms=now,
)
if eligibility.eligible:
    enqueue_item_brief_work(
        repos,
        news_item_ids=[news_item_id],
        priority_by_news_item_id={
            news_item_id: news_item_agent_brief_priority(
                item=processed_item,
                token_mentions=[_object_payload(mention) for mention in mentions],
                fact_candidates=[_object_payload(candidate) for candidate in candidates],
                context_items=[],
            )
        },
        reason="news_item_processed",
        now_ms=now,
        commit=False,
    )
```

Add a small object serializer near `_json_list`:

```python
def _object_payload(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    dump = getattr(value, "model_dump", None)
    if dump is not None:
        return dict(dump(mode="json"))
    return dict(getattr(value, "__dict__", {}) or {})
```

- [ ] **Step 5: Update brief worker eligibility recheck**

In `news_item_brief_worker.py`, change:

```python
eligibility = news_item_agent_brief_eligibility(_dict(candidate.get("item") or candidate), now_ms=now)
```

to:

```python
eligibility = news_item_agent_brief_eligibility(
    item=_dict(candidate.get("item") or candidate),
    token_mentions=_list_of_dicts(candidate.get("token_mentions")),
    fact_candidates=_list_of_dicts(candidate.get("fact_candidates")),
    context_items=_list_of_dicts(candidate.get("context_items")),
    now_ms=now,
)
```

- [ ] **Step 6: Update ops repair**

In `projection_dirty_targets.py`, remove direct raw target construction for brief items. For selected `brief_input`, fetch rows with processed context counts only. Translate rows into:

```python
eligibility = news_item_agent_brief_eligibility(
    item=row,
    token_mentions=_json_list(row.get("token_mentions_json")),
    fact_candidates=_json_list(row.get("fact_candidates_json")),
    context_items=_json_list(row.get("context_items_json")),
    now_ms=now_ms,
)
```

Then call `enqueue_item_brief_work(...)` with the new priority signature. Page repair calls `enqueue_page_reprojection(...)`; source-quality repair calls `enqueue_source_quality_refresh(...)`.

- [ ] **Step 7: Run policy, process, brief, and ops tests**

Run:

```bash
uv run pytest tests/unit/domains/news_intel/test_news_item_agent_policy.py tests/unit/domains/news_intel/test_news_workers.py tests/unit/domains/news_intel/test_news_item_brief_worker.py tests/unit/test_projection_dirty_targets_runtime.py -q
```

Expected: PASS. If `tests/unit/test_projection_dirty_targets_runtime.py` is absent in this checkout, run `rg -n "enqueue_projection_dirty_targets" tests` and execute the matching test file instead.

- [ ] **Step 8: Commit processed-state admission**

```bash
git add src/parallax/domains/news_intel/services/news_item_agent_policy.py src/parallax/domains/news_intel/runtime/news_item_process_worker.py src/parallax/domains/news_intel/runtime/news_item_brief_worker.py src/parallax/app/runtime/projection_dirty_targets.py tests/unit/domains/news_intel/test_news_item_agent_policy.py tests/unit/domains/news_intel/test_news_workers.py tests/unit/domains/news_intel/test_news_item_brief_worker.py
git commit -m "refactor: centralize news brief admission after processing"
```

## Task 5: Decouple Source Quality From Item Hot Path

**Files:**
- Modify: `src/parallax/app/runtime/worker_factories/news_intel.py`
- Modify: `src/parallax/domains/news_intel/runtime/news_source_quality_projection_worker.py`
- Modify: `src/parallax/domains/news_intel/runtime/news_item_brief_worker.py`
- Modify: `src/parallax/platform/config/settings.py`
- Modify: `src/parallax/app/runtime/worker_manifest.py`
- Modify: `tests/unit/domains/news_intel/test_news_projection_dirty_targets.py`
- Modify: `tests/unit/domains/news_intel/test_source_quality_projection.py`
- Modify: `tests/architecture/test_worker_inventory_contract.py` indirectly through docs in Task 8.

- [ ] **Step 1: Update source-quality tests**

In `tests/unit/domains/news_intel/test_news_projection_dirty_targets.py`, change `test_fetch_worker_enqueues_news_item_and_source_quality_dirty_for_inserted_and_updated_news_items_only` so the second enqueue is one source refresh intent:

```python
assert repos.dirty.enqueued[1] == {
    "rows": [
        {"projection_name": "source_quality", "target_kind": "source", "target_id": "source-1", "window": "_refresh"}
    ],
    "reason": "news_fetch_run_finished",
    "now_ms": NOW_MS,
    "commit": False,
}
```

Rename `test_process_worker_enqueues_page_and_source_quality_dirty_in_same_transaction_after_writes` to `test_process_worker_enqueues_page_and_brief_dirty_in_same_transaction_after_writes`. Remove the `source_quality_windows=("4h", "24h")` constructor argument and assert no source-quality rows are created:

```python
assert repos.dirty.enqueued == [
    {
        "rows": [
            {"projection_name": "page", "target_kind": "news_item", "target_id": "news-1"},
            {"projection_name": "brief_input", "target_kind": "news_item", "target_id": "news-1", "priority": 14},
        ],
        "reason": "news_item_processed",
        "now_ms": NOW_MS,
        "commit": False,
    }
]
```

Rename `test_brief_worker_enqueues_page_and_source_quality_dirty_in_same_transaction_after_current_brief_write` to `test_brief_worker_enqueues_only_page_dirty_after_current_brief_write` and assert the brief worker no longer creates source-quality work:

```python
assert repos.dirty.enqueued == [
    {
        "rows": [{"projection_name": "page", "target_kind": "news_item", "target_id": "news-1"}],
        "reason": "news_item_brief_updated",
        "now_ms": NOW_MS,
        "commit": False,
    }
]
```

In `tests/unit/domains/news_intel/test_source_quality_projection.py`, update the worker claim fixture to use a refresh target and assert expansion happens inside `NewsSourceQualityProjectionWorker`:

```python
dirty = FakeDirtyTargets(
    claimed=[
        {
            "projection_name": "source_quality",
            "target_kind": "source",
            "target_id": "source-1",
            "window": "_refresh",
            "payload_hash": "hash-1",
            "lease_owner": "news_source_quality_projection",
            "attempt_count": 0,
        }
    ]
)

worker = NewsSourceQualityProjectionWorker(
    name="news_source_quality_projection",
    settings=SimpleNamespace(batch_size=10, lease_ms=30_000, retry_ms=30_000, windows=("4h", "24h")),
    db=FakeDB(news=repo, dirty=dirty),
    telemetry=object(),
    wake_bus=None,
)

result = worker.run_once_sync(now_ms=NOW_MS)

assert result.processed == 2
assert repo.list_calls == [{"source_windows": [("source-1", "4h"), ("source-1", "24h")], "now_ms": NOW_MS}]
```

- [ ] **Step 2: Run source-quality tests and confirm they fail**

Run:

```bash
uv run pytest tests/unit/domains/news_intel/test_news_projection_dirty_targets.py tests/unit/domains/news_intel/test_source_quality_projection.py -q
```

Expected: FAIL on old per-window upstream fanout.

- [ ] **Step 3: Remove factory window injection**

In `worker_factories/news_intel.py`, delete these constructor kwargs:

```python
source_quality_windows=workers.news_source_quality_projection.windows,
```

from `NewsFetchWorker`, `NewsItemProcessWorker`, and `NewsItemBriefWorker`.

- [ ] **Step 4: Update brief worker post-write dirties**

In `news_item_brief_worker.py`, remove `source_quality_windows` constructor state and `_source_quality_windows`.

In `_upsert_current`, replace the enqueue list with:

```python
enqueue_page_reprojection(
    repos,
    news_item_ids=[packet.news_item.news_item_id],
    reason="news_item_brief_updated",
    now_ms=int(computed_at_ms),
    commit=False,
)
```

Do not enqueue source-quality refresh from brief completion.

- [ ] **Step 5: Update source quality worker to own expansion**

In `news_source_quality_projection_worker.py`, import semantic helpers:

```python
from parallax.domains.news_intel.runtime.news_projection_work import (
    claim_source_quality_work,
    enqueue_page_reprojection,
    enqueue_source_quality_windows,
    mark_work_done,
    mark_work_error,
    source_quality_windows_for_claimed,
)
```

Replace `claim_due(... projection_name="source_quality" ...)` with `claim_source_quality_work(...)`.

Replace:

```python
source_windows = _source_windows(claimed)
```

with:

```python
source_windows = source_quality_windows_for_claimed(claimed, configured_windows=windows)
```

Replace page dirty enqueue with `enqueue_page_reprojection(...)`.

Replace future target enqueue with `enqueue_source_quality_windows(...)`, passing:

```python
source_watermark_ms_by_source_window={
    (str(target["target_id"]), str(target["window"])): int(target.get("source_watermark_ms") or 0)
    for target in future_targets
}
```

Then delete `_source_windows` and `_page_dirty_targets`.

- [ ] **Step 6: Update source-quality default wake inputs**

In `settings.py`, change:

```python
wakes_on: tuple[str, ...] = ("news_item_written",)
```

In `worker_manifest.py`, change `news_source_quality_projection.wakes_on` to:

```python
wakes_on=("news_item_written",)
```

Keep `windows` validation unchanged.

- [ ] **Step 7: Run decoupling and architecture tests**

Run:

```bash
uv run pytest tests/unit/domains/news_intel/test_news_projection_work.py tests/unit/domains/news_intel/test_news_projection_dirty_targets.py tests/unit/domains/news_intel/test_source_quality_projection.py tests/architecture/test_news_intel_kiss_simplification.py -q
```

Expected: PASS.

- [ ] **Step 8: Commit source-quality decoupling**

```bash
git add src/parallax/app/runtime/worker_factories/news_intel.py src/parallax/domains/news_intel/runtime/news_source_quality_projection_worker.py src/parallax/domains/news_intel/runtime/news_item_brief_worker.py src/parallax/platform/config/settings.py src/parallax/app/runtime/worker_manifest.py tests/unit/domains/news_intel/test_news_projection_dirty_targets.py tests/unit/domains/news_intel/test_source_quality_projection.py
git commit -m "refactor: move news source quality windows into projection worker"
```

## Task 6: Hide Dirty Strings From Page And Brief Workers

**Files:**
- Modify: `src/parallax/domains/news_intel/runtime/news_page_projection_worker.py`
- Modify: `src/parallax/domains/news_intel/runtime/news_item_brief_worker.py`
- Modify: `tests/unit/domains/news_intel/test_news_page_projection.py`
- Modify: `tests/unit/domains/news_intel/test_news_item_brief_worker.py`
- Test: `tests/architecture/test_news_intel_kiss_simplification.py`

- [ ] **Step 1: Update page worker to use adapter**

In `news_page_projection_worker.py`, import:

```python
from parallax.domains.news_intel.runtime.news_projection_work import (
    claim_page_projection_work,
    mark_work_done,
    mark_work_error,
    page_news_item_ids,
)
```

Replace direct `claim_due`, `_target_ids`, `_processed_keys`, `mark_error`, and `mark_done` calls with adapter helpers. Delete local `_target_ids`, `_processed_keys`, and `_unique_values`.

- [ ] **Step 2: Update brief worker to use adapter**

In `news_item_brief_worker.py`, import:

```python
from parallax.domains.news_intel.runtime.news_projection_work import (
    claim_item_brief_work,
    item_brief_news_item_ids,
    mark_work_done,
    mark_work_error,
    queue_item_brief_depth,
    terminalize_work,
)
```

Replace:

- `_claim_targets` internals with `claim_item_brief_work`.
- `_queue_depth` internals with `queue_item_brief_depth`.
- `_target_ids` with `item_brief_news_item_ids`.
- `_mark_targets_done`, `_mark_targets_error`, and `_terminalize_claimed_target` internals with adapter helpers.

Delete local raw projection-string filtering.

- [ ] **Step 3: Run worker tests**

Run:

```bash
uv run pytest tests/unit/domains/news_intel/test_news_item_brief_worker.py tests/unit/domains/news_intel/test_news_page_projection.py tests/architecture/test_news_intel_kiss_simplification.py -q
```

Expected: PASS and architecture scan sees no raw dirty projection strings in worker files.

- [ ] **Step 4: Commit dirty-string hiding**

```bash
git add src/parallax/domains/news_intel/runtime/news_page_projection_worker.py src/parallax/domains/news_intel/runtime/news_item_brief_worker.py tests/unit/domains/news_intel/test_news_item_brief_worker.py tests/unit/domains/news_intel/test_news_page_projection.py
git commit -m "refactor: hide news dirty target strings behind adapter"
```

## Task 7: Hard-Cut News Item Brief Stage Adapter Name

**Files:**
- Delete: `src/parallax/domains/news_intel/services/news_item_brief_runtime.py`
- Create: `src/parallax/domains/news_intel/services/news_item_brief_stage.py`
- Modify: `src/parallax/integrations/model_execution/news_item_brief_agent_client.py`
- Rename: `tests/unit/domains/news_intel/test_news_item_brief_runtime.py` to `tests/unit/domains/news_intel/test_news_item_brief_stage.py`
- Modify docs references that mention `news_item_brief_runtime.py`.

- [ ] **Step 1: Rename test imports**

Rename the test file:

```bash
git mv tests/unit/domains/news_intel/test_news_item_brief_runtime.py tests/unit/domains/news_intel/test_news_item_brief_stage.py
```

Change imports inside the renamed test to:

```python
from parallax.domains.news_intel.services.news_item_brief_stage import (
    build_news_item_brief_stage,
)
```

- [ ] **Step 2: Run renamed test and confirm it fails**

Run:

```bash
uv run pytest tests/unit/domains/news_intel/test_news_item_brief_stage.py -q
```

Expected: FAIL because `news_item_brief_stage.py` does not exist yet.

- [ ] **Step 3: Rename implementation without alias**

Run:

```bash
git mv src/parallax/domains/news_intel/services/news_item_brief_runtime.py src/parallax/domains/news_intel/services/news_item_brief_stage.py
```

In `news_item_brief_agent_client.py`, change:

```python
from parallax.domains.news_intel.services.news_item_brief_stage import (
    build_news_item_brief_stage,
)
```

Do not leave `news_item_brief_runtime.py` behind.

- [ ] **Step 4: Update docs references**

Run:

```bash
rg -n "news_item_brief_runtime" docs src tests
```

Replace active references with `news_item_brief_stage.py` and phrase it as the item brief stage adapter. Historical completed specs may be left only if the file path is part of old dated history and architecture tests do not scan them.

- [ ] **Step 5: Run stage and client tests**

Run:

```bash
uv run pytest tests/unit/domains/news_intel/test_news_item_brief_stage.py tests/unit/integrations/model_execution/test_news_item_brief_agent_client.py tests/architecture/test_news_intel_kiss_simplification.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit stage rename**

```bash
git add src/parallax/domains/news_intel/services/news_item_brief_stage.py src/parallax/integrations/model_execution/news_item_brief_agent_client.py tests/unit/domains/news_intel/test_news_item_brief_stage.py docs
git add -u src/parallax/domains/news_intel/services/news_item_brief_runtime.py tests/unit/domains/news_intel/test_news_item_brief_runtime.py
git commit -m "refactor: rename news item brief stage adapter"
```

## Task 8: Hard-Cut Public Signal Envelope

**Files:**
- Modify: `src/parallax/domains/news_intel/services/news_page_projection.py`
- Modify: `src/parallax/domains/news_intel/repositories/news_repository.py` if public query helpers assume top-level old signal keys.
- Modify: `tests/unit/domains/news_intel/test_news_page_projection.py`
- Modify frontend model/UI files that currently read old top-level signal keys:
  - First read: `docs/FRONTEND.md`
  - Modify: `web/src/shared/model/newsIntel.ts`
  - Modify: `web/src/features/news/model/newsSignalViewModel.ts`
  - Modify: `web/src/features/news/ui/NewsItemEvidencePage.tsx`
  - Modify: `web/src/features/news/ui/NewsTape.tsx`

- [ ] **Step 1: Add hard-cut page projection tests**

In `tests/unit/domains/news_intel/test_news_page_projection.py`, add:

```python
def test_page_signal_envelope_separates_provider_agent_display_and_alert() -> None:
    row = build_news_page_row(
        item={
            "news_item_id": "news-1",
            "title": "Binance lists EXAMPLE",
            "summary": "Listing starts today",
            "source_domain": "6551.io",
            "canonical_url": "https://example.com/news-1",
            "published_at_ms": 1_000,
            "provider_signal_json": {
                "source": "provider",
                "provider": "opennews",
                "status": "ready",
                "direction": "bullish",
                "score": 90,
                "method": "opennews.aiRating",
            },
        },
        token_mentions=[],
        fact_candidates=[],
        agent_brief={
            "status": "ready",
            "direction": "bullish",
            "decision_class": "watch",
            "brief_json": {"summary_zh": "交易所上线带来流动性关注。"},
            "computed_at_ms": 2_000,
        },
        computed_at_ms=3_000,
    )

    assert set(row["signal"]) == {"display_signal", "provider_signal", "agent_signal", "alert_eligibility"}
    assert row["signal"]["display_signal"]["source"] == "agent"
    assert row["signal"]["provider_signal"]["provider"] == "opennews"
    assert row["signal"]["agent_signal"]["status"] == "ready"
    assert row["signal"]["alert_eligibility"]["external_push_ready"] is True
```

Add delayed-source-status test:

```python
def test_page_source_status_defaults_unknown_when_source_quality_missing() -> None:
    row = build_news_page_row(
        item={
            "news_item_id": "news-1",
            "title": "Market update",
            "summary": "",
            "source_domain": "example.com",
            "published_at_ms": 1_000,
            "source_quality_status": None,
            "provider_signal_json": {},
        },
        token_mentions=[],
        fact_candidates=[],
        computed_at_ms=2_000,
    )

    assert row["source"]["source_quality_status"] == "unknown"
```

- [ ] **Step 2: Run page tests and confirm they fail**

Run:

```bash
uv run pytest tests/unit/domains/news_intel/test_news_page_projection.py -q
```

Expected: FAIL because `signal` still has top-level display fields and source status may omit unknown.

- [ ] **Step 3: Replace signal shape**

In `news_page_projection.py`, make `_page_signal` return only:

```python
return {
    "display_signal": display_signal,
    "provider_signal": provider_payload,
    "agent_signal": agent_signal,
    "alert_eligibility": alert_eligibility,
}
```

Use current display computation for `display_signal`; remove top-level `source`, `status`, `direction`, `score`, and `method` from `row["signal"]`. Keep those fields inside `display_signal`.

In `_source_payload`, change:

```python
"source_quality_status": item.get("source_quality_status") or "unknown",
```

- [ ] **Step 4: Update frontend signal consumers**

Run:

```bash
rg -n "signal\\.|signal_json|alert_eligibility|provider_signal|display_signal" web/src
```

If files are returned, read `docs/FRONTEND.md`, then update TypeScript types and render code to use:

```ts
row.signal.display_signal
row.signal.provider_signal
row.signal.agent_signal
row.signal.alert_eligibility
```

Remove old top-level signal fallback logic. Run:

```bash
npm run lint
```

Expected: PASS if frontend files are touched.

- [ ] **Step 5: Run backend page tests**

Run:

```bash
uv run pytest tests/unit/domains/news_intel/test_news_page_projection.py tests/unit/domains/news_intel/test_news_workers.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit signal envelope**

```bash
git add src/parallax/domains/news_intel/services/news_page_projection.py tests/unit/domains/news_intel/test_news_page_projection.py
git add web/src docs/FRONTEND.md
git commit -m "refactor: expose explicit news signal envelope"
```

Only include `web/src` in the commit if frontend files changed.

## Task 9: Drop Dead Read-Model Watermark Columns

**Files:**
- Create: `src/parallax/platform/db/alembic/versions/20260601_0141_news_intel_kiss_simplification.py`
- Modify: `src/parallax/domains/news_intel/repositories/news_repository.py` if any serving-row SQL still selects these columns.
- Modify: tests that assert serving-table `source_watermark_ms`.

- [ ] **Step 1: Confirm serving columns are unused**

Run:

```bash
rg -n "news_page_rows.*source_watermark_ms|news_source_quality_rows.*source_watermark_ms|source_watermark_ms" src/parallax/domains/news_intel src/parallax/app/surfaces tests/unit/domains/news_intel
```

Expected: dirty-target uses remain; `replace_page_rows_for_items` and `replace_source_quality_rows` do not write serving-table `source_watermark_ms`.

- [ ] **Step 2: Add hard-cut migration**

Create `src/parallax/platform/db/alembic/versions/20260601_0141_news_intel_kiss_simplification.py`:

```python
"""Simplify News Intel read-model lifecycle columns."""

from __future__ import annotations

from alembic import op

revision = "20260601_0141"
down_revision = "20260601_0140"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute("ALTER TABLE news_page_rows DROP COLUMN source_watermark_ms")
    op.execute("ALTER TABLE news_source_quality_rows DROP COLUMN source_watermark_ms")
    op.execute("ANALYZE news_page_rows")
    op.execute("ANALYZE news_source_quality_rows")


def downgrade() -> None:
    """No downgrade for hard-cut removal of unused News serving watermarks."""
```

- [ ] **Step 3: Run migration/import checks**

Run:

```bash
uv run python -m compileall src/parallax/platform/db/alembic/versions/20260601_0141_news_intel_kiss_simplification.py
```

Expected: PASS.

- [ ] **Step 4: Commit migration**

```bash
git add src/parallax/platform/db/alembic/versions/20260601_0141_news_intel_kiss_simplification.py
git commit -m "db: drop unused news read model watermarks"
```

## Task 10: Update Worker Inventory And Docs

**Files:**
- Modify: `docs/ARCHITECTURE.md`
- Modify: `docs/WORKERS.md`
- Modify: `docs/CONTRACTS.md`
- Modify: `docs/RELIABILITY.md` if it describes source-quality wake/fanout.
- Modify: `src/parallax/domains/news_intel/ARCHITECTURE.md`

- [ ] **Step 1: Update News domain architecture**

In `src/parallax/domains/news_intel/ARCHITECTURE.md`, describe:

```text
Required core:
news_fetch -> news_item_process -> news_page_projection

Optional enhancement:
news_item_process -> news_item_brief -> news_page_projection

Operational projection:
news_fetch/source refresh -> news_source_quality_projection -> page dirty only when compact source status changes
```

Remove wording that says fetch creates brief work or that process/brief fan out source-quality windows.

- [ ] **Step 2: Update worker inventory**

In `docs/WORKERS.md`:

- `news_fetch` writes facts and semantic page/source refresh dirty work; wake-out remains `news_item_written`.
- `news_item_process` writes deterministic facts and may create item brief work after processed-state admission.
- `news_item_brief` input is semantic item brief work, not reader-facing `projection_name='brief_input'`.
- `news_page_projection` input is semantic page reprojection work.
- `news_source_quality_projection` wake-in is `news_item_written`; input is semantic source-quality refresh/window work; windows are owned by its settings.

Update the `<!-- worker-inventory-keys: ... -->` marker only if it is accidentally changed; the worker set must remain unchanged.

- [ ] **Step 3: Update contracts**

In `docs/CONTRACTS.md`, document the hard-cut News row signal shape:

```json
{
  "signal": {
    "display_signal": {},
    "provider_signal": {},
    "agent_signal": {},
    "alert_eligibility": {}
  }
}
```

State that source quality may be `unknown`, `stale`, or `degraded` and does not block `/news` rows.

- [ ] **Step 4: Run docs/worker architecture tests**

Run:

```bash
uv run pytest tests/architecture/test_worker_inventory_contract.py tests/architecture/test_news_intel_kiss_simplification.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit docs**

```bash
git add docs/ARCHITECTURE.md docs/WORKERS.md docs/CONTRACTS.md docs/RELIABILITY.md src/parallax/domains/news_intel/ARCHITECTURE.md src/parallax/app/runtime/worker_manifest.py src/parallax/platform/config/settings.py
git commit -m "docs: simplify news intel worker flow"
```

Only include `docs/RELIABILITY.md` if changed.

## Task 11: Full Verification

**Files:**
- No new source files unless tests expose a missed hard-cut violation.

- [ ] **Step 1: Run focused News suite**

Run:

```bash
uv run pytest \
  tests/unit/domains/news_intel/test_news_projection_work.py \
  tests/unit/domains/news_intel/test_news_item_agent_policy.py \
  tests/unit/domains/news_intel/test_news_workers.py \
  tests/unit/domains/news_intel/test_news_item_brief_worker.py \
  tests/unit/domains/news_intel/test_news_page_projection.py \
  tests/unit/domains/news_intel/test_news_projection_dirty_targets.py \
  tests/unit/domains/news_intel/test_source_quality_projection.py \
  tests/unit/integrations/model_execution/test_news_item_brief_agent_client.py \
  -q
```

Expected: PASS.

- [ ] **Step 2: Run architecture gates**

Run:

```bash
uv run pytest \
  tests/architecture/test_news_intel_kiss_simplification.py \
  tests/architecture/test_runtime_performance_architecture_hard_cut.py \
  tests/architecture/test_worker_inventory_contract.py \
  tests/architecture/test_worker_runtime_contracts.py \
  -q
```

Expected: PASS.

- [ ] **Step 3: Run static searches for no-compat leftovers**

Run:

```bash
rg -n "news_item_brief_runtime|source_quality_windows|NEWS_ITEM_AGENT_BRIEF_MAX_PUBLISHED_AGE_MS" src/parallax/domains/news_intel src/parallax/app/runtime tests/unit/domains/news_intel tests/architecture
```

Expected:

- no `news_item_brief_runtime`
- no `source_quality_windows`
- `NEWS_ITEM_AGENT_BRIEF_MAX_PUBLISHED_AGE_MS` only in `news_item_agent_policy.py` and policy tests, not fetch

Run:

```bash
rg -n "\"brief_input\"|'brief_input'|\"page\"|'page'|\"source_quality\"|'source_quality'" src/parallax/domains/news_intel/runtime src/parallax/app/runtime/projection_dirty_targets.py
```

Expected: raw projection strings appear only in `news_projection_work.py` and `projection_dirty_targets.py`.

- [ ] **Step 4: Run broader test gate**

Run:

```bash
uv run pytest tests/unit/domains/news_intel tests/architecture -q
```

Expected: PASS.

- [ ] **Step 5: Inspect git diff for accidental scope creep**

Run:

```bash
git diff --stat
git diff -- docs/superpowers/specs/active/2026-06-01-news-intel-kiss-simplification-cn.md
```

Expected: changes are limited to News Intel simplification, tests, docs, and the one Alembic migration. The spec file should not drift unless a deliberate clarification was added.

## Acceptance Mapping

- AC1-AC3: Task 3 removes fetch admission; Task 4 makes processed-state admission the only normal brief creator.
- AC4: Task 3 removes fetch dependency on agent age constants and uses cursor/fetch policy.
- AC5: Task 4 preserves page reprojection for non-brief-eligible items.
- AC6-AC8: Task 5 removes upstream windows and lets source quality own refresh/window expansion.
- AC9-AC10: Task 8 exposes unknown source status and explicit signal layers.
- AC11: Tasks 1, 2, and 6 hide raw dirty-target strings.
- AC12: Task 7 renames the stage adapter.
- AC13: Tasks 1 and 10 keep worker inventory unchanged.
- AC14: No task removes canonical observations or source edges.
- AC15: Task 9 drops unused serving-table watermarks while preserving dirty-target watermarks.

## Execution Notes

- Use subagent-driven development task by task. Each task is independent enough for a fresh subagent, but the reviewing agent must run the targeted tests after every task.
- Do not batch Task 3, Task 4, and Task 5 into one edit. Those are the three risk centers: admission, processing policy, and source-quality scheduling.
- If a test fixture cannot be updated because its helper names differ from the snippets above, keep the same asserted behavior and adapt only the fixture names.
