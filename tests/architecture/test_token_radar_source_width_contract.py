from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_source_edge_populate_is_windowless_narrow_event_edge() -> None:
    query = _text("src/parallax/domains/token_intel/queries/token_radar_rank_source_query.py")
    populate = query.rsplit("_POPULATE_RANK_SOURCE_EDGES_FOR_EVENT_IDS_SQL", 1)[1]

    assert "requested_event_ids" in populate
    forbidden = (
        "market_tick_current",
        "latest_price_",
        "latest_market_",
        "event_price_",
        "account_profiles",
        "social_event_extractions",
        "asset_identity_current",
        "registry_assets",
        "cex_tokens",
        "price_feeds",
        "enriched_events",
        "market_ticks",
        "row_number() OVER",
        "to_jsonb(ranked_source)",
        "sha256(",
    )
    offenders = [token for token in forbidden if token in populate]
    assert offenders == []


def test_rank_source_table_is_not_window_or_payload_coupled() -> None:
    migration = _text(
        "src/parallax/platform/db/alembic/versions/20260529_0126_token_radar_venue_source_width_hard_cut.py"
    )
    create_table = migration.split("CREATE TABLE token_radar_rank_source_events", 1)[1].split(
        "CREATE INDEX idx_token_radar_rank_source_events_target_time", 1
    )[0]

    assert "source_kind" in create_table
    assert "source_id" in create_table
    assert '"window"' not in create_table
    assert "scope" not in create_table
    assert "source_payload_json" not in create_table
    assert "factor_snapshot_json" not in create_table
    assert len([line for line in create_table.splitlines() if line.strip() and "--" not in line]) <= 32


def test_source_dirty_is_event_edge_queue_not_target_union() -> None:
    projection = _text("src/parallax/domains/token_intel/services/token_radar_projection.py")
    source_dirty_repo = _text(
        "src/parallax/domains/token_intel/repositories/token_radar_source_dirty_event_repository.py"
    )
    target_dirty_repo = _text("src/parallax/domains/token_intel/repositories/token_radar_dirty_target_repository.py")

    assert "token_radar_source_dirty_events" in source_dirty_repo
    assert "source_event_id" in source_dirty_repo
    assert "source_event_ids_json = (" not in target_dirty_repo
    assert "jsonb_agg" not in target_dirty_repo
    assert "populate_edges_for_requests(" not in projection
    assert "populate_edges_for_event_ids(" in projection


def test_source_dirty_queue_is_required_without_optional_runtime_fallback() -> None:
    projection_worker = _text("src/parallax/domains/token_intel/runtime/token_radar_projection_worker.py")
    projection_service = _text("src/parallax/domains/token_intel/services/token_radar_projection.py")
    resolution_refresh = _text("src/parallax/domains/token_intel/services/token_resolution_refresh.py")
    ingest_service = _text("src/parallax/domains/evidence/services/ingest_service.py")
    bootstrap = _text("src/parallax/app/runtime/bootstrap.py")

    forbidden_by_file = {
        "projection_worker": (
            'getattr(repos, "token_radar_source_dirty_events", None)',
            "if source_dirty_repo is not None",
            "else []",
        ),
        "projection_service": (
            'getattr(self.repos, "token_radar_source_dirty_events", None)',
            "if source_dirty_repo is not None",
            "if source_claims and source_dirty_repo is None",
        ),
        "resolution_refresh": (
            'getattr(repos, "token_radar_source_dirty_events", None)',
            "dirty_repo is not None",
        ),
        "ingest_service": ("self.token_radar_source_dirty_events is not None",),
        "bootstrap": ('getattr(repos, "token_radar_source_dirty_events", None)',),
    }
    sources = {
        "projection_worker": projection_worker,
        "projection_service": projection_service,
        "resolution_refresh": resolution_refresh,
        "ingest_service": ingest_service,
        "bootstrap": bootstrap,
    }

    offenders = [
        f"{name} contains {token}"
        for name, tokens in forbidden_by_file.items()
        for token in tokens
        if token in sources[name]
    ]

    assert "repos.token_radar_source_dirty_events.claim_due" in projection_worker
    assert "source_dirty_repo = self.repos.token_radar_source_dirty_events" in projection_service
    assert "repos.token_radar_source_dirty_events.enqueue_events" in resolution_refresh
    assert "self.token_radar_source_dirty_events.enqueue_events" in ingest_service
    assert "token_radar_source_dirty_events=repos.token_radar_source_dirty_events" in bootstrap
    assert offenders == []


