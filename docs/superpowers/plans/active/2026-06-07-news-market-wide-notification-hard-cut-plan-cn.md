# News Market-Wide Notification Hard Cut Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the legacy crypto-only News admission gate from runtime, storage, API, frontend, docs, and harness so market-wide agent `driver/watch` briefs can become notification candidates under the normal score/source/recency/dedup/cooldown rules.

**Architecture:** News keeps Kappa/CQRS boundaries: material facts stay in `news_items`, deterministic market scope and story identity are produced in item processing, `news_page_rows` remains a single-writer rebuildable read model, and notification rules read only projected market-wide eligibility. The hard cut drops `analysis_admission_*` from product paths instead of aliasing or dual-reading old and new state.

**Tech Stack:** Python 3.13, FastAPI/Pydantic, PostgreSQL/Alembic, pytest, ruff, mypy, React/TypeScript, generated OpenAPI types.

---

**Status:** Draft, ready for execution approval
**Date:** 2026-06-07
**Owning spec:** `docs/superpowers/specs/active/2026-06-07-news-market-wide-notification-hard-cut-cn.md`
**Worktree:** `.worktrees/news-market-wide-notification-hard-cut/`
**Branch:** `codex/news-market-wide-notification-hard-cut`

## Pre-Flight

- [ ] Spec is approved: `docs/superpowers/specs/active/2026-06-07-news-market-wide-notification-hard-cut-cn.md`.
- [ ] Work starts in a dedicated worktree, not the main checkout.
- [ ] Baseline commands are recorded before code edits:

```bash
git worktree add .worktrees/news-market-wide-notification-hard-cut -b codex/news-market-wide-notification-hard-cut main
cd .worktrees/news-market-wide-notification-hard-cut
git status --short
git branch --show-current
uv run pytest tests/architecture/test_news_intel_kiss_simplification.py tests/unit/domains/news_intel/test_news_item_agent_policy.py -q
```

Expected branch: `codex/news-market-wide-notification-hard-cut`. Expected targeted baseline: pass before red tests are added.

## File Map

### Runtime And Domain

- Modify: `src/parallax/domains/news_intel/_constants.py`
  - Add `NEWS_MARKET_SCOPE_VERSION`.
  - Bump `NEWS_PAGE_PROJECTION_VERSION` after row shape changes.
- Create: `src/parallax/domains/news_intel/services/news_market_scope.py`
  - Deterministic market-scope classifier with no reject/not-crypto statuses.
- Delete: `src/parallax/domains/news_intel/services/news_analysis_admission.py`
  - Remove the old crypto-only admission abstraction.
- Modify: `src/parallax/domains/news_intel/services/news_story_identity.py`
  - Replace `admission` input with `market_scope`.
- Modify: `src/parallax/domains/news_intel/runtime/news_item_process_worker.py`
  - Persist `market_scope_json`, not `analysis_admission_*`.
- Modify: `src/parallax/domains/news_intel/runtime/news_item_brief_worker.py`
  - Keep market-wide agent admission recheck; include changed artifact hash behavior.
- Modify: `src/parallax/domains/news_intel/services/news_page_projection.py`
  - Project `market_scope` and market-wide `alert_eligibility`.
- Modify: `src/parallax/domains/news_intel/repositories/news_repository.py`
  - Remove old columns from inserts/selects/details/high-signal query.
  - Add market-scope persistence and query payloads.
- Modify: `src/parallax/domains/notifications/services/notification_rules.py`
  - Stop rechecking `analysis_admission_status`.
  - Stop writing old admission fields into notification payloads.

### Agent Harness

- Modify: `src/parallax/platform/agent_hashing.py`
  - Add prompt text hash to `artifact_hash_for`.
- Modify: `src/parallax/integrations/model_execution/news_item_brief_agent_client.py`
  - Include `text_sha256(read_news_item_brief_prompt())` in item brief artifact hash.
- Modify: `src/parallax/integrations/model_execution/execution_gateway.py`
  - Include `text_sha256(stage.instructions)` in generic request audit artifact hash.
- Modify: `src/parallax/domains/news_intel/services/news_item_brief_validation.py`
  - Treat provider market-impact labels as source-backed.

### Storage

- Create: `src/parallax/platform/db/alembic/versions/20260607_0152_news_market_scope_hard_cut.py`
  - `down_revision = "20260606_0151"` for the clean implementation worktree head.
  - Drop `analysis_admission_*` columns and indexes.
  - Add `market_scope_json` to `news_items` and `news_page_rows`.

### API And Frontend

- Modify: `src/parallax/app/surfaces/api/schemas.py`
  - Add explicit News row/detail Pydantic schemas.
- Modify: `src/parallax/app/surfaces/api/routes_news.py`
  - Keep route behavior; response models become explicit.
- Modify: `web/src/shared/model/newsIntel.ts`
  - Add `NewsMarketScope`, `NewsAgentAdmission`, and explicit fields on `NewsRow`.
- Modify: `web/src/lib/api/client.ts`
  - Normalize `market_scope` and `agent_admission`; drop old fields.
- Modify: `web/src/features/news/model/newsSignalViewModel.ts`
  - Split agent outcome from push readiness.
- Modify: `web/src/features/news/ui/NewsTape.tsx`
  - Do not label agent-ready `watch/driver` rows as agent hold only because external push is blocked.
- Modify: `web/src/features/news/ui/NewsItemEvidencePage.tsx`
  - Display market scope and agent/notification state, not legacy admission.
- Regenerate: `docs/generated/openapi.json`
- Regenerate: `web/src/lib/types/openapi.ts`

### CLI / Repair

- Modify: `src/parallax/app/surfaces/cli/parser.py`
  - Add `ops repair-news-market-signal`.
- Modify: `src/parallax/app/surfaces/cli/commands/ops.py`
  - Dispatch the repair command.
- Create: `src/parallax/domains/news_intel/services/news_market_signal_repair.py`
  - Bounded dry-run/execute repair that recomputes market scope, agent admission, and dirty targets.

### Docs And Specs

- Move to completed with superseded note:
  - `docs/superpowers/specs/active/2026-06-05-news-intel-hard-cut-root-fix-cn.md`
  - `docs/superpowers/plans/active/2026-06-05-news-intel-hard-cut-root-fix-cn.md`
  - `docs/superpowers/plans/active/2026-06-05-news-intel-hard-cut-root-fix-verification-cn.md`
  - `docs/superpowers/specs/active/2026-06-06-news-agent-market-wide-dedup-admission-cn.md`
  - `docs/superpowers/plans/active/2026-06-06-news-agent-market-wide-hard-cut-plan-cn.md`
- Modify: `docs/CONTRACTS.md`
- Modify: `docs/WORKERS.md`
- Modify: `src/parallax/domains/news_intel/ARCHITECTURE.md`
- Modify: `docs/AGENT_EXECUTION.md` only for prompt-hash/packet wording that changed.

## Task 1: Planning Lane Hygiene And Red Architecture Gates

**Files:**
- Modify: `tests/architecture/test_news_intel_kiss_simplification.py`
- Create: `tests/architecture/test_news_active_spec_hygiene.py`

- [ ] **Step 1: Add failing runtime-path guard**

Append this test to `tests/architecture/test_news_intel_kiss_simplification.py`:

```python
def test_news_runtime_product_paths_do_not_use_legacy_analysis_admission_gate() -> None:
    paths = [
        "src/parallax/domains/news_intel/services/news_page_projection.py",
        "src/parallax/domains/news_intel/services/news_story_identity.py",
        "src/parallax/domains/news_intel/runtime/news_item_process_worker.py",
        "src/parallax/domains/news_intel/runtime/news_item_brief_worker.py",
        "src/parallax/domains/news_intel/repositories/news_repository.py",
        "src/parallax/domains/notifications/services/notification_rules.py",
        "src/parallax/app/surfaces/api/schemas.py",
        "src/parallax/app/surfaces/api/routes_news.py",
        "web/src/shared/model/newsIntel.ts",
        "web/src/lib/api/client.ts",
        "web/src/features/news/model/newsSignalViewModel.ts",
        "web/src/features/news/ui/NewsTape.tsx",
        "web/src/features/news/ui/NewsItemEvidencePage.tsx",
    ]
    forbidden = {
        "analysis_admission",
        "non_crypto_subject",
        "no_crypto_native_evidence",
        "provider_evidence_only",
        "analysis_not_admitted",
        "page_material_not_admitted",
    }
    offenders = [
        f"{path} contains {token}"
        for path in paths
        for token in forbidden
        if token in _read(path)
    ]
    assert offenders == []
```

