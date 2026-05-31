# Src Domain Package Restructure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move `src/parallax` from flat technical-layer packages into enforceable domain packages without changing public HTTP, WebSocket, CLI, config, scoring, or database behaviour.

**Architecture:** Introduce `domains/`, `app/`, `integrations/`, and `platform/` as the only long-term source packages. Move business logic domain-by-domain, keep `parallax.cli` and `parallax.__main__` as entry shims, and add structural tests that enforce package ownership, import direction, and SQL ownership. Use compatibility shims only while a slice is in flight; final verification requires old flat packages to contain no business logic.

**Tech Stack:** Python 3.13, pytest, ruff, compileall, PostgreSQL repositories, FastAPI, argparse, existing Makefile/docs-generated scripts, AST-based structural tests.

---

**Status**: Approved
**Date**: 2026-05-10
**Owning spec**: `docs/superpowers/specs/active/2026-05-10-src-domain-package-restructure.md`
**Worktree**: `.claude/worktrees/src-domain-package-restructure/` (native harness path; original draft referenced `.worktrees/...`)
**Branch**: `worktree-src-domain-package-restructure` (native harness branch; original draft referenced `codex/src-domain-package-restructure`)

## Pre-flight

- [ ] Spec is approved. Confirm `docs/superpowers/specs/active/2026-05-10-src-domain-package-restructure.md` has `**Status**: Approved`.
- [ ] Worktree exists at `.worktrees/src-domain-package-restructure/`.
- [ ] `git branch --show-current` inside the worktree returns `codex/src-domain-package-restructure`.
- [ ] `git status --short` inside the worktree is clean before implementation starts.
- [ ] Baseline `uv run ruff check .` passes.
- [ ] Baseline `uv run pytest` passes.
- [ ] Baseline `uv run python -m compileall src tests` passes.

Known-failing baseline tests: none expected. If the worktree inherits unrelated active docs from `main`, leave them untouched and record them in verification.

Create the worktree:

```bash
git worktree add .worktrees/src-domain-package-restructure -b codex/src-domain-package-restructure main
cd .worktrees/src-domain-package-restructure
git worktree list
git branch --show-current
git status --short
```

## File Structure

### New Package Roots

- Create `src/parallax/app/__init__.py`.
- Create `src/parallax/app/runtime/__init__.py`.
- Create `src/parallax/app/surfaces/__init__.py`.
- Create `src/parallax/app/surfaces/api/__init__.py`.
- Create `src/parallax/app/surfaces/cli/__init__.py`.
- Create `src/parallax/domains/__init__.py`.
- Create one `__init__.py` for each domain:
  `ingestion`, `evidence`, `asset_market`, `token_intel`, `social_enrichment`,
  `closed_loop_harness`, `notifications`, `pulse_lab`, `account_quality`.
- Inside every domain, create subpackages only when used:
  `types`, `interfaces`, `repositories`, `queries`, `services`, `scoring`, `read_models`, `runtime`.
- Create `src/parallax/integrations/__init__.py`.
- Create `src/parallax/integrations/gmgn/__init__.py`.
- Create `src/parallax/integrations/okx/__init__.py`.
- Create `src/parallax/integrations/openai_agents/__init__.py`.
- Create `src/parallax/platform/__init__.py`.
- Create `src/parallax/platform/config/__init__.py`.
- Create `src/parallax/platform/db/__init__.py`.
- Create `src/parallax/platform/logging/__init__.py`.
- Create `src/parallax/platform/paths/__init__.py`.

### Move Map

Use `git mv` for these files so history is preserved.

#### App and Platform

| Current | Target |
|---------|--------|
| `src/parallax/api/app.py` | `src/parallax/app/runtime/app.py` |
| `src/parallax/api/http.py` | `src/parallax/app/surfaces/api/http.py` |
| `src/parallax/api/ws.py` | `src/parallax/app/surfaces/api/ws.py` |
| `src/parallax/cli.py` | `src/parallax/app/surfaces/cli/main.py` |
| `src/parallax/storage/repository_session.py` | `src/parallax/app/runtime/repository_session.py` |
| `src/parallax/settings.py` | `src/parallax/platform/config/settings.py` |
| `src/parallax/runtime_paths.py` | `src/parallax/platform/paths/runtime_paths.py` |
| `src/parallax/logging_setup.py` | `src/parallax/platform/logging/setup.py` |
| `src/parallax/storage/postgres_client.py` | `src/parallax/platform/db/postgres_client.py` |
| `src/parallax/storage/postgres_migrations.py` | `src/parallax/platform/db/postgres_migrations.py` |
| `src/parallax/storage/postgres_audit.py` | `src/parallax/platform/db/postgres_audit.py` |

Create final shims:

- `src/parallax/cli.py` imports and calls `parallax.app.surfaces.cli.main`.
- `src/parallax/__main__.py` imports `main` from `parallax.cli`.
- `src/parallax/api/app.py` re-exports `create_app`, `_build_runtime`, and `_readiness_payload` from `parallax.app.runtime.app` for existing tests and app factory imports.
- `src/parallax/api/http.py` and `src/parallax/api/ws.py` re-export from the new app surface modules while tests are migrated. If no internal imports remain at the end, delete these two shims.

#### Integrations

| Current | Target |
|---------|--------|
| `src/parallax/collector/direct_ws.py` | `src/parallax/integrations/gmgn/direct_ws.py` |
| `src/parallax/market/gmgn_directory_client.py` | `src/parallax/integrations/gmgn/directory_client.py` |
| `src/parallax/market/gmgn_openapi_client.py` | `src/parallax/integrations/gmgn/openapi_client.py` |
| `src/parallax/market/okx_cex_client.py` | `src/parallax/integrations/okx/cex_client.py` |
| `src/parallax/market/okx_chains.py` | `src/parallax/integrations/okx/chains.py` |
| `src/parallax/market/okx_dex_client.py` | `src/parallax/integrations/okx/dex_client.py` |
| `src/parallax/market/okx_models.py` | `src/parallax/integrations/okx/models.py` |
| `src/parallax/pipeline/social_event_agent_client.py` | `src/parallax/integrations/openai_agents/social_event_agent_client.py` |
| `src/parallax/pipeline/pulse_thesis_agent_client.py` | `src/parallax/integrations/openai_agents/pulse_thesis_agent_client.py` |

#### `domains/ingestion`

| Current | Target |
|---------|--------|
| `src/parallax/collector/service.py` | `src/parallax/domains/ingestion/runtime/collector_service.py` |
| `src/parallax/collector/normalizer.py` | `src/parallax/domains/ingestion/services/normalizer.py` |
| `src/parallax/collector/subscriptions.py` | `src/parallax/domains/ingestion/services/subscriptions.py` |
| `src/parallax/collector/gmgn_token_payload.py` | `src/parallax/domains/ingestion/types/gmgn_token_payload.py` |

Create `src/parallax/domains/ingestion/interfaces.py` with the `IngestedEvent` dataclass currently in `pipeline/ingest_service.py` so collector runtime depends on an interface, not on token/evidence service internals.

#### `domains/evidence`

| Current | Target |
|---------|--------|
| `src/parallax/models.py` | `src/parallax/domains/evidence/types/twitter_event.py` |
| `src/parallax/pipeline/entity_extractor.py` | `src/parallax/domains/evidence/services/entity_extractor.py` |
| `src/parallax/pipeline/tweet_identity.py` | `src/parallax/domains/evidence/services/tweet_identity.py` |
| `src/parallax/pipeline/tweet_text.py` | `src/parallax/domains/evidence/services/tweet_text.py` |
| `src/parallax/storage/evidence_repository.py` | `src/parallax/domains/evidence/repositories/evidence_repository.py` |
| `src/parallax/storage/entity_repository.py` | `src/parallax/domains/evidence/repositories/entity_repository.py` |

Create `src/parallax/domains/evidence/interfaces.py` that re-exports `TwitterAuthor`, `TwitterEvent`, `TokenSnapshot`, `event_to_row`, and `decode_event_row` for cross-domain consumers.

#### `domains/asset_market`

| Current | Target |
|---------|--------|
| `src/parallax/pipeline/asset_market_sync.py` | `src/parallax/domains/asset_market/services/asset_market_sync.py` |
| `src/parallax/pipeline/asset_market_sync_worker.py` | `src/parallax/domains/asset_market/runtime/asset_market_sync_worker.py` |
| `src/parallax/pipeline/message_market_observation.py` | `src/parallax/domains/asset_market/services/message_market_observation.py` |
| `src/parallax/pipeline/message_market_observation_worker.py` | `src/parallax/domains/asset_market/runtime/message_market_observation_worker.py` |
| `src/parallax/pipeline/token_discovery_worker.py` | `src/parallax/domains/asset_market/runtime/token_discovery_worker.py` |
| `src/parallax/storage/asset_repository.py` | `src/parallax/domains/asset_market/repositories/asset_repository.py` |
| `src/parallax/storage/discovery_repository.py` | `src/parallax/domains/asset_market/repositories/discovery_repository.py` |
| `src/parallax/storage/market_repository.py` | `src/parallax/domains/asset_market/repositories/market_repository.py` |
| `src/parallax/storage/price_observation_repository.py` | `src/parallax/domains/asset_market/repositories/price_observation_repository.py` |
| `src/parallax/storage/registry_repository.py` | `src/parallax/domains/asset_market/repositories/registry_repository.py` |