def test_ingest_source_dirty_requires_formal_resolution_decisions_without_dict_fallback() -> None:
    ingest_service = _text("src/parallax/domains/evidence/services/ingest_service.py")

    forbidden_tokens = (
        "_decision_value(",
        "isinstance(decision, dict)",
        "decision.get(",
        "getattr(decision,",
        "hasattr(decision",
    )

    assert [token for token in forbidden_tokens if token in ingest_service] == []
    assert "TokenIntentResolutionDecision" in ingest_service
    assert "isinstance(decision, TokenIntentResolutionDecision)" in ingest_service
    assert "ingest_resolution_decision_contract_required" in ingest_service
    assert 'event_id = str(formal_decision.event_id or "")' in ingest_service
    assert "target_type = formal_decision.target_type" in ingest_service
    assert "target_id = formal_decision.target_id" in ingest_service


def test_projection_claim_completion_keys_require_attempt_contract_without_defaults() -> None:
    projection = _text("src/parallax/domains/token_intel/services/token_radar_projection.py")
    forbidden_tokens = (
        'int(claim.get("attempt_count") or 0)',
        'claim.get("attempt_count") or 0',
    )

    assert [token for token in forbidden_tokens if token in projection] == []
    assert "token_radar_dirty_claim_attempt_contract_required" in projection
    assert 'claim["attempt_count"]' in projection


def test_token_radar_downstream_dirty_target_repositories_are_required_without_optional_probes() -> None:
    projection_service = _text("src/parallax/domains/token_intel/services/token_radar_projection.py")

    forbidden_tokens = (
        'getattr(self.repos, "pulse_trigger_dirty_targets", None)',
        'getattr(self.repos, "narrative_admission_dirty_targets", None)',
        'getattr(self.repos, "token_profile_current_dirty_targets", None)',
        'getattr(self.repos, "token_capture_tier_dirty_targets", None)',
        "if repo is None:",
    )
    required_tokens = (
        "self.repos.pulse_trigger_dirty_targets",
        "self.repos.narrative_admission_dirty_targets",
        "self.repos.token_profile_current_dirty_targets",
        "self.repos.token_capture_tier_dirty_targets",
    )

    assert [token for token in forbidden_tokens if token in projection_service] == []
    assert [token for token in required_tokens if token not in projection_service] == []


def test_source_dirty_event_repository_uses_connection_transaction_without_manual_commit_fallback() -> None:
    source = _text("src/parallax/domains/token_intel/repositories/token_radar_source_dirty_event_repository.py")
    forbidden = (
        "self.conn.commit()",
        'getattr(self.conn, "transaction", None)',
        "return nullcontext()",
    )

    assert "def _run_repository_write" in source
    assert source.count("_run_repository_write(self.conn, commit,") == 4
    assert [token for token in forbidden if token in source] == []


def test_target_dirty_repository_uses_connection_transaction_without_manual_commit_fallback() -> None:
    source = _text("src/parallax/domains/token_intel/repositories/token_radar_dirty_target_repository.py")
    forbidden = (
        "self.conn.commit()",
        'getattr(self.conn, "transaction", None)',
        "return nullcontext()",
    )

    assert "def _run_repository_write" in source
    assert source.count("_run_repository_write(self.conn, commit,") == 7
    assert [token for token in forbidden if token in source] == []


def test_token_radar_dirty_enqueue_requires_formal_identity_without_alias_fallback() -> None:
    target_source = _text("src/parallax/domains/token_intel/repositories/token_radar_dirty_target_repository.py")
    source_source = _text("src/parallax/domains/token_intel/repositories/token_radar_source_dirty_event_repository.py")
    target_enqueue_source = target_source.split("def _dirty_records", 1)[1].split("\ndef _target_dirty_params", 1)[0]
    source_enqueue_source = source_source.split("def _source_event_records", 1)[1].split(
        "\ndef _source_completion_key",
        1,
    )[0]
    target_forbidden = (
        'row.get("target_type_key") or row.get("target_type")',
        'row.get("identity_id") or row.get("target_id")',
        'row.get("identity_id") or row.get("target_id") or row.get("intent_id")',
        "if not identity_id:",
    )
    source_forbidden = (
        'row.get("source_event_id") or row.get("event_id")',
        'row.get("target_type_key") or row.get("target_type")',
        'row.get("identity_id") or row.get("target_id")',
        "if not source_event_id or not target_type_key or not identity_id:",
    )
    required = (
        "_required_enqueue_text(",
        "token_radar_dirty_target_enqueue_identity_required",
        "token_radar_source_dirty_event_enqueue_identity_required",
    )

    assert [token for token in target_forbidden if token in target_enqueue_source] == []
    assert [token for token in source_forbidden if token in source_enqueue_source] == []
    assert [token for token in required if token not in target_source + source_source] == []