- [ ] **Step 2: Add failing active spec hygiene guard**

Create `tests/architecture/test_news_active_spec_hygiene.py`:

```python
from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
ACTIVE_DIRS = (
    ROOT / "docs" / "superpowers" / "specs" / "active",
    ROOT / "docs" / "superpowers" / "plans" / "active",
)
ALLOWLIST = {
    "2026-06-07-news-market-wide-notification-hard-cut-cn.md",
    "2026-06-07-news-market-wide-notification-hard-cut-plan-cn.md",
}
FORBIDDEN = (
    "analysis_admission_status == admitted",
    "analysis_admission_status = 'admitted'",
    "analysis_not_admitted",
    "non_crypto_subject",
    "no_crypto_native_evidence",
    "provider_evidence_only",
    "not delete `analysis_admission_*`",
    "不删除 `analysis_admission_*`",
    "不能 brief/notify",
)


def test_active_news_specs_do_not_define_legacy_crypto_gate() -> None:
    offenders: list[str] = []
    for directory in ACTIVE_DIRS:
        for path in sorted(directory.glob("*news*.md")):
            if path.name in ALLOWLIST:
                continue
            text = path.read_text(encoding="utf-8")
            for token in FORBIDDEN:
                if token in text:
                    offenders.append(f"{path.relative_to(ROOT)} contains {token}")
    assert offenders == []
```

- [ ] **Step 3: Run the red architecture tests**

```bash
uv run pytest tests/architecture/test_news_intel_kiss_simplification.py::test_news_runtime_product_paths_do_not_use_legacy_analysis_admission_gate tests/architecture/test_news_active_spec_hygiene.py -q
```

Expected: fail with offenders in projection, repository, notification rules, API/client paths, and old active docs.

- [ ] **Step 4: Move superseded active docs**

```bash
git mv docs/superpowers/specs/active/2026-06-05-news-intel-hard-cut-root-fix-cn.md docs/superpowers/specs/completed/2026-06-05-news-intel-hard-cut-root-fix-cn.md
git mv docs/superpowers/plans/active/2026-06-05-news-intel-hard-cut-root-fix-cn.md docs/superpowers/plans/completed/2026-06-05-news-intel-hard-cut-root-fix-cn.md
git mv docs/superpowers/plans/active/2026-06-05-news-intel-hard-cut-root-fix-verification-cn.md docs/superpowers/plans/completed/2026-06-05-news-intel-hard-cut-root-fix-verification-cn.md
git mv docs/superpowers/specs/active/2026-06-06-news-agent-market-wide-dedup-admission-cn.md docs/superpowers/specs/completed/2026-06-06-news-agent-market-wide-dedup-admission-cn.md
git mv docs/superpowers/plans/active/2026-06-06-news-agent-market-wide-hard-cut-plan-cn.md docs/superpowers/plans/completed/2026-06-06-news-agent-market-wide-hard-cut-plan-cn.md
```

Prepend this note to each moved file:

```markdown
> Superseded on 2026-06-07 by `docs/superpowers/specs/active/2026-06-07-news-market-wide-notification-hard-cut-cn.md` and `docs/superpowers/plans/active/2026-06-07-news-market-wide-notification-hard-cut-plan-cn.md`. Do not use this file for current News agent, projection, notification, API, or storage behavior.

```

- [ ] **Step 5: Commit Task 1**

```bash
uv run pytest tests/architecture/test_news_active_spec_hygiene.py -q
git add tests/architecture/test_news_intel_kiss_simplification.py tests/architecture/test_news_active_spec_hygiene.py docs/superpowers/specs docs/superpowers/plans
git commit -m "test: guard news market-wide hard cut"
```

Expected: active spec hygiene passes after superseded files move; runtime guard still fails until later tasks.

## Task 2: Storage Hard Cut And Market Scope Fact Shape

**Files:**
- Create: `src/parallax/platform/db/alembic/versions/20260607_0152_news_market_scope_hard_cut.py`
- Modify: `tests/unit/test_postgres_schema.py`
- Modify: `src/parallax/domains/news_intel/_constants.py`

- [ ] **Step 1: Add the failing schema test**

In `tests/unit/test_postgres_schema.py`, add a constant near the existing News migrations:

```python
NEWS_MARKET_SCOPE_HARD_CUT_MIGRATION = Path(
    "src/parallax/platform/db/alembic/versions/20260607_0152_news_market_scope_hard_cut.py"
)
```

Add the migration to the News migration presence test list, then add:

```python
def test_news_market_scope_hard_cut_drops_legacy_analysis_admission_columns() -> None:
    text = NEWS_MARKET_SCOPE_HARD_CUT_MIGRATION.read_text(encoding="utf-8")
    assert 'revision = "20260607_0152"' in text
    assert 'down_revision = "20260606_0151"' in text
    for table in ("news_items", "news_page_rows"):
        assert f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS market_scope_json JSONB NOT NULL DEFAULT '{{}}'::jsonb" in text
    for column_name in (
        "analysis_admission_status",
        "analysis_admission_reason",
        "analysis_admission_json",
        "analysis_admission_version",
        "analysis_admission_computed_at_ms",
    ):
        assert f"DROP COLUMN IF EXISTS {column_name}" in text
    assert "DROP INDEX CONCURRENTLY IF EXISTS ix_news_items_analysis_admission_published" in text
    assert "DROP INDEX CONCURRENTLY IF EXISTS ix_news_page_rows_analysis_admission" in text
```

- [ ] **Step 2: Run the schema test and confirm it fails**

```bash
uv run pytest tests/unit/test_postgres_schema.py::test_news_market_scope_hard_cut_drops_legacy_analysis_admission_columns -q
```

Expected: fail because the migration file does not exist.

- [ ] **Step 3: Add constants**

Modify `src/parallax/domains/news_intel/_constants.py`:

```python
NEWS_MARKET_SCOPE_VERSION = "news_market_scope_v1"
NEWS_PAGE_PROJECTION_VERSION = "news_page_rows_v5"
```

Keep `NEWS_ITEM_AGENT_ADMISSION_VERSION` unchanged unless its payload shape changes.

- [ ] **Step 4: Add the migration**

Create `src/parallax/platform/db/alembic/versions/20260607_0152_news_market_scope_hard_cut.py`:

```python
"""Hard-cut News market scope and drop legacy analysis admission."""

from __future__ import annotations

from alembic import op

revision = "20260607_0152"
down_revision = "20260606_0151"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute("SET LOCAL statement_timeout = '30min'")
    op.execute(
        """
        ALTER TABLE news_items
          ADD COLUMN IF NOT EXISTS market_scope_json JSONB NOT NULL DEFAULT '{}'::jsonb
        """
    )
    op.execute(
        """
        ALTER TABLE news_page_rows
          ADD COLUMN IF NOT EXISTS market_scope_json JSONB NOT NULL DEFAULT '{}'::jsonb
        """
    )
    with op.get_context().autocommit_block():
        op.execute("SET lock_timeout = '5s'")
        op.execute("SET statement_timeout = '30min'")
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS ix_news_items_analysis_admission_published")
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS ix_news_page_rows_analysis_admission")
        op.execute("RESET lock_timeout")
        op.execute("RESET statement_timeout")
    for column_name in (
        "analysis_admission_status",
        "analysis_admission_reason",
        "analysis_admission_json",
        "analysis_admission_version",
        "analysis_admission_computed_at_ms",
    ):
        op.execute(f"ALTER TABLE news_items DROP COLUMN IF EXISTS {column_name}")
    for column_name in (
        "analysis_admission_status",
        "analysis_admission_reason",
        "analysis_admission_json",
        "analysis_admission_version",
        "analysis_admission_computed_at_ms",
    ):
        op.execute(f"ALTER TABLE news_page_rows DROP COLUMN IF EXISTS {column_name}")
    op.execute("ANALYZE news_items")
    op.execute("ANALYZE news_page_rows")


def downgrade() -> None:
    raise RuntimeError(
        "20260607_0152 is a News market-scope hard cut. Downgrade would recreate "
        "legacy crypto-only product gates and is intentionally unsupported."
    )
```