Create `src/parallax/domains/asset_market/interfaces.py` with public aliases for `AssetRepository`, `RegistryRepository`, `PriceObservationRepository`, and provider result types used by token/harness domains.

#### `domains/token_intel`

| Current | Target |
|---------|--------|
| `src/parallax/pipeline/atomic_mention.py` | `src/parallax/domains/token_intel/services/atomic_mention.py` |
| `src/parallax/pipeline/cross_section_normalizer.py` | `src/parallax/domains/token_intel/scoring/cross_section_normalizer.py` |
| `src/parallax/pipeline/deterministic_token_resolver.py` | `src/parallax/domains/token_intel/services/deterministic_token_resolver.py` |
| `src/parallax/pipeline/factor_cohort.py` | `src/parallax/domains/token_intel/scoring/factor_cohort.py` |
| `src/parallax/pipeline/token_evidence_builder.py` | `src/parallax/domains/token_intel/services/token_evidence_builder.py` |
| `src/parallax/pipeline/token_intent_builder.py` | `src/parallax/domains/token_intel/services/token_intent_builder.py` |
| `src/parallax/pipeline/token_intent_rebuild.py` | `src/parallax/domains/token_intel/runtime/token_intent_rebuild.py` |
| `src/parallax/pipeline/token_intent_resolver.py` | `src/parallax/domains/token_intel/services/token_intent_resolver.py` |
| `src/parallax/pipeline/token_radar_contract.py` | `src/parallax/domains/token_intel/interfaces.py` |
| `src/parallax/pipeline/token_radar_feature_builder.py` | `src/parallax/domains/token_intel/scoring/token_radar_feature_builder.py` |
| `src/parallax/pipeline/token_radar_projection.py` | `src/parallax/domains/token_intel/services/token_radar_projection.py` |
| `src/parallax/pipeline/token_radar_projection_worker.py` | `src/parallax/domains/token_intel/runtime/token_radar_projection_worker.py` |
| `src/parallax/pipeline/token_resolution_refresh.py` | `src/parallax/domains/token_intel/runtime/token_resolution_refresh.py` |
| `src/parallax/retrieval/asset_flow_service.py` | `src/parallax/domains/token_intel/read_models/asset_flow_service.py` |
| `src/parallax/retrieval/asset_search_service.py` | `src/parallax/domains/token_intel/read_models/asset_search_service.py` |
| `src/parallax/retrieval/baseline_scoring.py` | `src/parallax/domains/token_intel/scoring/baseline_scoring.py` |
| `src/parallax/retrieval/catalyst_ranking_service.py` | `src/parallax/domains/token_intel/read_models/catalyst_ranking_service.py` |
| `src/parallax/retrieval/diffusion_health.py` | `src/parallax/domains/token_intel/scoring/diffusion_health.py` |
| `src/parallax/retrieval/discussion_quality_scoring.py` | `src/parallax/domains/token_intel/scoring/discussion_quality_scoring.py` |
| `src/parallax/retrieval/opportunity_scoring.py` | `src/parallax/domains/token_intel/scoring/opportunity_scoring.py` |
| `src/parallax/retrieval/post_text_quality.py` | `src/parallax/domains/token_intel/scoring/post_text_quality.py` |
| `src/parallax/retrieval/propagation_scoring.py` | `src/parallax/domains/token_intel/scoring/propagation_scoring.py` |
| `src/parallax/retrieval/query_parser.py` | `src/parallax/domains/token_intel/services/query_parser.py` |
| `src/parallax/retrieval/scoring_common.py` | `src/parallax/domains/token_intel/scoring/scoring_common.py` |
| `src/parallax/retrieval/social_heat_scoring.py` | `src/parallax/domains/token_intel/scoring/social_heat_scoring.py` |
| `src/parallax/retrieval/timeline_features.py` | `src/parallax/domains/token_intel/scoring/timeline_features.py` |
| `src/parallax/retrieval/timing_scoring.py` | `src/parallax/domains/token_intel/scoring/timing_scoring.py` |
| `src/parallax/retrieval/token_message_price_payload.py` | `src/parallax/domains/token_intel/read_models/token_message_price_payload.py` |
| `src/parallax/retrieval/token_target_cursor.py` | `src/parallax/domains/token_intel/read_models/token_target_cursor.py` |
| `src/parallax/retrieval/token_target_post_serializer.py` | `src/parallax/domains/token_intel/read_models/token_target_post_serializer.py` |
| `src/parallax/retrieval/token_target_posts_service.py` | `src/parallax/domains/token_intel/read_models/token_target_posts_service.py` |
| `src/parallax/retrieval/token_target_social_timeline_service.py` | `src/parallax/domains/token_intel/read_models/token_target_social_timeline_service.py` |
| `src/parallax/retrieval/token_target_stage_builder.py` | `src/parallax/domains/token_intel/read_models/token_target_stage_builder.py` |
| `src/parallax/retrieval/tradeability_scoring.py` | `src/parallax/domains/token_intel/scoring/tradeability_scoring.py` |
| `src/parallax/storage/asset_signal_repository.py` | `src/parallax/domains/token_intel/repositories/asset_signal_repository.py` |
| `src/parallax/storage/intent_resolution_repository.py` | `src/parallax/domains/token_intel/repositories/intent_resolution_repository.py` |
| `src/parallax/storage/projection_repository.py` | `src/parallax/domains/token_intel/repositories/projection_repository.py` |
| `src/parallax/storage/token_evidence_repository.py` | `src/parallax/domains/token_intel/repositories/token_evidence_repository.py` |
| `src/parallax/storage/token_intent_lookup_repository.py` | `src/parallax/domains/token_intel/repositories/token_intent_lookup_repository.py` |
| `src/parallax/storage/token_intent_repository.py` | `src/parallax/domains/token_intel/repositories/token_intent_repository.py` |
| `src/parallax/storage/token_radar_repository.py` | `src/parallax/domains/token_intel/repositories/token_radar_repository.py` |
| `src/parallax/storage/token_target_repository.py` | `src/parallax/domains/token_intel/repositories/token_target_repository.py` |

Create `src/parallax/domains/token_intel/queries/token_radar_source_query.py` and move `TokenRadarProjection._source_rows` SQL there.

#### `domains/social_enrichment`

| Current | Target |
|---------|--------|
| `src/parallax/pipeline/enrichment_worker.py` | `src/parallax/domains/social_enrichment/runtime/enrichment_worker.py` |
| `src/parallax/pipeline/social_event_extraction.py` | `src/parallax/domains/social_enrichment/types/social_event_extraction.py` |
| `src/parallax/pipeline/watched_event_gate.py` | `src/parallax/domains/social_enrichment/services/watched_event_gate.py` |
| `src/parallax/storage/enrichment_repository.py` | `src/parallax/domains/social_enrichment/repositories/enrichment_repository.py` |

Create `src/parallax/domains/social_enrichment/interfaces.py` that exposes `SocialEventExtraction`, `SocialTokenCandidate`, `AnchorTerm`, and the watched-event priority function.

#### `domains/closed_loop_harness`

| Current | Target |
|---------|--------|
| `src/parallax/pipeline/harness_credit.py` | `src/parallax/domains/closed_loop_harness/scoring/harness_credit.py` |
| `src/parallax/pipeline/harness_ops.py` | `src/parallax/domains/closed_loop_harness/services/harness_ops.py` |
| `src/parallax/pipeline/harness_ops_worker.py` | `src/parallax/domains/closed_loop_harness/runtime/harness_ops_worker.py` |
| `src/parallax/pipeline/harness_scoring.py` | `src/parallax/domains/closed_loop_harness/scoring/harness_scoring.py` |
| `src/parallax/pipeline/harness_settlement.py` | `src/parallax/domains/closed_loop_harness/scoring/harness_settlement.py` |
| `src/parallax/pipeline/harness_snapshot_builder.py` | `src/parallax/domains/closed_loop_harness/services/harness_snapshot_builder.py` |
| `src/parallax/retrieval/harness_service.py` | `src/parallax/domains/closed_loop_harness/read_models/harness_service.py` |
| `src/parallax/storage/harness_repository.py` | `src/parallax/domains/closed_loop_harness/repositories/harness_repository.py` |

Add repository methods to remove direct `.conn.execute` from harness services:

```python
def pending_market_unavailable_social_events(self, *, limit: int) -> list[dict[str, Any]]:
def snapshot_count_for_event(self, event_id: str) -> int:
def due_snapshots(self, *, horizon: str, due_before_ms: int, limit: int) -> list[dict[str, Any]]:
def outcome_exists(self, snapshot_id: str) -> bool:
def outcome_for_snapshot(self, snapshot_id: str) -> dict[str, Any] | None:
def snapshots_pending_credit(self, *, horizon: str, limit: int) -> list[dict[str, Any]]:
def credit_exists(self, credit_id: str) -> bool:
def mark_credit_assigned(self, *, snapshot_id: str) -> None:
def credit_weight_groups(self, *, limit: int) -> list[dict[str, Any]]:
def score_bucket_rows(self, *, horizon: str | None) -> list[dict[str, Any]]:
def pending_score_bucket_rows(self, *, horizon: str | None) -> list[dict[str, Any]]:
```