def test_token_radar_dirty_queue_write_counts_require_real_cursor_rowcount_without_defaults() -> None:
    target_source = _text("src/parallax/domains/token_intel/repositories/token_radar_dirty_target_repository.py")
    source_source = _text("src/parallax/domains/token_intel/repositories/token_radar_source_dirty_event_repository.py")
    combined = target_source + source_source
    target_enqueue_source = target_source.split("    def enqueue_targets", maxsplit=1)[1].split(
        "\n    def enqueue_market_targets",
        maxsplit=1,
    )[0]
    source_enqueue_source = source_source.split("    def enqueue_events", maxsplit=1)[1].split(
        "\n    def claim_due",
        maxsplit=1,
    )[0]
    forbidden = (
        'getattr(cursor, "rowcount"',
        'getattr(cursor, "rowcount", 0)',
        "count = int(rowcount)",
    )
    required = (
        "def _cursor_rowcount(cursor: Any) -> int:",
        "rowcount: object = cursor.rowcount",
        "isinstance(rowcount, bool) or not isinstance(rowcount, int)",
        "token_radar_dirty_target_rowcount_required",
        "token_radar_dirty_target_rowcount_invalid",
        "token_radar_source_dirty_event_rowcount_required",
        "token_radar_source_dirty_event_rowcount_invalid",
        "return _cursor_rowcount(cursor)",
    )

    assert [token for token in forbidden if token in combined] == []
    assert [token for token in required if token not in combined] == []
    assert "return len(records)" not in target_enqueue_source + source_enqueue_source
    assert "return _cursor_rowcount(cursor)" in target_enqueue_source
    assert "return _cursor_rowcount(cursor)" in source_enqueue_source


def test_rank_source_target_payloads_require_formal_identity_without_alias_fallback() -> None:
    query = _text("src/parallax/domains/token_intel/queries/token_radar_rank_source_query.py")
    target_payloads_source = query.split("def _target_payloads", 1)[1].split(
        "\n\n_LATEST_MARKET_CONTEXT_FOR_TARGETS_SQL",
        1,
    )[0]
    affected_targets_source = query.split("def affected_targets_for_event_ids", 1)[1].split(
        "\n    def populate_edges_for_event_ids",
        1,
    )[0]
    market_context_source = query.split("def latest_market_context_for_targets", 1)[1].split(
        "\n    def affected_targets_for_event_ids",
        1,
    )[0]
    combined = target_payloads_source + affected_targets_source + market_context_source
    forbidden = (
        'target.get("target_type_key") or target.get("target_type")',
        'target.get("identity_id") or target.get("target_id")',
        'payload.get("target_type_key") or ""',
        'payload.get("identity_id") or ""',
        "if not target_type_key or not identity_id",
        'if target["target_type_key"] and target["identity_id"]',
    )
    required = (
        '_required_target_payload_text(target, "target_type_key")',
        '_required_target_payload_text(target, "identity_id")',
        '_required_target_payload_text(row, "target_type_key")',
        '_required_target_payload_text(row, "identity_id")',
        '_required_target_payload_text(payload, "target_type_key")',
        '_required_target_payload_text(payload, "identity_id")',
        "token_radar_rank_source_target_identity_required",
    )

    assert [token for token in forbidden if token in combined] == []
    assert [token for token in required if token not in query] == []


def test_rank_source_mutation_counts_require_explicit_sql_evidence_without_defaults() -> None:
    query = _text("src/parallax/domains/token_intel/queries/token_radar_rank_source_query.py")
    forbidden = (
        "row or {}",
        '.get("upserted_count") or 0',
        '.get("deleted_count") or 0',
        'getattr(cursor, "rowcount"',
        'getattr(cursor, "rowcount", 0)',
        "count = int(rowcount)",
    )
    required = (
        "def _mutation_count_result(row: Any) -> Mapping[str, Any]:",
        "def _required_mutation_count(row: Mapping[str, Any], column: str) -> int:",
        "def _cursor_rowcount(cursor: Any) -> int:",
        "rowcount: object = cursor.rowcount",
        "isinstance(rowcount, bool) or not isinstance(rowcount, int)",
        "token_radar_rank_source_write_count_required",
        "token_radar_rank_source_write_count_invalid",
        "token_radar_rank_source_rowcount_required",
        "token_radar_rank_source_rowcount_invalid",
        "return _cursor_rowcount(cursor)",
    )

    assert [token for token in forbidden if token in query] == []
    assert [token for token in required if token not in query] == []


def test_token_radar_dirty_repositories_require_attempt_contract_without_default_completion_keys() -> None:
    sources = {
        "target": _text("src/parallax/domains/token_intel/repositories/token_radar_dirty_target_repository.py"),
        "source": _text("src/parallax/domains/token_intel/repositories/token_radar_source_dirty_event_repository.py"),
    }
    forbidden = (
        'int(key.get("attempt_count") or 0)',
        'key.get("attempt_count") or 0',
    )

    assert {name: [token for token in forbidden if token in source] for name, source in sources.items()} == {
        "target": [],
        "source": [],
    }
    assert all('key["attempt_count"]' in source for source in sources.values())