- [ ] **Step 5: Verify Alembic graph and schema test**

```bash
uv run pytest tests/unit/test_postgres_schema.py::test_alembic_revision_graph_has_single_head tests/unit/test_postgres_schema.py::test_news_market_scope_hard_cut_drops_legacy_analysis_admission_columns -q
```

Expected: pass with a single Alembic head at `20260607_0152`.

- [ ] **Step 6: Commit Task 2**

```bash
git add src/parallax/domains/news_intel/_constants.py src/parallax/platform/db/alembic/versions/20260607_0152_news_market_scope_hard_cut.py tests/unit/test_postgres_schema.py
git commit -m "db: hard cut news market scope storage"
```

## Task 3: Market Scope Classifier And Item Processing

**Files:**
- Create: `src/parallax/domains/news_intel/services/news_market_scope.py`
- Delete: `src/parallax/domains/news_intel/services/news_analysis_admission.py`
- Modify: `src/parallax/domains/news_intel/runtime/news_item_process_worker.py`
- Modify: `src/parallax/domains/news_intel/services/news_story_identity.py`
- Modify: `src/parallax/domains/news_intel/repositories/news_repository.py`
- Delete or rewrite: `tests/unit/domains/news_intel/test_news_analysis_admission.py`
- Create: `tests/unit/domains/news_intel/test_news_market_scope.py`
- Modify: `tests/unit/domains/news_intel/test_news_workers.py`

- [ ] **Step 1: Write market-scope tests**

Create `tests/unit/domains/news_intel/test_news_market_scope.py`:

```python
from __future__ import annotations

from parallax.domains.news_intel.services.news_market_scope import classify_news_market_scope


def test_private_company_equity_scope_is_metadata_not_rejection() -> None:
    scope = classify_news_market_scope(
        item={
            "title": "SpaceX shares trade at higher valuation in tender offer",
            "summary": "Private company valuation update affects aerospace and growth equity sentiment.",
            "content_class": "low_signal",
            "provider_signal_json": {"source": "provider", "score": 95},
            "provider_token_impacts_json": [{"symbol": "SPCX", "market_type": "private_company", "score": 95}],
        },
        token_mentions=[],
        fact_candidates=[],
    )
    assert scope.scope == ["private_company", "us_equity"]
    assert scope.primary == "private_company"
    assert scope.status == "classified"
    assert "non_crypto_subject" not in scope.reason


def test_macro_rates_scope_without_crypto_is_classified() -> None:
    scope = classify_news_market_scope(
        item={
            "title": "Fed officials signal rates may stay restrictive",
            "summary": "Rates and dollar sensitivity remain the market transmission channel.",
            "content_class": "macro_rates",
            "provider_signal_json": {"source": "provider", "score": 91},
        },
        token_mentions=[],
        fact_candidates=[],
    )
    assert "macro_rates" in scope.scope
    assert scope.status == "classified"


def test_crypto_scope_remains_supported() -> None:
    scope = classify_news_market_scope(
        item={
            "title": "Coinbase lists new BTC futures product",
            "summary": "Crypto market structure and exchange access are affected.",
            "content_class": "exchange_listing",
            "provider_signal_json": {"source": "provider", "score": 90},
            "provider_token_impacts_json": [{"symbol": "BTC", "market_type": "crypto", "score": 90}],
        },
        token_mentions=[{"symbol": "BTC", "resolution_status": "known_symbol"}],
        fact_candidates=[],
    )
    assert scope.primary == "crypto"
    assert "crypto" in scope.scope
```

- [ ] **Step 2: Run the market-scope tests and confirm they fail**

```bash
uv run pytest tests/unit/domains/news_intel/test_news_market_scope.py -q
```

Expected: fail because `news_market_scope.py` does not exist.

- [ ] **Step 3: Implement deterministic market scope**

Create `src/parallax/domains/news_intel/services/news_market_scope.py` with this interface:

```python
from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from parallax.domains.news_intel._constants import NEWS_MARKET_SCOPE_VERSION


_SCOPE_ORDER = (
    "crypto",
    "us_equity",
    "private_company",
    "macro_rates",
    "energy_geopolitics",
    "commodities",
    "fx",
    "ai_semiconductors",
    "broad_risk",
    "unknown",
)
_TEXT_RULES = (
    ("crypto", re.compile(r"\b(?:bitcoin|btc|ethereum|eth|crypto|stablecoin|tokeni[sz]ed|coinbase|binance|bybit)\b", re.I)),
    ("private_company", re.compile(r"\b(?:private company|tender offer|spacex|openai|valuation)\b", re.I)),
    ("us_equity", re.compile(r"\b(?:shares?|stocks?|equity|nasdaq|nyse|earnings|guidance)\b", re.I)),
    ("macro_rates", re.compile(r"\b(?:fed|rates?|treasury|yields?|inflation|cpi|pce|dollar)\b", re.I)),
    ("energy_geopolitics", re.compile(r"\b(?:oil|gas|energy|sanctions|russia|ukraine|iran|opec)\b", re.I)),
    ("commodities", re.compile(r"\b(?:gold|copper|commodity|commodities|wheat|uranium)\b", re.I)),
    ("fx", re.compile(r"\b(?:fx|currency|yen|euro|dollar index|dxy)\b", re.I)),
    ("ai_semiconductors", re.compile(r"\b(?:ai|semiconductor|semis|nvidia|amd|memory chip|dram|hbm)\b", re.I)),
    ("broad_risk", re.compile(r"\b(?:risk sentiment|market risk|liquidity|volatility|credit spread)\b", re.I)),
)
_PROVIDER_MARKET_MAP = {
    "crypto": "crypto",
    "cex": "crypto",
    "dex": "crypto",
    "perp": "crypto",
    "spot": "crypto",
    "equity": "us_equity",
    "stock": "us_equity",
    "us_equity": "us_equity",
    "private_company": "private_company",
    "macro": "macro_rates",
    "rates": "macro_rates",
    "commodity": "commodities",
    "commodities": "commodities",
    "fx": "fx",
}


@dataclass(frozen=True, slots=True)
class NewsMarketScope:
    scope: list[str]
    primary: str
    status: str
    reason: str
    basis: dict[str, Any]
    version: str = NEWS_MARKET_SCOPE_VERSION

    def to_payload(self) -> dict[str, Any]:
        return {
            "scope": list(self.scope),
            "primary": self.primary,
            "status": self.status,
            "reason": self.reason,
            "basis": dict(self.basis),
            "version": self.version,
        }


def classify_news_market_scope(
    *,
    item: Mapping[str, Any],
    token_mentions: Sequence[Mapping[str, Any]],
    fact_candidates: Sequence[Mapping[str, Any]],
) -> NewsMarketScope:
    del token_mentions, fact_candidates
    evidence: dict[str, list[str]] = {"provider": [], "content_class": [], "text": []}
    scopes: set[str] = set()
    for impact in _json_list(item.get("provider_token_impacts_json")):
        market_type = str(_mapping(impact).get("market_type") or "").strip().lower()
        mapped = _PROVIDER_MARKET_MAP.get(market_type)
        if mapped:
            scopes.add(mapped)
            evidence["provider"].append(f"market_type:{market_type}")
    content_class = str(item.get("content_class") or "").strip()
    content_scope = _scope_from_content_class(content_class)
    if content_scope:
        scopes.add(content_scope)
        evidence["content_class"].append(content_class)
    text = _item_text(item)
    for scope, pattern in _TEXT_RULES:
        if pattern.search(text):
            scopes.add(scope)
            evidence["text"].append(scope)
    ordered = [scope for scope in _SCOPE_ORDER if scope in scopes]
    if not ordered:
        ordered = ["unknown"]
    return NewsMarketScope(
        scope=ordered,
        primary=ordered[0],
        status="classified",
        reason="market_scope_classified",
        basis=evidence,
    )


def _scope_from_content_class(value: str) -> str:
    normalized = value.strip().lower()
    if normalized in {"crypto_market", "exchange_listing", "protocol_development", "market_structure"}:
        return "crypto"
    if normalized in {"macro_policy", "rates_fed", "macro_rates", "consumer_macro"}:
        return "macro_rates"
    if normalized == "energy_geopolitics":
        return "energy_geopolitics"
    if normalized in {"etf_fund_flow", "equity_market"}:
        return "us_equity"
    return ""


def _item_text(item: Mapping[str, Any]) -> str:
    return " ".join(
        str(part)
        for part in (
            item.get("title") or "",
            item.get("summary") or "",
            item.get("body_text") or "",
            item.get("source_domain") or "",
            item.get("source_name") or "",
        )
    )


def _json_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return list(value)
    if isinstance(value, str) and value.strip():
        parsed = json.loads(value)
        return list(parsed) if isinstance(parsed, list) else []
    return []


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


__all__ = ["NewsMarketScope", "classify_news_market_scope"]
```