#### `domains/notifications`

| Current | Target |
|---------|--------|
| `src/parallax/pipeline/notification_delivery.py` | `src/parallax/domains/notifications/runtime/notification_delivery.py` |
| `src/parallax/pipeline/notification_models.py` | `src/parallax/domains/notifications/types.py` |
| `src/parallax/pipeline/notification_rules.py` | `src/parallax/domains/notifications/services/notification_rules.py` |
| `src/parallax/pipeline/notification_worker.py` | `src/parallax/domains/notifications/runtime/notification_worker.py` |
| `src/parallax/storage/notification_repository.py` | `src/parallax/domains/notifications/repositories/notification_repository.py` |

Create `src/parallax/domains/notifications/interfaces.py` to expose `NotificationRuleEngine`, notification candidates, and repository public types.

#### `domains/pulse_lab`

| Current | Target |
|---------|--------|
| `src/parallax/pipeline/pulse_candidate_gate.py` | `src/parallax/domains/pulse_lab/services/pulse_candidate_gate.py` |
| `src/parallax/pipeline/pulse_candidate_worker.py` | `src/parallax/domains/pulse_lab/runtime/pulse_candidate_worker.py` |
| `src/parallax/pipeline/pulse_contract.py` | `src/parallax/domains/pulse_lab/interfaces.py` |
| `src/parallax/pipeline/pulse_thesis.py` | `src/parallax/domains/pulse_lab/types/pulse_thesis.py` |
| `src/parallax/pipeline/pulse_timeline_context.py` | `src/parallax/domains/pulse_lab/services/pulse_timeline_context.py` |
| `src/parallax/retrieval/signal_pulse_service.py` | `src/parallax/domains/pulse_lab/read_models/signal_pulse_service.py` |
| `src/parallax/storage/pulse_repository.py` | `src/parallax/domains/pulse_lab/repositories/pulse_repository.py` |

Update pulse thesis agent imports to use `integrations/openai_agents/pulse_thesis_agent_client.py`.

#### `domains/account_quality`

| Current | Target |
|---------|--------|
| `src/parallax/retrieval/account_alert_service.py` | `src/parallax/domains/account_quality/read_models/account_alert_service.py` |
| `src/parallax/retrieval/account_quality_service.py` | `src/parallax/domains/account_quality/read_models/account_quality_service.py` |
| `src/parallax/storage/account_quality_repository.py` | `src/parallax/domains/account_quality/repositories/account_quality_repository.py` |

Create `src/parallax/domains/account_quality/interfaces.py` that exposes `AccountQualityRepository`, `AccountQualityService`, and `AccountAlertService`.

### Tests to Modify

- `tests/test_project_structure.py`
  - Replace old flat path assertions at lines 18-60 with domain-package path assertions.
  - Keep absence assertions for retired modules.
- `tests/test_harness_structure.py`
  - No source architecture changes needed.
- `tests/test_docs_generated.py`
  - Keep generated-doc checks; update expected score-version file paths after scoring modules move.
- Every test importing from old paths must import from new domain path unless it intentionally tests the entry shim:
  - `tests/test_api_*.py` should prefer `parallax.app.runtime.app` or `parallax.app.surfaces.api.*`.
  - Scoring tests should import from `parallax.domains.token_intel.scoring.*`.
  - Harness tests should import from `parallax.domains.closed_loop_harness.*`.
  - Repository tests should import from the matching domain repository.

## Tasks

### Task 1: Add Source Architecture Guardrails

**Files:**
- Create: `tests/test_src_domain_architecture.py`
- Modify: `tests/test_project_structure.py:18-60`
- Modify: `docs/TECH_DEBT.md`

- [ ] **Step 1: Write the failing architecture tests.**

Create `tests/test_src_domain_architecture.py`:

```python
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = ROOT / "src" / "parallax"

DOMAINS = {
    "ingestion",
    "evidence",
    "asset_market",
    "token_intel",
    "social_enrichment",
    "closed_loop_harness",
    "notifications",
    "pulse_lab",
    "account_quality",
}

ALLOWED_ROOTS = {"app", "domains", "integrations", "platform"}
LEGACY_PACKAGES = {"collector", "pipeline", "retrieval", "storage", "market"}
SQL_ALLOWED_PARTS = {
    "repositories",
    "queries",
    "platform/db",
    "app/runtime",
}
SHIM_ALLOWED_FILES = {
    SRC_ROOT / "cli.py",
    SRC_ROOT / "__main__.py",
    SRC_ROOT / "api" / "app.py",
    SRC_ROOT / "api" / "http.py",
    SRC_ROOT / "api" / "ws.py",
}


def _python_files() -> list[Path]:
    return [
        path
        for path in SRC_ROOT.rglob("*.py")
        if "__pycache__" not in path.parts and "storage/alembic/versions" not in path.as_posix()
    ]


def _module(path: Path) -> str:
    return ".".join(path.relative_to(ROOT / "src").with_suffix("").parts)


def _parse(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"))


def _imports(path: Path) -> list[str]:
    imports: list[str] = []
    module = _module(path)
    package_parts = module.split(".")[:-1]
    for node in ast.walk(_parse(path)):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        if isinstance(node, ast.ImportFrom):
            if node.module is None:
                continue
            if node.level:
                base = package_parts[: max(0, len(package_parts) - node.level + 1)]
                imports.append(".".join([*base, node.module]))
            else:
                imports.append(node.module)
    return [item for item in imports if item.startswith("parallax.")]


def _top_package(path: Path) -> str:
    parts = path.relative_to(SRC_ROOT).parts
    return parts[0] if parts else ""


def _domain_name(path: Path) -> str | None:
    parts = path.relative_to(SRC_ROOT).parts
    if len(parts) >= 2 and parts[0] == "domains":
        return parts[1]
    return None


def _is_sql_allowed(path: Path) -> bool:
    posix = path.relative_to(SRC_ROOT).as_posix()
    return any(part in posix for part in SQL_ALLOWED_PARTS)


def _is_thin_shim(path: Path) -> bool:
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return True
    tree = _parse(path)
    allowed = (ast.Import, ast.ImportFrom, ast.Assign, ast.AnnAssign, ast.Expr)
    return all(isinstance(node, allowed) for node in tree.body)


def test_expected_domain_packages_exist() -> None:
    assert {path.name for path in (SRC_ROOT / "domains").iterdir() if path.is_dir()} == DOMAINS
    for domain in DOMAINS:
        assert (SRC_ROOT / "domains" / domain / "__init__.py").is_file()


def test_legacy_technical_packages_contain_no_business_logic() -> None:
    offenders: list[str] = []
    for package in LEGACY_PACKAGES:
        package_path = SRC_ROOT / package
        if not package_path.exists():
            continue
        for path in package_path.rglob("*.py"):
            if path.name == "__init__.py":
                continue
            if path in SHIM_ALLOWED_FILES:
                continue
            if not _is_thin_shim(path):
                offenders.append(path.relative_to(ROOT).as_posix())
    assert offenders == []


def test_root_package_contains_only_entry_shims() -> None:
    allowed = {"__init__.py", "__main__.py", "cli.py"}
    actual = {path.name for path in SRC_ROOT.glob("*.py")}
    assert actual <= allowed


def test_platform_does_not_import_domains_or_integrations_or_app() -> None:
    offenders: list[tuple[str, str]] = []
    for path in (SRC_ROOT / "platform").rglob("*.py"):
        for imported in _imports(path):
            if imported.startswith(("parallax.domains.", "parallax.integrations.", "parallax.app.")):
                offenders.append((path.relative_to(ROOT).as_posix(), imported))
    assert offenders == []


def test_cross_domain_imports_use_interfaces() -> None:
    offenders: list[tuple[str, str]] = []
    for path in (SRC_ROOT / "domains").rglob("*.py"):
        current_domain = _domain_name(path)
        for imported in _imports(path):
            prefix = "parallax.domains."
            if not imported.startswith(prefix):
                continue
            parts = imported.removeprefix(prefix).split(".")
            imported_domain = parts[0]
            if imported_domain == current_domain:
                continue
            if len(parts) >= 2 and parts[1] == "interfaces":
                continue
            offenders.append((path.relative_to(ROOT).as_posix(), imported))
    assert offenders == []


def test_repositories_and_queries_do_not_import_services_or_runtime() -> None:
    offenders: list[tuple[str, str]] = []
    for path in (SRC_ROOT / "domains").rglob("*.py"):
        rel_parts = path.relative_to(SRC_ROOT).parts
        if "repositories" not in rel_parts and "queries" not in rel_parts:
            continue
        for imported in _imports(path):
            if ".services." in imported or ".runtime." in imported or ".read_models." in imported:
                offenders.append((path.relative_to(ROOT).as_posix(), imported))
    assert offenders == []


def test_raw_sql_is_owned_by_repositories_queries_or_app_runtime() -> None:
    offenders = [
        path.relative_to(ROOT).as_posix()
        for path in _python_files()
        if "conn.execute(" in path.read_text(encoding="utf-8") and not _is_sql_allowed(path)
    ]
    assert offenders == []


def test_no_business_modules_import_old_flat_packages() -> None:
    prefixes = tuple(f"parallax.{name}." for name in LEGACY_PACKAGES)
    offenders: list[tuple[str, str]] = []
    for path in _python_files():
        if _top_package(path) in LEGACY_PACKAGES:
            continue
        for imported in _imports(path):
            if imported.startswith(prefixes):
                offenders.append((path.relative_to(ROOT).as_posix(), imported))
    assert offenders == []
```

- [ ] **Step 2: Replace flat path expectations in `tests/test_project_structure.py`.**

Change `test_project_uses_standard_uv_src_layout` to assert these roots:

```python
def test_project_uses_domain_package_src_layout():
    base = ROOT / "src" / "parallax"
    assert (ROOT / "pyproject.toml").is_file()
    assert (base / "__init__.py").is_file()
    assert (base / "__main__.py").is_file()
    assert (base / "cli.py").is_file()
    assert (base / "app" / "runtime" / "app.py").is_file()
    assert (base / "app" / "surfaces" / "api" / "http.py").is_file()
    assert (base / "app" / "surfaces" / "api" / "ws.py").is_file()
    assert (base / "app" / "surfaces" / "cli" / "main.py").is_file()
    for domain in {
        "ingestion",
        "evidence",
        "asset_market",
        "token_intel",
        "social_enrichment",
        "closed_loop_harness",
        "notifications",
        "pulse_lab",
        "account_quality",
    }:
        assert (base / "domains" / domain / "__init__.py").is_file()
    assert (base / "integrations" / "gmgn" / "__init__.py").is_file()
    assert (base / "integrations" / "okx" / "__init__.py").is_file()
    assert (base / "integrations" / "openai_agents" / "__init__.py").is_file()
    assert (base / "platform" / "db" / "postgres_client.py").is_file()
    assert (ROOT / "Makefile").is_file()
    assert (ROOT / "Dockerfile").is_file()
    assert (ROOT / "compose.yaml").is_file()
```

- [ ] **Step 3: Run tests and verify red.**

```bash
uv run pytest tests/test_src_domain_architecture.py tests/test_project_structure.py -q
```

Expected: failures naming missing `domains/`, existing flat package business modules, and old project-structure path assertions.

- [ ] **Step 4: Commit.**

```bash
git add tests/test_src_domain_architecture.py tests/test_project_structure.py docs/TECH_DEBT.md
git commit -m "test: add source domain architecture guardrails"
```

### Task 2: Move Platform, Integrations, and App Entry Shims

**Files:**
- Move app/platform/integration files listed in "App and Platform" and "Integrations".
- Modify imports in `src/parallax/app/runtime/app.py`.
- Modify imports in `src/parallax/app/surfaces/api/http.py`.
- Modify imports in `src/parallax/app/surfaces/api/ws.py`.
- Create/modify shims: `src/parallax/cli.py`, `src/parallax/__main__.py`, `src/parallax/api/app.py`, `src/parallax/api/http.py`, `src/parallax/api/ws.py`.
- Tests: `tests/test_api_health.py`, `tests/test_api_http.py`, `tests/test_api_static.py`, `tests/test_api_websocket.py`, `tests/test_cli.py`, `tests/test_settings.py`, `tests/test_okx_clients.py`, `tests/test_gmgn_directory_client.py`, `tests/test_gmgn_openapi_client.py`.

- [ ] **Step 1: Move files.**

Run the `git mv` commands from the App and Platform and Integrations tables.

- [ ] **Step 2: Update app/runtime imports.**

In `app/runtime/app.py`, update imports to the new platform and integration paths. Required import replacements:

```python
from ...integrations.gmgn.direct_ws import DirectGmgnWebSocketClient
from ...integrations.okx.cex_client import OkxCexClient
from ...integrations.okx.dex_client import OkxDexClient
from ...platform.config.settings import Settings, load_settings
from ...platform.db.postgres_client import create_pool, postgres_health_check, with_password_from_file
from ...platform.db.postgres_migrations import latest_migration_version
from .repository_session import PooledRepository, repository_session
from ..surfaces.api.http import ApiBadRequest, ApiUnauthorized, api_bad_request_response, api_unauthorized_response, create_api_router
from ..surfaces.api.ws import PublicWebSocketHub
```

Keep domain imports temporarily pointing to old flat packages until their domain tasks move them.

- [ ] **Step 3: Update CLI imports.**

In `app/surfaces/cli/main.py`, update platform and integration imports:

```python
from ...platform.config.settings import load_settings
from ...platform.db.postgres_audit import audit_postgres
from ...platform.db.postgres_client import create_pool, postgres_health_check, with_password_from_file
from ...platform.db.postgres_migrations import run_migrations
from ...integrations.gmgn.directory_client import GmgnDirectoryClient
from ...integrations.okx.cex_client import OkxCexClient
from ...integrations.okx.dex_client import OkxDexClient
```

Keep domain imports temporarily pointing to old flat packages until later tasks.

- [ ] **Step 4: Add entry shims.**

`src/parallax/cli.py`:

```python
from __future__ import annotations

from .app.surfaces.cli.main import main

__all__ = ["main"]
```

`src/parallax/__main__.py`:

```python
from __future__ import annotations

from .cli import main

if __name__ == "__main__":
    raise SystemExit(main())
```

`src/parallax/api/app.py`:

```python
from __future__ import annotations

from ..app.runtime.app import *  # noqa: F403
```

`src/parallax/api/http.py`:

```python
from __future__ import annotations

from ..app.surfaces.api.http import *  # noqa: F403
```

`src/parallax/api/ws.py`:

```python
from __future__ import annotations

from ..app.surfaces.api.ws import *  # noqa: F403
```

- [ ] **Step 5: Update tests that import app/platform/integration modules.**

Use new imports for focused tests. Examples:

```python
from parallax.app.runtime.app import create_app
from parallax.platform.config.settings import Settings
from parallax.integrations.okx.dex_client import OkxDexClient
from parallax.integrations.gmgn.directory_client import GmgnDirectoryClient
```

Tests for the installed CLI may keep exercising `parallax.cli:main`.

- [ ] **Step 6: Run focused tests.**

```bash
uv run pytest tests/test_api_health.py tests/test_api_http.py tests/test_api_static.py tests/test_api_websocket.py tests/test_cli.py tests/test_settings.py tests/test_okx_clients.py tests/test_gmgn_directory_client.py tests/test_gmgn_openapi_client.py -q
uv run ruff check src/parallax/app src/parallax/integrations src/parallax/platform tests/test_api_health.py tests/test_api_http.py tests/test_api_websocket.py tests/test_cli.py tests/test_settings.py tests/test_okx_clients.py
```

Expected: focused tests and ruff pass; `tests/test_src_domain_architecture.py` still fails because domain moves are not complete.

- [ ] **Step 7: Commit.**

```bash
git add src/parallax tests
git commit -m "refactor: introduce app platform and integration packages"
```

### Task 3: Move Evidence and Ingestion Domains

**Files:**
- Move files listed in `domains/ingestion` and `domains/evidence`.
- Modify `src/parallax/domains/ingestion/runtime/collector_service.py`.
- Modify `src/parallax/domains/evidence/interfaces.py`.
- Modify `src/parallax/app/runtime/repository_session.py`.
- Modify `src/parallax/app/runtime/app.py`.
- Tests: `tests/test_collector_service.py`, `tests/test_direct_ws.py`, `tests/test_event_normalizer.py`, `tests/test_gmgn_token_payload.py`, `tests/test_entity_extractor.py`, `tests/test_evidence_repository.py`, `tests/test_postgres_repositories.py`.

- [ ] **Step 1: Move ingestion and evidence files.**

Run the `git mv` commands from the `domains/ingestion` and `domains/evidence` tables.

- [ ] **Step 2: Create ingestion interface.**

`src/parallax/domains/ingestion/interfaces.py`:

```python
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from parallax.domains.evidence.interfaces import TwitterEvent


@dataclass(frozen=True, slots=True)
class IngestedEvent:
    event: TwitterEvent
    entities: list[dict[str, Any]]
    alerts: list[dict[str, Any]]
    inserted: bool
    enrichment_job_id: str | None = None
    token_intents: list[dict[str, Any]] = field(default_factory=list)
    token_resolutions: list[dict[str, Any]] = field(default_factory=list)
```

Remove the duplicate `IngestedEvent` definition from the moved ingest service in Task 6.

- [ ] **Step 3: Create evidence interface.**

`src/parallax/domains/evidence/interfaces.py`:

```python
from __future__ import annotations

from .types.twitter_event import TokenSnapshot, TwitterAuthor, TwitterEvent
from .repositories.evidence_repository import decode_event_row, event_to_row

__all__ = [
    "TokenSnapshot",
    "TwitterAuthor",
    "TwitterEvent",
    "decode_event_row",
    "event_to_row",
]
```

- [ ] **Step 4: Update moved imports.**

Required replacements:

```python
from parallax.domains.evidence.interfaces import TwitterEvent
from parallax.domains.ingestion.interfaces import IngestedEvent
from parallax.domains.evidence.services.entity_extractor import EVM_QUERY_CHAINS, normalize_ca
from parallax.domains.evidence.services.tweet_identity import canonical_tweet_url, logical_dedup_key
from parallax.domains.evidence.services.tweet_text import build_text_projection
```

Collector runtime should import `IngestedEvent` only from the interface:

```python
from parallax.domains.ingestion.interfaces import IngestedEvent
```