- [ ] **Step 4: Update item processing and story identity**

Change `build_news_story_identity` signature from:

```python
def build_news_story_identity(
    *,
    item: Mapping[str, Any],
    token_mentions: Sequence[Mapping[str, Any]],
    fact_candidates: Sequence[Mapping[str, Any]],
    admission: Mapping[str, Any],
) -> NewsStoryIdentity:
```

to:

```python
def build_news_story_identity(
    *,
    item: Mapping[str, Any],
    token_mentions: Sequence[Mapping[str, Any]],
    fact_candidates: Sequence[Mapping[str, Any]],
    market_scope: Mapping[str, Any],
) -> NewsStoryIdentity:
```

Replace every `"admission_status": _field(admission, "status", "")` basis field with:

```python
"market_scope": _json_list(market_scope.get("scope")),
"market_scope_primary": _field(market_scope, "primary", ""),
```

Add `_json_list` to `news_story_identity.py` if it is not already present:

```python
def _json_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return list(value)
    return []
```

In `NewsItemProcessWorker`, replace the analysis admission block with:

```python
market_scope = classify_news_market_scope(
    item=processed_item,
    token_mentions=mention_payloads,
    fact_candidates=candidate_payloads,
)
market_scope_payload = market_scope.to_payload()
story_identity = build_news_story_identity(
    item=processed_item,
    token_mentions=mention_payloads,
    fact_candidates=candidate_payloads,
    market_scope=market_scope_payload,
)
processed_item.update(
    {
        "market_scope_json": market_scope_payload,
        "story_key": story_identity_payload["story_key"],
        "story_identity_json": story_identity_payload,
        "story_identity_version": story_identity_payload["version"],
    }
)
```

Update repository persistence method names so item processing calls a method that writes market scope and story identity:

```python
repos.news.update_item_market_scope_and_story_identity(
    news_item_id=news_item_id,
    market_scope=market_scope_payload,
    story_identity=story_identity,
    now_ms=now,
    commit=False,
)
```

- [ ] **Step 5: Remove old service and tests**

```bash
git rm src/parallax/domains/news_intel/services/news_analysis_admission.py
git rm tests/unit/domains/news_intel/test_news_analysis_admission.py
```

- [ ] **Step 6: Run focused tests**

```bash
uv run pytest tests/unit/domains/news_intel/test_news_market_scope.py tests/unit/domains/news_intel/test_news_workers.py::test_news_item_process_rejects_unsupported_analysis_admission_shape_before_persistence -q
```

Expected: market-scope tests pass. The old worker test should be deleted or rewritten to assert unsupported market-scope shapes are rejected before persistence.

- [ ] **Step 7: Commit Task 3**

```bash
git add src/parallax/domains/news_intel tests/unit/domains/news_intel
git commit -m "feat: replace news analysis admission with market scope"
```

## Task 4: Projection, Repository, And Notification Eligibility

**Files:**
- Modify: `src/parallax/domains/news_intel/services/news_page_projection.py`
- Modify: `src/parallax/domains/news_intel/repositories/news_repository.py`
- Modify: `src/parallax/domains/notifications/services/notification_rules.py`
- Modify: `tests/unit/domains/news_intel/test_news_page_projection.py`
- Modify: `tests/unit/test_notification_rules.py`
- Modify: `tests/integration/domains/news_intel/test_news_repository.py`

- [ ] **Step 1: Rewrite projection tests around market-wide eligibility**

Replace `test_non_admitted_provider_score_does_not_set_in_app_eligible` with:

```python
def test_ready_market_watch_brief_sets_in_app_eligible_without_crypto_admission() -> None:
    row = build_news_page_row(
        item={
            "news_item_id": "news-spacex",
            "title": "SpaceX shares trade at higher valuation",
            "summary": "",
            "source_domain": "example.test",
            "canonical_url": "https://example.test/spacex",
            "published_at_ms": 1000,
            "market_scope_json": {
                "scope": ["private_company", "us_equity"],
                "primary": "private_company",
                "status": "classified",
                "reason": "market_scope_classified",
            },
            "provider_signal_json": {
                "source": "provider",
                "provider": "opennews",
                "status": "ready",
                "direction": "bullish",
                "score": 95,
                "grade": "A",
            },
            "agent_admission_status": "eligible",
            "agent_admission_reason": "provider_score_high",
            "agent_admission_json": {
                "status": "eligible",
                "reason": "provider_score_high",
                "representative_news_item_id": "news-spacex",
            },
        },
        token_mentions=[],
        fact_candidates=[],
        agent_brief={
            "status": "ready",
            "direction": "bullish",
            "decision_class": "watch",
            "brief_json": {"summary_zh": "SpaceX valuation update may affect private growth equity sentiment."},
            "computed_at_ms": 1500,
        },
        computed_at_ms=2000,
    )

    eligibility = row["signal"]["alert_eligibility"]
    assert row["market_scope"]["primary"] == "private_company"
    assert eligibility["in_app_eligible"] is True
    assert eligibility["external_push_ready"] is True
    assert eligibility["external_push_block_reason"] is None
```

- [ ] **Step 2: Rewrite notification skip test**

Replace `test_news_high_signal_skips_page_only_provider_score` with:

```python
def test_news_high_signal_allows_market_wide_ready_watch_candidate():
    news = FakeNews(
        [
            {
                "news_item_id": "news-provider-high",
                "latest_at_ms": NOW_MS - 5_000,
                "headline": "Provider high signal should alert",
                "source_domain": "example.test",
                "canonical_url": "https://example.test/high",
                "duplicate_count": 1,
                "market_scope": {"scope": ["us_equity"], "primary": "us_equity"},
                "content_class": "low_signal",
                "content_tags": ["market_context"],
                "signal": {
                    "direction": "bullish",
                    "alert_eligibility": {
                        "in_app_eligible": True,
                        "external_push_ready": True,
                        "provider_score": 90,
                        "decision_class": "watch",
                    },
                },
                "token_impacts": [{"symbol": "SPCX", "score": 90}],
                "agent_brief": {
                    "status": "ready",
                    "direction": "bullish",
                    "decision_class": "watch",
                    "summary_zh": "高分市场新闻已由 agent 归纳。",
                    "brief_json": {"summary_zh": "高分市场新闻已由 agent 归纳。"},
                },
            }
        ]
    )
    notifications = NotificationsConfig(
        rules={
            "news_high_signal": {
                "enabled": True,
                "channels": ["in_app", "pushdeer"],
                "combined_score_min": 85,
                "external_score_min": 85,
                "cooldown_seconds": 1800,
            }
        }
    )

    candidates = [
        item
        for item in engine(news=news, notifications=notifications).evaluate(now_ms=NOW_MS)
        if item.rule_id == "news_high_signal"
    ]

    assert len(candidates) == 1
    assert candidates[0].channels == ("in_app", "pushdeer")
    assert candidates[0].payload["decision_class"] == "watch"
    assert candidates[0].payload["market_scope"] == {"scope": ["us_equity"], "primary": "us_equity"}
```