- [ ] **Step 5: Update repository session.**

In `app/runtime/repository_session.py`, replace evidence/entity repository imports:

```python
from parallax.domains.evidence.repositories.entity_repository import EntityRepository
from parallax.domains.evidence.repositories.evidence_repository import EvidenceRepository
```

- [ ] **Step 6: Update tests.**

Use new imports:

```python
from parallax.domains.evidence.interfaces import TwitterAuthor, TwitterEvent
from parallax.domains.evidence.repositories.evidence_repository import EvidenceRepository
from parallax.domains.evidence.repositories.entity_repository import EntityRepository
from parallax.domains.evidence.services.entity_extractor import extract_entities_from_surfaces
from parallax.domains.ingestion.runtime.collector_service import CollectorService
from parallax.domains.ingestion.services.normalizer import normalize_gmgn_payload
from parallax.domains.ingestion.types.gmgn_token_payload import parse_gmgn_token_payload
```

- [ ] **Step 7: Run focused tests.**

```bash
uv run pytest tests/test_collector_service.py tests/test_direct_ws.py tests/test_event_normalizer.py tests/test_gmgn_token_payload.py tests/test_entity_extractor.py tests/test_evidence_repository.py tests/test_postgres_repositories.py -q
uv run ruff check src/parallax/domains/ingestion src/parallax/domains/evidence tests/test_collector_service.py tests/test_event_normalizer.py tests/test_entity_extractor.py tests/test_evidence_repository.py
```

Expected: focused tests pass.

- [ ] **Step 8: Commit.**

```bash
git add src/parallax tests
git commit -m "refactor: move ingestion and evidence domains"
```

### Task 4: Move Asset Market Domain

**Files:**
- Move files listed in `domains/asset_market`.
- Modify moved asset-market imports.
- Modify `app/runtime/repository_session.py`.
- Modify `app/runtime/app.py`.
- Modify `app/surfaces/cli/main.py`.
- Tests: `tests/test_asset_market_sync.py`, `tests/test_message_market_observation.py`, `tests/test_token_discovery_worker.py`, `tests/test_asset_repository.py`, `tests/test_registry_repository.py`, `tests/test_price_observation_repository.py`, `tests/test_discovery_and_lookup_repositories.py`, `tests/test_market_observation_repository.py` if present in the checkout.

- [ ] **Step 1: Move asset-market files.**

Run the `git mv` commands from the `domains/asset_market` table.

- [ ] **Step 2: Create asset-market interface.**

`src/parallax/domains/asset_market/interfaces.py`:

```python
from __future__ import annotations

from .repositories.asset_repository import AssetRepository
from .repositories.discovery_repository import DiscoveryRepository
from .repositories.price_observation_repository import PriceObservationRepository
from .repositories.registry_repository import RegistryRepository

__all__ = [
    "AssetRepository",
    "DiscoveryRepository",
    "PriceObservationRepository",
    "RegistryRepository",
]
```

- [ ] **Step 3: Update imports.**

Required replacements:

```python
from parallax.domains.asset_market.repositories.asset_repository import AssetRepository
from parallax.domains.asset_market.repositories.registry_repository import RegistryRepository
from parallax.domains.asset_market.repositories.price_observation_repository import PriceObservationRepository
from parallax.integrations.okx.chains import chain_id_to_okx
from parallax.integrations.okx.dex_client import OkxDexClient
from parallax.integrations.okx.cex_client import OkxCexClient
from parallax.integrations.gmgn.openapi_client import GmgnOpenApiClient
from parallax.integrations.gmgn.directory_client import GmgnDirectoryClient
from parallax.platform.db.postgres_client import transaction
```

- [ ] **Step 4: Update repository session and app runtime.**

Repository session imports:

```python
from parallax.domains.asset_market.repositories.asset_repository import AssetRepository
from parallax.domains.asset_market.repositories.discovery_repository import DiscoveryRepository
from parallax.domains.asset_market.repositories.market_repository import MarketRepository
from parallax.domains.asset_market.repositories.price_observation_repository import PriceObservationRepository
from parallax.domains.asset_market.repositories.registry_repository import RegistryRepository
```

App runtime imports:

```python
from parallax.domains.asset_market.runtime.asset_market_sync_worker import AssetMarketSyncWorker
from parallax.domains.asset_market.runtime.message_market_observation_worker import MessageMarketObservationWorker
from parallax.domains.asset_market.runtime.token_discovery_worker import TokenDiscoveryWorker
```

- [ ] **Step 5: Run focused tests.**

```bash
uv run pytest tests/test_asset_market_sync.py tests/test_message_market_observation.py tests/test_token_discovery_worker.py tests/test_asset_repository.py tests/test_registry_repository.py tests/test_price_observation_repository.py tests/test_discovery_and_lookup_repositories.py -q
uv run ruff check src/parallax/domains/asset_market src/parallax/integrations tests/test_asset_market_sync.py tests/test_message_market_observation.py tests/test_asset_repository.py tests/test_registry_repository.py
```

Expected: focused tests pass.

- [ ] **Step 6: Commit.**

```bash
git add src/parallax tests
git commit -m "refactor: move asset market domain"
```

### Task 5: Move Token Intel Domain and Own Token-Radar SQL

**Files:**
- Move files listed in `domains/token_intel`.
- Create: `domains/token_intel/queries/token_radar_source_query.py`.
- Modify: `domains/token_intel/services/token_radar_projection.py`.
- Modify: `app/runtime/repository_session.py`.
- Modify: `app/runtime/app.py`.
- Modify: `app/surfaces/api/http.py`.
- Modify: `app/surfaces/cli/main.py`.
- Tests: all `tests/test_token_*`, all scoring tests, `tests/test_asset_flow_service.py`, `tests/test_asset_search_service.py`, `tests/test_query_parser.py`, `tests/test_postgres_retrieval_services.py`.

- [ ] **Step 1: Move token-intel files.**

Run the `git mv` commands from the `domains/token_intel` table.

- [ ] **Step 2: Create token-radar source query.**

Move the SQL currently inside `TokenRadarProjection._source_rows` into:

```python
# src/parallax/domains/token_intel/queries/token_radar_source_query.py
from __future__ import annotations

from typing import Any


class TokenRadarSourceQuery:
    def __init__(self, conn: Any):
        self.conn = conn

    def source_rows(self, *, since_ms: int, scope: str, now_ms: int) -> list[dict[str, Any]]:
        watched_clause = "AND events.is_watched = true" if scope == "matched" else ""
        rows = self.conn.execute(
            f"""
            SELECT
              token_intents.*,
              token_intent_resolutions.resolution_id,
              token_intent_resolutions.target_type,
              token_intent_resolutions.target_id,
              COALESCE(token_intent_resolutions.pricefeed_id, preferred_price_feed.pricefeed_id) AS pricefeed_id,
              token_intent_resolutions.resolution_status,
              token_intent_resolutions.reason_codes_json,
              token_intent_resolutions.candidate_ids_json,
              token_intent_resolutions.lookup_keys_json,
              discovery.discovery_results AS discovery_results_json,
              token_intent_resolutions.decision_time_ms,
              events.author_handle,
              events.is_watched,
              events.received_at_ms,
              events.text,
              events.text_clean,
              events.reference_json,
              events.author_followers,
              events.author_tags_json,
              events.event_json,
              price_observations.price_usd,
              price_observations.market_cap_usd,
              price_observations.liquidity_usd,
              price_observations.volume_24h_usd,
              price_observations.holders,
              price_observations.observed_at_ms AS price_observed_at_ms,
              price_observations.provider AS price_provider
            FROM token_intents
            JOIN events ON events.event_id = token_intents.event_id
            LEFT JOIN token_intent_resolutions
              ON token_intent_resolutions.intent_id = token_intents.intent_id
            LEFT JOIN LATERAL (
              SELECT pricefeed_id
              FROM price_feeds
              WHERE subject_type = token_intent_resolutions.target_type
                AND subject_id = token_intent_resolutions.target_id
              ORDER BY updated_at_ms DESC
              LIMIT 1
            ) preferred_price_feed ON true
            LEFT JOIN LATERAL (
              SELECT po.*
              FROM price_observations po
              WHERE po.pricefeed_id = COALESCE(token_intent_resolutions.pricefeed_id, preferred_price_feed.pricefeed_id)
                AND po.observed_at_ms <= %s
              ORDER BY po.observed_at_ms DESC
              LIMIT 1
            ) price_observations ON true
            LEFT JOIN LATERAL (
              SELECT jsonb_agg(to_jsonb(dr.*) ORDER BY dr.observed_at_ms DESC) AS discovery_results
              FROM discovery_results dr
              WHERE dr.intent_id = token_intents.intent_id
            ) discovery ON true
            WHERE events.received_at_ms >= %s
              {watched_clause}
            ORDER BY events.received_at_ms DESC
            """,
            (now_ms, since_ms),
        ).fetchall()
        return [dict(row) for row in rows]
```

If the current `_source_rows` query has additional selected fields beyond this block, preserve them exactly when moving; do not change scoring semantics.

- [ ] **Step 3: Update projection service to use the query.**

In `domains/token_intel/services/token_radar_projection.py`:

```python
from parallax.domains.token_intel.queries.token_radar_source_query import TokenRadarSourceQuery
```

Replace `_source_rows` body with:

```python
def _source_rows(self, *, since_ms: int, scope: str, now_ms: int) -> list[dict[str, Any]]:
    return TokenRadarSourceQuery(self.repos.conn).source_rows(since_ms=since_ms, scope=scope, now_ms=now_ms)
```

Keep this one `.conn` access temporarily in token-intel service until Task 11 moves query construction into `RepositorySession`. The architecture test allows raw SQL only in the query file, and the service no longer contains SQL.

- [ ] **Step 4: Update imports.**

Representative replacements:

```python
from parallax.domains.token_intel.interfaces import TOKEN_RADAR_PROJECTION_VERSION
from parallax.domains.token_intel.scoring.social_heat_scoring import social_heat_score
from parallax.domains.token_intel.scoring.discussion_quality_scoring import discussion_quality_score
from parallax.domains.token_intel.scoring.tradeability_scoring import tradeability_score
from parallax.domains.token_intel.read_models.asset_flow_service import AssetFlowService
from parallax.domains.token_intel.read_models.asset_search_service import AssetSearchService
from parallax.domains.token_intel.repositories.token_radar_repository import TokenRadarRepository
from parallax.domains.token_intel.services.token_intent_resolver import TokenIntentResolver
```

- [ ] **Step 5: Update repository session.**

Replace token repository imports with domain paths:

```python
from parallax.domains.token_intel.repositories.asset_signal_repository import AssetSignalRepository
from parallax.domains.token_intel.repositories.intent_resolution_repository import IntentResolutionRepository
from parallax.domains.token_intel.repositories.projection_repository import ProjectionRepository
from parallax.domains.token_intel.repositories.token_evidence_repository import TokenEvidenceRepository
from parallax.domains.token_intel.repositories.token_intent_lookup_repository import TokenIntentLookupRepository
from parallax.domains.token_intel.repositories.token_intent_repository import TokenIntentRepository
from parallax.domains.token_intel.repositories.token_radar_repository import TokenRadarRepository
from parallax.domains.token_intel.repositories.token_target_repository import TokenTargetRepository
```

- [ ] **Step 6: Run focused tests.**

```bash
uv run pytest tests/test_token_evidence_builder.py tests/test_token_intent_builder.py tests/test_token_intent_resolver.py tests/test_token_intent_rebuild.py tests/test_token_resolution_refresh.py tests/test_token_radar_projection.py tests/test_token_radar_feature_builder.py tests/test_token_radar_projection_worker.py tests/test_token_radar_repository.py tests/test_asset_flow_service.py tests/test_asset_search_service.py tests/test_query_parser.py tests/test_baseline_scoring.py tests/test_social_heat_scoring.py tests/test_discussion_quality_scoring.py tests/test_propagation_scoring.py tests/test_opportunity_scoring.py tests/test_timing_scoring.py tests/test_tradeability_scoring.py tests/test_token_target_posts_service.py tests/test_token_target_social_timeline_service.py tests/test_token_target_stage_builder.py -q
uv run ruff check src/parallax/domains/token_intel tests/test_token_radar_projection.py tests/test_asset_flow_service.py tests/test_social_heat_scoring.py
```

Expected: focused tests pass.

- [ ] **Step 7: Commit.**

```bash
git add src/parallax tests
git commit -m "refactor: move token intel domain"
```

### Task 6: Move Ingest Orchestration Into Evidence Domain

**Files:**
- Move: `src/parallax/pipeline/ingest_service.py` to `src/parallax/domains/evidence/services/ingest_service.py`.
- Modify: `domains/evidence/services/ingest_service.py`.
- Modify: `domains/ingestion/runtime/collector_service.py`.
- Modify: `app/runtime/app.py`.
- Tests: `tests/test_asset_ingest_flow.py`, `tests/test_collector_service.py`, `tests/test_enrichment_worker.py`, `tests/test_postgres_repositories.py`, `tests/test_token_intent_builder.py`.

- [ ] **Step 1: Move ingest service.**

```bash
git mv src/parallax/pipeline/ingest_service.py src/parallax/domains/evidence/services/ingest_service.py
```

- [ ] **Step 2: Update `IngestedEvent` import and remove duplicate dataclass.**

In moved `ingest_service.py`, remove the local `IngestedEvent` dataclass and add:

```python
from parallax.domains.ingestion.interfaces import IngestedEvent
```

Required repository/service imports:

```python
from parallax.domains.asset_market.repositories.price_observation_repository import PriceObservationRepository
from parallax.domains.asset_market.repositories.registry_repository import RegistryRepository
from parallax.domains.evidence.interfaces import TwitterEvent, event_to_row
from parallax.domains.evidence.repositories.entity_repository import EntityRepository
from parallax.domains.evidence.repositories.evidence_repository import EvidenceRepository
from parallax.domains.evidence.services.entity_extractor import TextSurface, extract_entities_from_surfaces
from parallax.domains.social_enrichment.interfaces import watched_social_event_priority
from parallax.domains.token_intel.repositories.intent_resolution_repository import IntentResolutionRepository
from parallax.domains.token_intel.repositories.token_evidence_repository import TokenEvidenceRepository
from parallax.domains.token_intel.repositories.token_intent_lookup_repository import TokenIntentLookupRepository
from parallax.domains.token_intel.repositories.token_intent_repository import TokenIntentRepository
from parallax.domains.token_intel.services.token_evidence_builder import build_token_evidence
from parallax.domains.token_intel.services.token_intent_builder import build_token_intents
from parallax.domains.token_intel.services.token_intent_resolver import TokenIntentResolutionDecision, TokenIntentResolver
from parallax.platform.db.postgres_client import transaction
```

- [ ] **Step 3: Update app runtime.**

```python
from parallax.domains.evidence.services.ingest_service import IngestService
```

- [ ] **Step 4: Run focused tests.**

```bash
uv run pytest tests/test_asset_ingest_flow.py tests/test_collector_service.py tests/test_enrichment_worker.py tests/test_postgres_repositories.py -q
uv run ruff check src/parallax/domains/evidence/services/ingest_service.py tests/test_asset_ingest_flow.py
```

Expected: focused tests pass.

- [ ] **Step 5: Commit.**

```bash
git add src/parallax tests
git commit -m "refactor: move ingest orchestration into evidence domain"
```

### Task 7: Move Social Enrichment and Closed-Loop Harness Domains

**Files:**
- Move files listed in `domains/social_enrichment` and `domains/closed_loop_harness`.
- Modify `domains/closed_loop_harness/repositories/harness_repository.py`.
- Modify `domains/closed_loop_harness/services/harness_ops.py`.
- Modify `domains/closed_loop_harness/read_models/harness_service.py`.
- Modify `domains/social_enrichment/runtime/enrichment_worker.py`.
- Modify `app/runtime/repository_session.py`.
- Modify `app/runtime/app.py`.
- Modify `app/surfaces/api/http.py`.
- Modify `app/surfaces/cli/main.py`.
- Tests: `tests/test_enrichment_worker.py`, `tests/test_social_event_extraction.py`, `tests/test_social_event_agent_client.py`, `tests/test_harness_ops.py`, `tests/test_harness_repository.py`, `tests/test_harness_scoring.py`, `tests/test_harness_settlement_credit.py`, `tests/test_harness_snapshot_builder.py`.

- [ ] **Step 1: Move files.**

Run the `git mv` commands from `domains/social_enrichment` and `domains/closed_loop_harness`.

- [ ] **Step 2: Create social enrichment interface.**

`src/parallax/domains/social_enrichment/interfaces.py`:

```python
from __future__ import annotations

from .services.watched_event_gate import watched_social_event_priority
from .types.social_event_extraction import AnchorTerm, SocialEventExtraction, SocialTokenCandidate

__all__ = [
    "AnchorTerm",
    "SocialEventExtraction",
    "SocialTokenCandidate",
    "watched_social_event_priority",
]
```

- [ ] **Step 3: Move harness SQL from services/read models into repository.**

Add the methods listed in the File Structure section to `closed_loop_harness/repositories/harness_repository.py`.

Replace direct SQL in `closed_loop_harness/services/harness_ops.py`:

```python
rows = harness.pending_market_unavailable_social_events(limit=limit)
before = harness.snapshot_count_for_event(str(social_event["event_id"]))
rows = harness.due_snapshots(horizon=horizon, due_before_ms=now, limit=limit)
existed = harness.outcome_exists(str(snapshot["snapshot_id"]))
rows = harness.snapshots_pending_credit(horizon=horizon, limit=limit)
outcome = harness.outcome_for_snapshot(str(row["snapshot_id"]))
if harness.credit_exists(credit_id):
    continue
harness.mark_credit_assigned(snapshot_id=str(snapshot["snapshot_id"]))
groups = harness.credit_weight_groups(limit=limit)
```

Replace direct SQL in `closed_loop_harness/read_models/harness_service.py`:

```python
rows = self.harness.score_bucket_rows(horizon=horizon)
pending_rows = self.harness.pending_score_bucket_rows(horizon=horizon)
```

- [ ] **Step 4: Update moved imports.**

Representative replacements:

```python
from parallax.domains.closed_loop_harness.services.harness_snapshot_builder import HarnessSnapshotBuilder
from parallax.domains.closed_loop_harness.runtime.harness_ops_worker import HarnessOpsWorker
from parallax.domains.closed_loop_harness.read_models.harness_service import HarnessService
from parallax.domains.closed_loop_harness.repositories.harness_repository import HarnessRepository
from parallax.domains.social_enrichment.runtime.enrichment_worker import EnrichmentWorker
from parallax.domains.social_enrichment.repositories.enrichment_repository import EnrichmentRepository
from parallax.integrations.openai_agents.social_event_agent_client import OpenAIAgentsSocialEventClient
```

- [ ] **Step 5: Run focused tests.**

```bash
uv run pytest tests/test_enrichment_worker.py tests/test_social_event_extraction.py tests/test_social_event_agent_client.py tests/test_harness_ops.py tests/test_harness_repository.py tests/test_harness_scoring.py tests/test_harness_settlement_credit.py tests/test_harness_snapshot_builder.py -q
uv run ruff check src/parallax/domains/social_enrichment src/parallax/domains/closed_loop_harness tests/test_enrichment_worker.py tests/test_harness_ops.py tests/test_harness_repository.py
```

Expected: focused tests pass and `test_raw_sql_is_owned_by_repositories_queries_or_app_runtime` no longer reports harness services.

- [ ] **Step 6: Commit.**

```bash
git add src/parallax tests
git commit -m "refactor: move enrichment and harness domains"
```

### Task 8: Move Notifications, Pulse Lab, and Account Quality Domains

**Files:**
- Move files listed in `domains/notifications`, `domains/pulse_lab`, and `domains/account_quality`.
- Modify imports in app runtime, API surface, CLI surface, notification rules, pulse worker, and pulse read model.
- Tests: `tests/test_notification_delivery.py`, `tests/test_notification_repository.py`, `tests/test_notification_rules.py`, `tests/test_notification_worker.py`, `tests/test_pulse_candidate_gate.py`, `tests/test_pulse_candidate_worker.py`, `tests/test_pulse_repository.py`, `tests/test_pulse_thesis.py`, `tests/test_pulse_thesis_agent_client.py`, `tests/test_pulse_timeline_context.py`, `tests/test_signal_pulse_service.py`, `tests/test_account_quality_repository.py`, `tests/test_account_quality_service.py`.

- [ ] **Step 1: Move notification files and create interface.**

Run the `git mv` commands from `domains/notifications`.

`src/parallax/domains/notifications/interfaces.py`:

```python
from __future__ import annotations

from .repositories.notification_repository import NotificationRepository
from .services.notification_rules import NotificationRuleEngine
from .types import NotificationCandidate

__all__ = ["NotificationCandidate", "NotificationRepository", "NotificationRuleEngine"]
```

- [ ] **Step 2: Move pulse files and update OpenAI integration import.**

Run the `git mv` commands from `domains/pulse_lab`.

Required import replacement:

```python
from parallax.integrations.openai_agents.pulse_thesis_agent_client import OpenAIAgentsPulseThesisClient
```

- [ ] **Step 3: Move account-quality files and create interface.**

Run the `git mv` commands from `domains/account_quality`.

`src/parallax/domains/account_quality/interfaces.py`:

```python
from __future__ import annotations

from .read_models.account_alert_service import AccountAlertService
from .read_models.account_quality_service import AccountQualityService
from .repositories.account_quality_repository import AccountQualityRepository

__all__ = ["AccountAlertService", "AccountQualityRepository", "AccountQualityService"]
```

- [ ] **Step 4: Update app runtime and API imports.**

Representative replacements:

```python
from parallax.domains.account_quality.read_models.account_alert_service import AccountAlertService
from parallax.domains.notifications.runtime.notification_delivery import NotificationDeliveryWorker
from parallax.domains.notifications.runtime.notification_worker import NotificationWorker
from parallax.domains.notifications.services.notification_rules import NotificationRuleEngine
from parallax.domains.pulse_lab.runtime.pulse_candidate_worker import PulseCandidateWorker, PulseTriggerThresholds
from parallax.domains.pulse_lab.services.pulse_candidate_gate import PulseGateThresholds
from parallax.domains.pulse_lab.read_models.signal_pulse_service import SignalPulseService
from parallax.domains.pulse_lab.repositories.pulse_repository import PulseRepository
```

- [ ] **Step 5: Run focused tests.**

```bash
uv run pytest tests/test_notification_delivery.py tests/test_notification_repository.py tests/test_notification_rules.py tests/test_notification_worker.py tests/test_pulse_candidate_gate.py tests/test_pulse_candidate_worker.py tests/test_pulse_repository.py tests/test_pulse_thesis.py tests/test_pulse_thesis_agent_client.py tests/test_pulse_timeline_context.py tests/test_signal_pulse_service.py tests/test_account_quality_repository.py tests/test_account_quality_service.py -q
uv run ruff check src/parallax/domains/notifications src/parallax/domains/pulse_lab src/parallax/domains/account_quality tests/test_notification_rules.py tests/test_pulse_candidate_gate.py tests/test_account_quality_service.py
```

Expected: focused tests pass.

- [ ] **Step 6: Commit.**

```bash
git add src/parallax tests
git commit -m "refactor: move notifications pulse and account domains"
```

### Task 9: Remove Old Flat Package Business Logic and Update All Imports

**Files:**
- Modify every remaining import under `src/` and `tests/` that references `parallax.collector`, `parallax.pipeline`, `parallax.retrieval`, `parallax.storage`, or `parallax.market`.
- Delete old flat package modules that are not approved shims.
- Modify: `tests/test_src_domain_architecture.py` if the shim allowlist needs to shrink.
- Modify: `scripts/regen_score_versions.py` only if it assumes old paths.

- [ ] **Step 1: Find remaining old imports.**

```bash
rg -n "parallax\\.(collector|pipeline|retrieval|storage|market)\\." src tests scripts
```

Expected before edits: a finite list of old imports. Expected after edits: no matches except approved shims if they exist.

- [ ] **Step 2: Replace old imports with domain paths.**

Use direct replacements, not broad regex blindly. Examples:

```python
from parallax.domains.token_intel.scoring.baseline_scoring import token_baseline_v2
from parallax.domains.closed_loop_harness.scoring.harness_credit import assign_cluster_credits
from parallax.domains.evidence.repositories.evidence_repository import EvidenceRepository
from parallax.domains.asset_market.repositories.asset_repository import AssetRepository
from parallax.platform.db.postgres_client import create_pool
```

- [ ] **Step 3: Delete or reduce legacy packages.**

Keep only these shims if still needed:

```text
src/parallax/api/app.py
src/parallax/api/http.py
src/parallax/api/ws.py
src/parallax/cli.py
src/parallax/__main__.py
```

Delete old business modules:

```bash
for path in src/parallax/collector src/parallax/pipeline src/parallax/retrieval src/parallax/storage src/parallax/market; do
  test ! -d "$path" || find "$path" -type f -name '*.py' ! -name '__init__.py' -print
done
```

For every printed file that is not an approved shim, remove it with `git rm`.

- [ ] **Step 4: Run architecture tests.**

```bash
uv run pytest tests/test_src_domain_architecture.py tests/test_project_structure.py -q
```

Expected: both files pass.

- [ ] **Step 5: Run import and compile checks.**

```bash
uv run ruff check src tests
uv run python -m compileall src tests
```

Expected: both commands pass.

- [ ] **Step 6: Commit.**

```bash
git add src tests scripts
git commit -m "refactor: remove old flat source packages"
```

### Task 10: Update Architecture Docs and Generated Artefacts

**Files:**
- Modify: `docs/ARCHITECTURE.md`
- Modify: `docs/generated/score-versions.md`
- Modify: `docs/generated/cli-help.md` if import path changes alter hidden help internals.
- Modify: `docs/generated/ws-protocol.md` if API module path extraction changes.
- Modify: `docs/generated/db-schema.md` only if regeneration changes formatting metadata.
- Modify: `docs/TECH_DEBT.md` if shims or follow-ups remain.

- [ ] **Step 1: Rewrite `docs/ARCHITECTURE.md` as the domain package map.**

Replace the current technical-layer table with:

````markdown
# Architecture

> **Scope.** Owns Python-service package boundaries, dependency direction, and conceptual data flow for `parallax`. Frontend (`web/`) architecture lives in `FRONTEND.md`. Public interface contracts live in `CONTRACTS.md`.

The service is organised around domain packages, explicit integration adapters, platform infrastructure, and app surfaces.

```
GMGN public stream
  -> domains/ingestion
  -> domains/evidence
  -> domains/token_intel
  -> domains/social_enrichment
  -> domains/closed_loop_harness
  -> domains/notifications and domains/pulse_lab
  -> app/surfaces/api + app/surfaces/cli
```

## Package Roots

| Root | Responsibility |
|------|----------------|
| `app/` | Composition root plus HTTP, WebSocket, and CLI surfaces. It wires domains and translates public inputs/outputs. |
| `domains/` | Product domains. Each domain owns its repositories, queries, services/scoring, read models, and runtime workers. |
| `integrations/` | External adapters for GMGN, OKX, and OpenAI Agents. These translate third-party API shapes but do not own product decisions. |
| `platform/` | Config, PostgreSQL infrastructure, logging, and runtime paths. Platform never imports product domains. |

## Domains