- [ ] **Step 3: Run rewritten tests and confirm they fail**

```bash
uv run pytest tests/unit/domains/news_intel/test_news_page_projection.py::test_ready_market_watch_brief_sets_in_app_eligible_without_crypto_admission tests/unit/test_notification_rules.py::test_news_high_signal_allows_market_wide_ready_watch_candidate -q
```

Expected: fail until projection/repository/notification code is changed.

- [ ] **Step 4: Update projection logic**

In `build_news_page_row`:

- Replace local `analysis_admission_*` variables with:

```python
market_scope = _market_scope_payload(item)
```

- Pass `market_scope` and `agent_admission` into `_page_signal`.
- Add row field:

```python
"market_scope": market_scope,
```

Replace `_alert_eligible` with:

```python
def _alert_eligible(
    *,
    agent_signal: Mapping[str, Any],
    provider_score: int | None,
    agent_admission_status: str,
) -> bool:
    if agent_admission_status not in {"eligible", "eligible_refresh"}:
        return False
    if provider_score is None or provider_score < 85:
        return False
    return str(agent_signal.get("status") or "") == "ready" and str(agent_signal.get("decision_class") or "") in {
        "driver",
        "watch",
    }
```

Replace `_external_push_readiness` with:

```python
def _external_push_readiness(agent_signal: Mapping[str, Any]) -> tuple[bool, str | None]:
    if str(agent_signal.get("status") or "") != "ready":
        return False, "agent_brief_not_ready"
    if str(agent_signal.get("decision_class") or "") not in {"driver", "watch"}:
        return False, "decision_not_notifiable"
    if not _agent_publishable_summary(agent_signal):
        return False, "agent_brief_missing_summary"
    return True, None
```

- [ ] **Step 5: Update repository query**

In `list_news_high_signal_notification_candidates`, remove:

```sql
AND analysis_admission_status = 'admitted'
```

Remove `analysis_admission_*` from SELECT and include:

```sql
market_scope_json AS market_scope,
```

Keep:

```sql
AND COALESCE((signal_json -> 'alert_eligibility' ->> 'in_app_eligible')::boolean, false) = true
AND COALESCE(NULLIF(signal_json -> 'alert_eligibility' ->> 'provider_score', '')::int, -1) >= %s
```

- [ ] **Step 6: Update notification rules**

Remove the loop guard:

```python
if str(row.get("analysis_admission_status") or "") != "admitted":
    continue
```

Remove `analysis_admission_*` from notification payload and add:

```python
"market_scope": _dict(row.get("market_scope")),
"agent_admission_status": row.get("agent_admission_status"),
"agent_admission_reason": row.get("agent_admission_reason"),
"agent_admission": _dict(row.get("agent_admission")),
```

- [ ] **Step 7: Run projection, notification, repository tests**

```bash
uv run pytest tests/unit/domains/news_intel/test_news_page_projection.py tests/unit/test_notification_rules.py tests/integration/domains/news_intel/test_news_repository.py -q
```

Expected: pass after fixtures and assertions use market scope.

- [ ] **Step 8: Commit Task 4**

```bash
git add src/parallax/domains/news_intel/services/news_page_projection.py src/parallax/domains/news_intel/repositories/news_repository.py src/parallax/domains/notifications/services/notification_rules.py tests/unit/domains/news_intel/test_news_page_projection.py tests/unit/test_notification_rules.py tests/integration/domains/news_intel/test_news_repository.py
git commit -m "fix: route news notifications through market-wide eligibility"
```

## Task 5: API Contract And Frontend State Split

**Files:**
- Modify: `src/parallax/app/surfaces/api/schemas.py`
- Modify: `src/parallax/domains/news_intel/repositories/news_repository.py`
- Modify: `tests/unit/test_api_news_contract.py`
- Modify: `web/src/shared/model/newsIntel.ts`
- Modify: `web/src/lib/api/client.ts`
- Modify: `web/src/features/news/model/newsSignalViewModel.ts`
- Modify: `web/src/features/news/ui/NewsTape.tsx`
- Modify: `web/src/features/news/ui/NewsItemEvidencePage.tsx`
- Regenerate: `docs/generated/openapi.json`
- Regenerate: `web/src/lib/types/openapi.ts`

- [ ] **Step 1: Rewrite API contract tests**

In `tests/unit/test_api_news_contract.py`, replace old detail assertions with:

```python
assert "analysis_admission_status" not in data
assert "analysis_admission_reason" not in data
assert "analysis_admission" not in data
assert data["market_scope"]["primary"] == "crypto"
assert data["agent_admission_status"] == "eligible"
assert data["agent_admission"]["reason"] == "provider_score_high"
```

Add a generated schema assertion:

```python
def test_news_openapi_schema_exposes_market_scope_not_analysis_admission() -> None:
    schema = client.get("/openapi.json").json()
    text = json.dumps(schema, sort_keys=True)
    assert "market_scope" in text
    assert "agent_admission" in text
    assert "analysis_admission" not in text
```

- [ ] **Step 2: Run API tests and confirm they fail**

```bash
uv run pytest tests/unit/test_api_news_contract.py -q
```

Expected: fail while repository detail and broad schemas still expose old fields.

- [ ] **Step 3: Add explicit API schemas**

In `src/parallax/app/surfaces/api/schemas.py`, replace generic News schema with explicit shapes:

```python
class NewsAlertEligibility(ApiSchema):
    in_app_eligible: bool | None = None
    external_push_ready: bool | None = None
    external_push_block_reason: str | None = None
    external_push_basis: str | None = None
    agent_status: str | None = None
    decision_class: str | None = None
    provider_status: str | None = None
    provider_score: int | None = None
    agent_admission_status: str | None = None
    agent_admission_reason: str | None = None
    market_scope: JsonObject = Field(default_factory=dict)


class NewsSignalEnvelope(ApiSchema):
    display_signal: JsonObject = Field(default_factory=dict)
    provider_signal: JsonObject | None = None
    agent_signal: JsonObject = Field(default_factory=dict)
    alert_eligibility: NewsAlertEligibility = Field(default_factory=NewsAlertEligibility)


class NewsRow(ApiSchema):
    row_id: str
    news_item_id: str
    representative_news_item_id: str | None = None
    story_key: str | None = None
    story: JsonObject = Field(default_factory=dict)
    latest_at_ms: int | None = None
    lifecycle_status: str
    headline: str
    summary: str | None = None
    source_domain: str | None = None
    canonical_url: str | None = None
    content_class: str | None = None
    content_tags: list[str] = Field(default_factory=list)
    content_classification: JsonObject = Field(default_factory=dict)
    market_scope: JsonObject = Field(default_factory=dict)
    signal: NewsSignalEnvelope
    token_impacts: list[JsonObject] = Field(default_factory=list)
    token_lanes: list[JsonObject] = Field(default_factory=list)
    fact_lanes: list[JsonObject] = Field(default_factory=list)
    source: JsonObject = Field(default_factory=dict)
    agent_brief: JsonObject = Field(default_factory=dict)
    agent_status: str | None = None
    agent_brief_computed_at_ms: int | None = None
    agent_admission_status: str | None = None
    agent_admission_reason: str | None = None
    agent_admission: JsonObject = Field(default_factory=dict)
    agent_representative_news_item_id: str | None = None
    duplicate_count: int | None = None
    source_ids: list[str] = Field(default_factory=list)
    source_domains: list[str] = Field(default_factory=list)
    provider_article_keys: list[str] = Field(default_factory=list)
    computed_at_ms: int | None = None
    projection_version: str | None = None


class NewsData(ApiSchema):
    items: list[NewsRow] = Field(default_factory=list)
    next_cursor: str | None = None


class NewsObjectData(NewsRow):
    title: str | None = None
    body_text: str | None = None
    language: str | None = None
    published_at_ms: int | None = None
    fetched_at_ms: int | None = None
    content: str | None = None
    entities: list[JsonObject] = Field(default_factory=list)
    token_mentions: list[JsonObject] = Field(default_factory=list)
    fact_candidates: list[JsonObject] = Field(default_factory=list)
    agent_run: JsonObject | None = None
    provider_item: JsonObject | None = None
    fetch_run: JsonObject | None = None
    observation_edges: list[JsonObject] = Field(default_factory=list)
    provider_observations: list[JsonObject] = Field(default_factory=list)
```

- [ ] **Step 4: Update frontend models**

In `web/src/shared/model/newsIntel.ts`, add:

```typescript
export type NewsMarketScope = {
  scope?: string[];
  primary?: string | null;
  status?: string | null;
  reason?: string | null;
  basis?: Record<string, unknown>;
  version?: string | null;
};

export type NewsAgentAdmission = {
  status?: string | null;
  reason?: string | null;
  representative_news_item_id?: string | null;
  basis?: Record<string, unknown>;
  version?: string | null;
};
```

Add these fields to `NewsAlertEligibility` and `NewsRow`:

```typescript
agent_admission_status?: string | null;
agent_admission_reason?: string | null;
market_scope?: NewsMarketScope | null;
```

```typescript
market_scope?: NewsMarketScope | null;
agent_admission_status?: string | null;
agent_admission_reason?: string | null;
agent_admission?: NewsAgentAdmission | null;
agent_representative_news_item_id?: string | null;
```

- [ ] **Step 5: Split frontend badge semantics**

In `newsSignalViewModel.ts`, make the agent badge read agent state first:

```typescript
const readyDecision = row.agent_brief?.status === "ready" && ["driver", "watch"].includes(String(row.agent_brief?.decision_class ?? ""));
if (readyDecision) return "AGENT READY";
if (row.agent_brief?.status === "ready") return "AGENT CONTEXT";
if (row.agent_status === "pending" || row.agent_brief_status === "pending") return "AGENT PENDING";
return "AGENT HOLD";
```

Keep push readiness as a separate display value:

```typescript
const pushReady = row.signal.alert_eligibility?.external_push_ready === true;
```

- [ ] **Step 6: Regenerate API contract**

```bash
make regen-contract
uv run pytest tests/unit/test_api_news_contract.py tests/contract -q
cd web && npm run typecheck && npm run lint && cd ..
```

Expected: generated OpenAPI includes News shapes and no public `analysis_admission` properties.

- [ ] **Step 7: Commit Task 5**

```bash
git add src/parallax/app/surfaces/api/schemas.py src/parallax/domains/news_intel/repositories/news_repository.py tests/unit/test_api_news_contract.py web/src/shared/model/newsIntel.ts web/src/lib/api/client.ts web/src/features/news/model/newsSignalViewModel.ts web/src/features/news/ui/NewsTape.tsx web/src/features/news/ui/NewsItemEvidencePage.tsx docs/generated/openapi.json web/src/lib/types/openapi.ts
git commit -m "feat: expose news market scope contract"
```

## Task 6: Agent Harness Drift Fixes

**Files:**
- Modify: `src/parallax/platform/agent_hashing.py`
- Modify: `src/parallax/integrations/model_execution/news_item_brief_agent_client.py`
- Modify: `src/parallax/integrations/model_execution/execution_gateway.py`
- Modify: `src/parallax/domains/news_intel/services/news_item_brief_stage.py`
- Modify: `src/parallax/domains/news_intel/services/news_item_brief_validation.py`
- Modify: `tests/unit/domains/news_intel/test_news_item_brief_validation.py`
- Create: `tests/unit/integrations/model_execution/test_news_item_brief_artifact_hash.py`

- [ ] **Step 1: Add prompt hash tests**

Create `tests/unit/integrations/model_execution/test_news_item_brief_artifact_hash.py`:

```python
from __future__ import annotations

from parallax.platform.agent_hashing import artifact_hash_for, json_sha256, text_sha256


def test_artifact_hash_changes_when_prompt_text_hash_changes() -> None:
    base = {
        "model": "model-a",
        "prompt_version": "news-item-brief-v4",
        "schema_version": "news_item_brief_market_v2",
        "runtime_version": "runtime-v1",
        "output_schema_hash": json_sha256({"type": "object"}),
    }
    first = artifact_hash_for(**base, prompt_text_hash=text_sha256("prompt one"))
    second = artifact_hash_for(**base, prompt_text_hash=text_sha256("prompt two"))
    assert first != second
```

- [ ] **Step 2: Add provider-impact validator test**

Append to `tests/unit/domains/news_intel/test_news_item_brief_validation.py`:

```python
def _packet_with_provider_impact():
    return build_news_item_brief_input_packet(
        item={
            "news_item_id": "item-spacex",
            "title": "Private company valuation update",
            "summary": "A private company tender offer changes market-implied valuation.",
            "body_text": "Provider market impact labels this as SPCX private-company exposure.",
            "published_at_ms": 1_779_000_000_000,
            "content_hash": "sha256:spacex",
            "provider_signal_json": {"source": "provider", "status": "ready", "score": 91},
            "provider_token_impacts_json": [
                {
                    "label": "SPCX",
                    "symbol": "SPCX",
                    "market_type": "private_company",
                    "target_type": "PrivateCompany",
                    "target_id": "spacex",
                    "score": 91,
                    "signal": "long",
                }
            ],
        },
        token_mentions=[],
        fact_candidates=[],
        agent_config=NewsItemBriefAgentConfig(
            model="gpt-5-mini",
            artifact_version_hash="artifact-v1",
            prompt_version="prompt-v1",
            schema_version="schema-v1",
            validator_version="validator-v1",
            guardrail_version="guardrail-v1",
        ),
    )


def test_provider_market_impact_label_is_source_backed() -> None:
    packet = _packet_with_provider_impact()
    result = validate_news_item_brief_output(
        payload=_ready_payload(
            decision_class="watch",
            market_impacts=[
                {
                    "label": "SPCX",
                    "market_type": "private_company",
                    "target_type": "PrivateCompany",
                    "target_id": "spacex",
                    "impact_direction": "bullish",
                    "reason_zh": "Provider market impact supplied SPCX as the source-backed label.",
                    "evidence_refs": ["provider:impact:SPCX"],
                }
            ],
            evidence_refs=["provider:impact:SPCX"],
        ),
        packet=packet,
        audit={},
    )
    assert result.publishable is True
    assert result.payload is not None
    assert result.payload["market_impacts"][0]["label"] == "SPCX"
```

- [ ] **Step 3: Run harness tests and confirm they fail**

```bash
uv run pytest tests/unit/integrations/model_execution/test_news_item_brief_artifact_hash.py tests/unit/domains/news_intel/test_news_item_brief_validation.py::test_provider_market_impact_label_is_source_backed -q
```

Expected: prompt hash test fails until `artifact_hash_for` accepts `prompt_text_hash`; validator test fails until provider labels are included.

- [ ] **Step 4: Implement prompt text hashing**

In `src/parallax/platform/agent_hashing.py`, change the signature:

```python
def artifact_hash_for(
    *,
    model: str,
    prompt_version: str,
    schema_version: str,
    runtime_version: str,
    output_schema_hash: str,
    provider_family: str = "litellm",
    output_strategy: str = "json_object",
    schema_enforcement: str = "client_validate",
    request_options_hash: str | None = None,
    prompt_text_hash: str | None = None,
) -> str:
```