| Domain | Responsibility |
|--------|----------------|
| `domains/ingestion/` | GMGN public-stream frame handling, snapshot gate, handle filtering, raw public-stream normalisation, collector status. |
| `domains/evidence/` | Canonical Twitter event model, event identity, text projection, entity extraction surfaces, evidence and entity persistence. |
| `domains/asset_market/` | Asset registry, chain/address identity, price observations, discovery, market hydration, asset-market sync. |
| `domains/token_intel/` | Token evidence, token intents, intent resolution, token target views, token-radar features, scoring, projection, token-radar read models. |
| `domains/social_enrichment/` | Watched-event gate, social-event extraction schema, enrichment job lifecycle, enrichment worker. |
| `domains/closed_loop_harness/` | Social-event harness extraction read model, attention seeds, snapshots, settlement, outcomes, credits, weights, harness health. |
| `domains/notifications/` | Notification rules, persistence, delivery, and workers. |
| `domains/pulse_lab/` | Signal pulse read model, pulse candidate gate/worker, thesis model, and pulse persistence. |
| `domains/account_quality/` | Account quality snapshots, account quality read model, and account alert read model. |

## Dependency Direction

Within a domain, use:

```
types/config -> repositories/queries -> services/scoring -> read_models/runtime -> app surfaces
```

Cross-domain imports must go through `domains/<domain>/interfaces.py`. Raw SQL lives in `repositories/`, `queries/`, `platform/db/`, or `app/runtime/` composition health checks. `tests/test_src_domain_architecture.py` enforces these rules.
````

- [ ] **Step 2: Regenerate generated docs.**

```bash
make docs-generated
```

Expected: `docs/generated/score-versions.md` paths change from `retrieval/*_scoring.py` to `domains/token_intel/scoring/*`; CLI and WS protocol remain semantically stable.

- [ ] **Step 3: Run docs and structure tests.**

```bash
uv run pytest tests/test_docs_generated.py tests/test_harness_structure.py tests/test_src_domain_architecture.py tests/test_project_structure.py -q
```

Expected: all pass.

- [ ] **Step 4: Commit.**

```bash
git add docs tests
git commit -m "docs: document source domain package architecture"
```

### Task 11: Full Verification and Plan Closure Artefact

**Files:**
- Create: `docs/superpowers/plans/active/2026-05-10-src-domain-package-restructure-verification.md`
- Modify: `docs/TECH_DEBT.md` only for real follow-up items discovered during execution.

- [ ] **Step 1: Run full verification commands.**

```bash
uv run ruff check .
uv run pytest
uv run python -m compileall src tests
make docs-generated
git diff --exit-code docs/generated
```

Expected: all commands exit 0.

- [ ] **Step 2: Exercise CLI surface.**

```bash
uv run parallax --help
uv run parallax db --help
uv run parallax ops --help
```

Expected: all commands exit 0 and show the existing command groups.

- [ ] **Step 3: Write verification artefact.**

Create `docs/superpowers/plans/active/2026-05-10-src-domain-package-restructure-verification.md`:

````markdown
# Src Domain Package Restructure Verification

**Date:** 2026-05-10
**Plan:** `docs/superpowers/plans/active/2026-05-10-src-domain-package-restructure.md`
**Spec:** `docs/superpowers/specs/active/2026-05-10-src-domain-package-restructure.md`
**Branch:** `codex/src-domain-package-restructure`

## Commands

| Command | Result |
|---------|--------|
| `uv run ruff check .` | PASS |
| `uv run pytest` | PASS |
| `uv run python -m compileall src tests` | PASS |
| `make docs-generated` | PASS |
| `git diff --exit-code docs/generated` | PASS |
| `uv run parallax --help` | PASS |
| `uv run parallax db --help` | PASS |
| `uv run parallax ops --help` | PASS |

## Acceptance Criteria

- AC1: PASS. `docs/ARCHITECTURE.md` documents domain packages and import direction.
- AC2: PASS. `tests/test_src_domain_architecture.py` enforces import and SQL ownership.
- AC3: PASS. Old flat packages contain no business logic modules.
- AC4: PASS. API, WebSocket, CLI, repository, scoring, and worker tests pass.
- AC5: PASS. Generated docs are regenerated and clean.
- AC6: PASS. New feature placement is governed by structural tests.
- AC7: PASS. Completion gates were run and recorded here.

## Manual / Live Gaps

No live WebSocket or Docker Compose flow was exercised in this refactor because public runtime behaviour and database schema were unchanged. Existing API, WebSocket, CLI, repository, and worker tests covered the moved code paths.

## Follow-Ups

No follow-up items remain.
````

If any follow-up remains, replace "No follow-up items remain" with the exact item and append it to `docs/TECH_DEBT.md` in the same commit.

- [ ] **Step 4: Final diff review.**

```bash
git diff --stat main...HEAD
git diff --name-status main...HEAD
```

Expected: moved source files, updated imports/tests/docs, no database migration files.

- [ ] **Step 5: Commit verification.**

```bash
git add docs/superpowers/plans/active/2026-05-10-src-domain-package-restructure-verification.md docs/TECH_DEBT.md
git commit -m "docs: record source domain restructure verification"
```

## PR Breakdown

1. **PR 1 — Architecture Guardrails**: Task 1 only. Adds failing structural tests and updates project structure expectations.
2. **PR 2 — App / Platform / Integrations**: Task 2. Move process wiring, API/CLI surfaces, config/db/logging/path infrastructure, and external adapters.
3. **PR 3 — Ingestion / Evidence / Asset Market**: Tasks 3 and 4. Move stream ingestion, canonical evidence, and market identity/price infrastructure.
4. **PR 4 — Token Intel / Ingest Orchestration**: Tasks 5 and 6. Move token extraction/resolution/scoring/read models/projection and place ingest orchestration behind domain interfaces.
5. **PR 5 — Enrichment / Harness**: Task 7. Move enrichment and closed-loop harness, and put harness SQL behind repository methods.
6. **PR 6 — Notifications / Pulse / Account Quality**: Task 8. Move the remaining domains.
7. **PR 7 — Remove Legacy Packages + Docs**: Tasks 9, 10, and 11. Remove old flat business modules, update architecture docs/generated docs, and record verification.

Each PR must pass its focused tests plus `uv run ruff check src tests` and `uv run python -m compileall src tests`. The final PR must pass the full verification gate.

## Rollout Order

1. Create worktree and baseline checks.
2. Add structural tests red.
3. Move platform/integrations/app surfaces.
4. Move domains in the order: ingestion/evidence, asset_market, token_intel, social_enrichment/closed_loop_harness, notifications/pulse_lab/account_quality.
5. Remove old flat package business modules.
6. Update architecture docs and generated docs.
7. Run full verification.
8. Open PR series or squash into one final PR after all slice commits are green.

No database migration, backfill, feature flag, or deploy sequencing is required because this refactor changes source ownership only.

## Rollback

- Before merge: reset the worktree branch to `main` or abandon the worktree with `git worktree remove .worktrees/src-domain-package-restructure`.
- After a slice PR but before final PR: revert the slice commit with `git revert <sha>`; no schema or data rollback is required.
- After final merge: revert the final PR. Public config, HTTP, WebSocket, CLI, and database schema remain compatible because no public contract changed.
- If generated docs are accidentally changed semantically, rerun `make docs-generated` on the reverted tree and commit the clean generated state.

## Acceptance Test Commands

- AC1:
  ```bash
  rg -n "Package Roots|Domains|Dependency Direction|domains/token_intel|cross-domain imports" docs/ARCHITECTURE.md
  ```
  Expected: all headings and domain references are present.

- AC2:
  ```bash
  uv run pytest tests/test_src_domain_architecture.py -q
  ```
  Expected: all tests pass.

- AC3:
  ```bash
  for path in src/parallax/collector src/parallax/pipeline src/parallax/retrieval src/parallax/storage src/parallax/market; do
    test ! -d "$path" || find "$path" -type f -name '*.py' ! -name '__init__.py' -print
  done
  ```
  Expected: no output, except approved API/CLI shims outside those flat packages.

- AC4:
  ```bash
  uv run pytest tests/test_api_health.py tests/test_api_http.py tests/test_api_websocket.py tests/test_cli.py tests/test_token_radar_projection.py tests/test_harness_ops.py tests/test_notification_rules.py tests/test_pulse_candidate_worker.py -q
  ```
  Expected: all pass.

- AC5:
  ```bash
  make docs-generated
  git diff --exit-code docs/generated
  ```
  Expected: no diff.

- AC6:
  ```bash
  uv run pytest tests/test_src_domain_architecture.py::test_cross_domain_imports_use_interfaces tests/test_src_domain_architecture.py::test_no_business_modules_import_old_flat_packages -q
  ```
  Expected: both pass.

- AC7:
  ```bash
  test -f docs/superpowers/plans/active/2026-05-10-src-domain-package-restructure-verification.md
  rg -n "uv run ruff check|uv run pytest|compileall|Acceptance Criteria" docs/superpowers/plans/active/2026-05-10-src-domain-package-restructure-verification.md
  ```
  Expected: file exists and records all completion gates.

## Verification

Verification will be recorded in `docs/superpowers/plans/active/2026-05-10-src-domain-package-restructure-verification.md` during Task 11. The task is not complete until that artefact exists and the full command table shows PASS for ruff, pytest, compileall, generated docs, and CLI help checks.