Add to the JSON payload:

```python
"prompt_text_hash": prompt_text_hash or json_sha256({}),
```

In `news_item_brief_stage.py`, expose:

```python
def news_item_brief_prompt_text_hash() -> str:
    return text_sha256(read_news_item_brief_prompt())
```

In both artifact hash callers, pass `prompt_text_hash=text_sha256(stage.instructions)` or `news_item_brief_prompt_text_hash()`.

- [ ] **Step 5: Include provider impact labels**

In `_source_backed_market_labels`, add:

```python
    provider = packet.provider_signal_evidence
    if provider is not None:
        for impact in provider.market_impacts:
            labels.update(
                _norm(value)
                for value in (
                    impact.label,
                    impact.market_type,
                    impact.target_type,
                    impact.target_id,
                )
                if value
            )
```

- [ ] **Step 6: Run harness tests**

```bash
uv run pytest tests/unit/integrations/model_execution/test_news_item_brief_artifact_hash.py tests/unit/domains/news_intel/test_news_item_brief_validation.py -q
```

Expected: pass.

- [ ] **Step 7: Commit Task 6**

```bash
git add src/parallax/platform/agent_hashing.py src/parallax/integrations/model_execution/news_item_brief_agent_client.py src/parallax/integrations/model_execution/execution_gateway.py src/parallax/domains/news_intel/services/news_item_brief_stage.py src/parallax/domains/news_intel/services/news_item_brief_validation.py tests/unit/integrations/model_execution/test_news_item_brief_artifact_hash.py tests/unit/domains/news_intel/test_news_item_brief_validation.py
git commit -m "fix: include news prompt text in agent artifacts"
```

## Task 7: Bounded Repair Command

**Files:**
- Create: `src/parallax/domains/news_intel/services/news_market_signal_repair.py`
- Modify: `src/parallax/app/surfaces/cli/parser.py`
- Modify: `src/parallax/app/surfaces/cli/commands/ops.py`
- Modify: `tests/unit/test_cli.py`
- Create: `tests/unit/domains/news_intel/test_news_market_signal_repair.py`

- [ ] **Step 1: Add CLI parser tests**

In `tests/unit/test_cli.py`, add:

```python
def test_ops_repair_news_market_signal_requires_mode() -> None:
    parser = build_parser()
    dry_run = parser.parse_args(["ops", "repair-news-market-signal", "--since-hours", "8", "--min-score", "80", "--dry-run"])
    execute = parser.parse_args(["ops", "repair-news-market-signal", "--since-hours", "8", "--min-score", "80", "--execute"])
    assert dry_run.ops_command == "repair-news-market-signal"
    assert dry_run.dry_run is True
    assert execute.execute is True
    with pytest.raises(SystemExit):
        parser.parse_args(["ops", "repair-news-market-signal"])
```

- [ ] **Step 2: Add service dry-run test**

Create `tests/unit/domains/news_intel/test_news_market_signal_repair.py`:

```python
from __future__ import annotations

from types import SimpleNamespace

from parallax.domains.news_intel.services.news_market_signal_repair import repair_news_market_signal


class FakeNews:
    def __init__(self) -> None:
        self.repair_rows = [{"news_item_id": "news-1", "published_at_ms": 1000}]
        self.updated = []

    def list_news_market_signal_repair_candidates(self, **kwargs):
        assert kwargs["since_ms"] == 3_600_000
        assert kwargs["min_score"] == 80
        return list(self.repair_rows)

    def update_item_market_scope_and_agent_admission(self, **kwargs):
        self.updated.append(kwargs)
        return 1


class FakeDirtyTargets:
    def __init__(self) -> None:
        self.enqueued = []

    def enqueue_targets(self, targets, **kwargs):
        self.enqueued.extend(targets)
        return len(targets)


def test_repair_news_market_signal_dry_run_reports_without_writes() -> None:
    repos = SimpleNamespace(news=FakeNews(), news_projection_dirty_targets=FakeDirtyTargets())
    result = repair_news_market_signal(repos, since_hours=1, min_score=80, execute=False, now_ms=7_200_000)
    assert result["matched_items"] == 1
    assert result["updated_items"] == 0
    assert result["enqueued_dirty_targets"] == 0
    assert repos.news.updated == []
    assert repos.news_projection_dirty_targets.enqueued == []
```

- [ ] **Step 3: Implement parser and dispatch**

In `parser.py`, add:

```python
repair_news_market_signal = ops_subcommands.add_parser(
    "repair-news-market-signal",
    help="recompute market scope and enqueue News market-signal repair targets",
)
repair_news_market_signal.add_argument("--since-hours", type=float, default=8.0)
repair_news_market_signal.add_argument("--min-score", type=int, default=80)
repair_news_market_signal_mode = repair_news_market_signal.add_mutually_exclusive_group(required=True)
repair_news_market_signal_mode.add_argument("--dry-run", action="store_true")
repair_news_market_signal_mode.add_argument("--execute", action="store_true")
```

In `ops.py`, dispatch:

```python
if args.ops_command == "repair-news-market-signal":
    data = repair_news_market_signal(
        repos,
        since_hours=float(args.since_hours),
        min_score=int(args.min_score),
        execute=bool(args.execute),
        now_ms=_now_ms(),
    )
    return 0, {"ok": True, "data": data}
```

- [ ] **Step 4: Implement repair service contract**

`repair_news_market_signal` must:

- compute `since_ms = now_ms - int(since_hours * 3_600_000)`;
- load candidates through `repos.news.list_news_market_signal_repair_candidates(since_ms=since_ms, min_score=min_score)`;
- recompute market scope and agent admission for each candidate;
- write item state only when `execute=True`;
- enqueue `page` and `brief_input` dirty targets only when `execute=True`;
- return counts: `matched_items`, `updated_items`, `enqueued_dirty_targets`, `eligible_items`, `suppressed_items`, `dry_run`.

- [ ] **Step 5: Run CLI and repair tests**

```bash
uv run pytest tests/unit/test_cli.py::test_ops_repair_news_market_signal_requires_mode tests/unit/domains/news_intel/test_news_market_signal_repair.py -q
```

Expected: pass.

- [ ] **Step 6: Commit Task 7**

```bash
git add src/parallax/app/surfaces/cli/parser.py src/parallax/app/surfaces/cli/commands/ops.py src/parallax/domains/news_intel/services/news_market_signal_repair.py tests/unit/test_cli.py tests/unit/domains/news_intel/test_news_market_signal_repair.py
git commit -m "feat: add news market signal repair command"
```

## Task 8: Canonical Docs And Contract Cleanup

**Files:**
- Modify: `docs/CONTRACTS.md`
- Modify: `docs/WORKERS.md`
- Modify: `src/parallax/domains/news_intel/ARCHITECTURE.md`
- Modify: `docs/AGENT_EXECUTION.md`
- Modify: `docs/generated/cli-help.md`

- [ ] **Step 1: Update docs**

Docs must state:

- News agent and notification eligibility are market-wide.
- `market_scope` is metadata, not rejection.
- `NON_CRYPTO` identity classification remains valid outside News product gates.
- `news_high_signal` reads market-wide `alert_eligibility`, not `analysis_admission_status`.
- `NewsItemProcessWorker` outputs `market_scope_json`, `story_identity_json`, and `agent_admission_*`.
- `NewsItemBriefAgent` artifact hashing includes prompt text hash.

- [ ] **Step 2: Regenerate CLI help**

```bash
make docs-cli-help
rg -n "repair-news-market-signal" docs/generated/cli-help.md
```

Expected: CLI help includes `repair-news-market-signal`.

- [ ] **Step 3: Run docs/runtime forbidden scan**

```bash
rg "analysis_admission|non_crypto_subject|no_crypto_native_evidence|provider_evidence_only|analysis_not_admitted" src/parallax/domains/news_intel src/parallax/domains/notifications web/src docs/CONTRACTS.md docs/WORKERS.md src/parallax/domains/news_intel/ARCHITECTURE.md docs/AGENT_EXECUTION.md
```

Expected: no output except migration downgrade text and historical completed docs outside the scanned runtime/canonical paths.

- [ ] **Step 4: Commit Task 8**

```bash
git add docs/CONTRACTS.md docs/WORKERS.md src/parallax/domains/news_intel/ARCHITECTURE.md docs/AGENT_EXECUTION.md docs/generated/cli-help.md
git commit -m "docs: document market-wide news notification contract"
```

## Task 9: Full Verification And Final Lane Move

**Files:**
- Create: `docs/superpowers/plans/active/2026-06-07-news-market-wide-notification-hard-cut-verification-cn.md`

- [ ] **Step 1: Run focused verification**

```bash
uv run pytest tests/architecture/test_news_intel_kiss_simplification.py tests/architecture/test_news_active_spec_hygiene.py -q
uv run pytest tests/unit/domains/news_intel/test_news_market_scope.py tests/unit/domains/news_intel/test_news_page_projection.py tests/unit/test_notification_rules.py tests/unit/test_api_news_contract.py tests/unit/test_postgres_schema.py -q
uv run pytest tests/unit/integrations/model_execution/test_news_item_brief_artifact_hash.py tests/unit/domains/news_intel/test_news_item_brief_validation.py -q
uv run pytest tests/integration/domains/news_intel/test_news_repository.py -q
make regen-contract
make contract-check
```

Expected: all commands exit 0.

- [ ] **Step 2: Run full verification**

```bash
make check-all
```

Expected: exit 0. Capture full output in the verification artefact.

- [ ] **Step 3: Record verification artefact**

Create `docs/superpowers/plans/active/2026-06-07-news-market-wide-notification-hard-cut-verification-cn.md` with:

```markdown
# News Market-Wide Notification Hard Cut Verification

**Spec:** `docs/superpowers/specs/active/2026-06-07-news-market-wide-notification-hard-cut-cn.md`
**Plan:** `docs/superpowers/plans/active/2026-06-07-news-market-wide-notification-hard-cut-plan-cn.md`
**Date:** 2026-06-07

## Implementation Match

The implementation removes the legacy News `analysis_admission_*` product gate and routes agent, projection, notification, API, and frontend state through market scope plus market-wide agent admission.

## Commands Run

Paste full command output for focused tests, `make regen-contract`, `make contract-check`, and `make check-all`.

## Coverage

Record the coverage summary from `make check-all`.

## Skipped Tests

Record skipped tests from `make check-all`; write `None observed` only when the output shows no skipped tests.

## E2E Golden Path

Record the News list/detail/API path checked after the hard cut.

## Other Commands Run

Record repair dry-run output:

```bash
uv run parallax ops repair-news-market-signal --since-hours 8 --min-score 80 --dry-run
```

## Residual Risks

List remaining risks or write `No residual risks beyond threshold tuning after market-wide notification eligibility is enabled.`
```

- [ ] **Step 4: Move active spec and plan after merge-ready verification**

Only after implementation is reviewed and verification is recorded:

```bash
git mv docs/superpowers/specs/active/2026-06-07-news-market-wide-notification-hard-cut-cn.md docs/superpowers/specs/completed/2026-06-07-news-market-wide-notification-hard-cut-cn.md
git mv docs/superpowers/plans/active/2026-06-07-news-market-wide-notification-hard-cut-plan-cn.md docs/superpowers/plans/completed/2026-06-07-news-market-wide-notification-hard-cut-plan-cn.md
git mv docs/superpowers/plans/active/2026-06-07-news-market-wide-notification-hard-cut-verification-cn.md docs/superpowers/plans/completed/2026-06-07-news-market-wide-notification-hard-cut-verification-cn.md
```

- [ ] **Step 5: Final commit**

```bash
git add docs/superpowers
git commit -m "docs: verify news market-wide notification hard cut"
```

## PR Breakdown

1. **PR 1 - Harness and planning hygiene:** Task 1. It makes the old gate fail in architecture tests and moves superseded active docs out of the active lane.
2. **PR 2 - Storage and market scope:** Tasks 2 and 3. It creates the new storage shape, market scope classifier, and item-processing persistence.
3. **PR 3 - Projection and notification:** Task 4. It removes the old admitted filters and makes market-wide ready `driver/watch` rows eligible.
4. **PR 4 - API/frontend/agent harness:** Tasks 5 and 6. It hard-cuts public contracts, generated types, frontend status semantics, prompt hash, and provider-impact validation.
5. **PR 5 - Repair/docs/verification:** Tasks 7, 8, and 9. It adds bounded repair, updates canonical docs, runs full verification, and closes the planning lane.

## Rollout Order

1. Merge PR 1 to make old gate regressions visible.
2. Merge PR 2 with migration; run `uv run parallax db migrate` in the target environment.
3. Merge PR 3 and start projection workers so new `news_page_rows_v5` rows are rebuilt by the single writer.
4. Merge PR 4 and deploy API/frontend together with regenerated OpenAPI types.
5. Run repair dry-run:

```bash
uv run parallax ops repair-news-market-signal --since-hours 8 --min-score 80 --dry-run
```

6. Execute repair:

```bash
uv run parallax ops repair-news-market-signal --since-hours 8 --min-score 80 --execute
```

7. Let `news_item_brief`, `news_page_projection`, and `notification_worker` catch up through normal worker intervals.

## Rollback

- Before PR 2 migration is applied, rollback is ordinary code revert.
- After PR 2 migration is applied, do not downgrade the database. Roll forward by re-adding missing market-scope projection or pausing notification channels in config.
- If notification volume is too high, raise `news_high_signal.combined_score_min` or `external_score_min` in `~/.parallax/workers.yaml`; do not restore `analysis_admission_*`.
- If API/frontend deploy fails, roll forward by redeploying matching regenerated OpenAPI/frontend build; do not reintroduce legacy optional fields.

## Acceptance Test Commands

- AC1, AC2:

```bash
uv run pytest tests/unit/domains/news_intel/test_news_market_scope.py tests/unit/domains/news_intel/test_news_item_agent_policy.py -q
```

- AC3 through AC8, AC12 through AC14:

```bash
uv run pytest tests/unit/domains/news_intel/test_news_page_projection.py tests/unit/test_notification_rules.py tests/integration/domains/news_intel/test_news_repository.py -q
```

- AC9, AC16, AC17:

```bash
uv run pytest tests/architecture/test_news_intel_kiss_simplification.py tests/architecture/test_news_active_spec_hygiene.py -q
```

- AC10, AC19, AC20:

```bash
uv run pytest tests/unit/integrations/model_execution/test_news_item_brief_artifact_hash.py tests/unit/domains/news_intel/test_news_item_brief_validation.py -q
```

- AC11, AC18:

```bash
make regen-contract
uv run pytest tests/unit/test_api_news_contract.py tests/contract -q
```

- AC15:

```bash
uv run parallax ops repair-news-market-signal --since-hours 8 --min-score 80 --dry-run
uv run parallax ops repair-news-market-signal --since-hours 8 --min-score 80 --dry-run
```

Expected second dry-run: `updated_items=0` and `enqueued_dirty_targets=0` when no source facts changed.

- AC21:

```bash
cd web && npm run typecheck && npm run lint && cd ..
```

- AC22:

```bash
uv run pytest tests/unit/test_postgres_schema.py::test_news_market_scope_hard_cut_drops_legacy_analysis_admission_columns -q
```

## Self-Review

- Spec coverage: Tasks cover active spec cleanup, runtime hard cut, storage migration, market scope, projection, notification, API, frontend, agent prompt hash, provider impact validation, repair command, docs, and full verification.
- Placeholder scan: passed; every task names concrete files, commands, and expected outcomes.
- Type consistency: `market_scope`, `agent_admission`, `signal.alert_eligibility`, and `news_market_scope_v1` names are used consistently across storage, API, frontend, tests, and docs.
