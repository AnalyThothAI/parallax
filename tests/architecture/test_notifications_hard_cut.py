from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src" / "parallax"
DB_POOL_BUNDLE = SRC / "app" / "runtime" / "db_pool_bundle.py"
REPOSITORY_SESSION = SRC / "app" / "runtime" / "repository_session.py"
NOTIFICATION_REPOSITORY = SRC / "domains/notifications/repositories/notification_repository.py"
NOTIFICATION_RULES = SRC / "domains/notifications/services/notification_rules.py"
NOTIFICATION_WORKER = SRC / "domains/notifications/runtime/notification_worker.py"
NOTIFICATION_DELIVERY_WORKER = SRC / "domains/notifications/runtime/notification_delivery.py"
NOTIFICATION_RUNTIME_FILES = (
    SRC / "platform/config/settings.py",
    SRC / "domains/notifications/services/notification_rules.py",
    SRC / "domains/notifications/runtime/notification_worker.py",
    NOTIFICATION_DELIVERY_WORKER,
    SRC / "app/runtime/worker_factories/notifications.py",
)

BANNED_5MIN_NOTIFICATION_TOKENS = (
    "hot_quality_token_5m",
    "quality_token_5m",
    "social_heat_min",
    "discussion_quality_min",
    "opportunity_min",
    "token_flow_limit",
    "_hot_quality_tokens",
    "_quality_tokens",
    "_token_candidates",
    "5m heat alert",
    "5m quality alert",
)


def test_legacy_5min_notification_runtime_is_removed() -> None:
    violations: list[str] = []
    for path in NOTIFICATION_RUNTIME_FILES:
        text = path.read_text(encoding="utf-8")
        violations.extend(
            f"{path.relative_to(ROOT)} contains {token!r}" for token in BANNED_5MIN_NOTIFICATION_TOKENS if token in text
        )

    assert violations == []


def test_notification_worker_does_not_probe_legacy_insert_api() -> None:
    text = (SRC / "domains/notifications/runtime/notification_worker.py").read_text(encoding="utf-8")

    banned = (
        'getattr(repository, "insert_notification_with_outcome"',
        "SimpleNamespace(row=result",
        "repository.insert_notification(",
    )

    assert [token for token in banned if token in text] == []


def test_notification_worker_requires_delivery_requeue_contract_without_insert_only_fallback() -> None:
    text = (SRC / "domains/notifications/runtime/notification_worker.py").read_text(encoding="utf-8")

    banned = (
        'getattr(repository, "enqueue_or_requeue_delivery", None)',
        "if enqueue is None:",
    )

    assert "repository.enqueue_or_requeue_delivery" in text
    assert [token for token in banned if token in text] == []


def test_notification_worker_requires_worker_session_unit_of_work_without_manual_commit_fallback() -> None:
    text = NOTIFICATION_WORKER.read_text(encoding="utf-8")

    banned = (
        "_unit_of_work_if_available",
        "_has_unit_of_work",
        "_commit_if_available",
        "return nullcontext()",
        'getattr(repos, "unit_of_work", None)',
        'getattr(repos, "notifications", None)',
    )

    assert "repos.unit_of_work()" in text
    assert [token for token in banned if token in text] == []


def test_notification_worker_uses_formal_insert_outcome_without_shape_fallback() -> None:
    text = NOTIFICATION_WORKER.read_text(encoding="utf-8")
    banned = (
        'getattr(outcome, "row"',
        'getattr(outcome, "created"',
        'getattr(outcome, "aggregated"',
        "row = getattr(outcome",
    )

    assert [token for token in banned if token in text] == []
    assert "row = outcome.row" in text
    assert "if outcome.created:" in text
    assert "elif outcome.aggregated" in text


def test_notification_workers_read_formal_settings_without_runtime_defaults() -> None:
    rule_text = NOTIFICATION_WORKER.read_text(encoding="utf-8")
    delivery_text = NOTIFICATION_DELIVERY_WORKER.read_text(encoding="utf-8")
    settings_text = (SRC / "platform/config/settings.py").read_text(encoding="utf-8")
    rule_settings = settings_text.split("class NotificationRuleWorkerSettings", 1)[1].split(
        "\n\nclass NotificationDeliveryWorkerSettings",
        1,
    )[0]
    delivery_settings = settings_text.split("class NotificationDeliveryWorkerSettings", 1)[1].split(
        "\n\nclass NewsFetchWorkerSettings",
        1,
    )[0]
    banned = (
        'getattr(settings, "batch_size"',
        'getattr(self.settings, "statement_timeout_seconds"',
        "delivery_max_attempts: int =",
        '"batch_size", 50',
        '"batch_size", 1',
        '"statement_timeout_seconds", None',
        "max(1, int(settings.batch_size))",
    )
    violations = [f"rule:{token}" for token in banned if token in rule_text] + [
        f"delivery:{token}" for token in banned if token in delivery_text
    ]

    assert violations == []
    assert "notification_rule_settings_required" in rule_text
    assert "notification_rule_db_required" in rule_text
    assert "delivery_max_attempts: int," in rule_text
    assert 'positive_worker_setting_int(settings, "batch_size", worker_name=name)' in rule_text
    assert "notification_rule_delivery_max_attempts_required" in rule_text
    assert "statement_timeout_seconds=self.settings.statement_timeout_seconds" in rule_text
    assert "delivery_max_attempts=workers.notification_delivery.max_attempts" in (
        SRC / "app/runtime/worker_factories/notifications.py"
    ).read_text(encoding="utf-8")
    assert "notification_delivery_settings_required" in delivery_text
    assert "notification_delivery_db_required" in delivery_text
    assert 'positive_worker_setting_int(settings, "batch_size", worker_name=name)' in delivery_text
    assert "statement_timeout_seconds=self.settings.statement_timeout_seconds" in delivery_text
    assert "statement_timeout_seconds: float = Field(default=30.0, ge=0)" in rule_settings
    assert "statement_timeout_seconds: float = Field(default=30.0, ge=0)" in delivery_settings
    assert "running_timeout_ms: int = Field(default=300_000, ge=1)" in delivery_settings
    assert "stale_running_terminalization_batch_size: int = Field(default=100, ge=1)" in delivery_settings


def test_notification_factory_uses_formal_worker_settings_without_dynamic_probe() -> None:
    factory_text = (SRC / "app/runtime/worker_factories/notifications.py").read_text(encoding="utf-8")

    assert "getattr(workers, name)" not in factory_text
    assert "if workers.notification_rule.enabled:" in factory_text
    assert "if workers.notification_delivery.enabled" in factory_text


def test_notification_cooldown_uses_formal_nonnegative_contract_without_runtime_repair() -> None:
    rules_text = NOTIFICATION_RULES.read_text(encoding="utf-8")
    settings_text = (SRC / "platform/config/settings.py").read_text(encoding="utf-8")

    assert "cooldown_seconds: int = Field(default=0, ge=0)" in settings_text
    assert "notification_cooldown_seconds_required" in rules_text
    assert "max(1, int(cooldown_seconds))" not in rules_text


def test_signal_pulse_notification_rule_uses_formal_config_without_service_defaults() -> None:
    rules_text = NOTIFICATION_RULES.read_text(encoding="utf-8")
    settings_text = (SRC / "platform/config/settings.py").read_text(encoding="utf-8")
    banned = (
        "DEFAULT_SIGNAL_PULSE_WINDOW",
        "DEFAULT_SIGNAL_PULSE_SCOPES",
        "DEFAULT_SIGNAL_PULSE_STATUSES",
        "rule.window or",
        "rule.scopes or",
        "rule.statuses or",
    )

    assert [token for token in banned if token in rules_text] == []
    assert "signal_pulse_notification_rule_config_required" in rules_text
    assert '"window": "1h"' in settings_text
    assert '"scopes": SIGNAL_PULSE_NOTIFICATION_SCOPES' in settings_text
    assert '"statuses": SIGNAL_PULSE_NOTIFICATION_STATUSES' in settings_text


def test_notification_rule_candidate_limit_uses_formal_config_without_service_floor() -> None:
    rules_text = NOTIFICATION_RULES.read_text(encoding="utf-8")
    settings_text = (SRC / "platform/config/settings.py").read_text(encoding="utf-8")
    banned = (
        "DEFAULT_LIMIT",
        "max(DEFAULT_LIMIT",
        "max(50",
        "candidate_limit) or",
    )

    assert [token for token in banned if token in rules_text] == []
    assert "candidate_limit: int = Field(default=50, ge=1)" in settings_text
    assert "return int(self.settings.notifications.candidate_limit)" in rules_text


def test_notification_rule_engine_requires_explicit_evaluation_clock_without_service_default() -> None:
    rules_text = NOTIFICATION_RULES.read_text(encoding="utf-8")
    worker_text = NOTIFICATION_WORKER.read_text(encoding="utf-8")
    watched_token_section = rules_text.split("    def _watched_account_token_alerts", 1)[1].split(
        "\n    def _signal_pulse_candidates",
        1,
    )[0]
    banned = (
        "import time",
        "def evaluate(self, *, now_ms: int | None = None)",
        "now_ms if now_ms is not None else _now_ms()",
        "def _now_ms()",
    )

    assert [token for token in banned if token in rules_text] == []
    assert "def evaluate(self, *, now_ms: int) -> list[NotificationCandidate]:" in rules_text
    assert "rule_engine.evaluate(now_ms=now_ms)" in worker_text
    assert "now_ms=now_ms" in watched_token_section


def test_notification_rule_query_windows_and_news_overscan_use_formal_config_without_service_constants() -> None:
    rules_text = NOTIFICATION_RULES.read_text(encoding="utf-8")
    settings_text = (SRC / "platform/config/settings.py").read_text(encoding="utf-8")
    banned = (
        "WATCHED_ACTIVITY_WINDOW_MS",
        "NEWS_HIGH_SIGNAL_QUERY_MIN_LIMIT",
        "NEWS_HIGH_SIGNAL_QUERY_MULTIPLIER",
        "NEWS_HIGH_SIGNAL_RECENCY_WINDOW_MS",
    )

    assert [token for token in banned if token in rules_text] == []
    assert "watched_activity_window_ms: int = Field(default=3_600_000, ge=1)" in settings_text
    assert "news_high_signal_recency_window_ms: int = Field(default=7_200_000, ge=1)" in settings_text
    assert "news_high_signal_query_min_limit: int = Field(default=500, ge=1)" in settings_text
    assert "news_high_signal_query_multiplier: int = Field(default=20, ge=1)" in settings_text
    assert "self.settings.notifications.watched_activity_window_ms" in rules_text
    assert "since_ms=since_ms" in rules_text
    assert "self.settings.notifications.news_high_signal_recency_window_ms" in rules_text
    assert "self.settings.notifications.news_high_signal_query_min_limit" in rules_text
    assert "self.settings.notifications.news_high_signal_query_multiplier" in rules_text


def test_signal_pulse_notification_page_budget_uses_formal_config_without_service_constant() -> None:
    rules_text = NOTIFICATION_RULES.read_text(encoding="utf-8")
    settings_text = (SRC / "platform/config/settings.py").read_text(encoding="utf-8")
    signal_pulse_section = rules_text.split("    def _signal_pulse_candidates", 1)[1].split(
        "\n    def _news_high_signal_candidates",
        1,
    )[0]

    assert "MAX_SIGNAL_PULSE_NOTIFICATION_PAGES" not in rules_text
    assert "signal_pulse_max_pages: int = Field(default=5, ge=1)" in settings_text
    assert "self._signal_pulse_per_scope_status_limit()" in signal_pulse_section
    assert "self._limit() * int(self.settings.notifications.signal_pulse_max_pages)" in rules_text
    assert "list_signal_pulse_notification_candidates" in signal_pulse_section
    banned = (
        "list_candidates(",
        "cursor =",
        'page.get("next_cursor")',
        "range(int(self.settings.notifications.signal_pulse_max_pages))",
    )
    assert [token for token in banned if token in signal_pulse_section] == []


def test_notification_settings_reject_unused_query_fields_for_non_signal_rules() -> None:
    settings_text = (SRC / "platform/config/settings.py").read_text(encoding="utf-8")

    assert 'if key in {"watched_account_activity", "watched_account_token_alert"}:' in settings_text
    assert 'forbidden = {"scopes", "statuses", "window"}' in settings_text
    assert 'if key == "news_high_signal":' in settings_text
    assert 'forbidden = {"combined_score_min", "external_score_min", "scopes", "statuses", "window"}' in settings_text


def test_notification_delivery_stale_running_policy_uses_formal_settings_without_repository_defaults() -> None:
    repository_text = NOTIFICATION_REPOSITORY.read_text(encoding="utf-8")
    repository_session_text = REPOSITORY_SESSION.read_text(encoding="utf-8")
    db_pool_bundle_text = DB_POOL_BUNDLE.read_text(encoding="utf-8")

    assert "running_timeout_ms: int =" not in repository_text
    assert "stale_running_terminalization_batch_size: int =" not in repository_text
    assert "notification_delivery_running_timeout_ms: int" in repository_session_text
    assert (
        "NotificationRepository(\n"
        "            conn,\n"
        "            running_timeout_ms=notification_delivery_running_timeout_ms,\n"
        "            stale_running_terminalization_batch_size="
        "notification_delivery_stale_running_terminalization_batch_size,\n"
        "        )" in repository_session_text
    )
    assert (
        "notification_delivery_running_timeout_ms=int(settings.workers.notification_delivery.running_timeout_ms)"
        in db_pool_bundle_text
    )
    assert "notification_delivery_stale_running_terminalization_batch_size=int(" in db_pool_bundle_text
    assert "settings.workers.notification_delivery.stale_running_terminalization_batch_size" in db_pool_bundle_text


def test_notification_runtime_requires_positive_int_policies_without_runtime_one_repair() -> None:
    runtime_files = (
        SRC / "domains/notifications/runtime/notification_worker.py",
        SRC / "domains/notifications/runtime/notification_delivery.py",
        SRC / "domains/notifications/repositories/notification_repository.py",
    )
    violations: list[str] = []
    for path in runtime_files:
        text = path.read_text(encoding="utf-8")
        violations.extend(
            f"{path.relative_to(ROOT)} contains runtime one repair {token!r}"
            for token in ("max(1, int(settings.", "max(1, int(delivery_max_attempts", "max(1, int(max_attempts")
            if token in text
        )

    repository_text = NOTIFICATION_REPOSITORY.read_text(encoding="utf-8")
    assert violations == []
    assert "notification_delivery_max_attempts_required" in repository_text
    assert "notification_delivery_running_timeout_ms_required" in repository_text
    assert "notification_delivery_stale_running_terminalization_batch_size_required" in repository_text


def test_notification_delivery_worker_requires_session_transaction_without_manual_commit_fallback() -> None:
    text = NOTIFICATION_DELIVERY_WORKER.read_text(encoding="utf-8")
    claim_source = text.split("    def _claim_delivery_sync", maxsplit=1)[1].split(
        "\n    def _complete_delivery_sync",
        maxsplit=1,
    )[0]
    complete_source = text.split("    def _complete_delivery_sync", maxsplit=1)[1].split(
        "\n    def _fail_delivery_sync",
        maxsplit=1,
    )[0]
    fail_source = text.split("    def _fail_delivery_sync", maxsplit=1)[1].split(
        "\n    def _repository_session",
        maxsplit=1,
    )[0]

    banned = (
        ".conn.commit()",
        "return nullcontext()",
        'getattr(repos, "transaction", None)',
        "_transaction_if_available",
        "_commit_if_available",
    )

    assert "repos.transaction()" in claim_source
    assert "commit=False" in claim_source
    assert "repos.transaction()" in complete_source
    assert "commit=False" in complete_source
    assert "repos.transaction()" in fail_source
    assert "commit=False" in fail_source
    assert [token for token in banned if token in text] == []


def test_notification_delivery_repository_exposes_worker_owned_commit_boundary() -> None:
    text = NOTIFICATION_REPOSITORY.read_text(encoding="utf-8")
    claim_source = text.split("    def claim_next_delivery", maxsplit=1)[1].split(
        "\n    def complete_delivery",
        maxsplit=1,
    )[0]
    complete_source = text.split("    def complete_delivery", maxsplit=1)[1].split(
        "\n    def fail_delivery",
        maxsplit=1,
    )[0]
    fail_source = text.split("    def fail_delivery", maxsplit=1)[1].split(
        "\n    def list_deliveries",
        maxsplit=1,
    )[0]

    assert "commit: bool = True" in claim_source
    assert "_run_delivery_write(self.conn, commit, write)" in claim_source
    assert "commit: bool = True" in complete_source
    assert "_run_delivery_write(self.conn, commit, write)" in complete_source
    assert "commit: bool = True" in fail_source
    assert "_run_delivery_write(self.conn, commit, write)" in fail_source


def test_notification_delivery_attempt_contract_has_no_default_fallback() -> None:
    delivery_text = NOTIFICATION_DELIVERY_WORKER.read_text(encoding="utf-8")
    repository_text = NOTIFICATION_REPOSITORY.read_text(encoding="utf-8")
    banned = (
        'delivery.get("attempt_count")',
        'delivery.get("max_attempts")',
        'int(delivery.get("attempt_count") or 0)',
        'int(delivery.get("max_attempts") or 1)',
        'int(delivery.get("max_attempts") or 5)',
    )

    violations = [f"worker:{token}" for token in banned if token in delivery_text] + [
        f"repository:{token}" for token in banned if token in repository_text
    ]

    assert violations == []
    assert "notification_delivery_attempt_contract_required" in delivery_text
    assert "notification_delivery_attempt_contract_required" in repository_text
    assert 'attempts = int(delivery["attempt_count"])' in delivery_text
    assert 'max_attempts = int(delivery["max_attempts"])' in delivery_text
    assert 'attempts = int(delivery["attempt_count"])' in repository_text
    assert 'max_attempts = int(delivery["max_attempts"])' in repository_text


def test_notification_repository_writes_use_connection_transactions_without_manual_commit_fallback() -> None:
    text = NOTIFICATION_REPOSITORY.read_text(encoding="utf-8")
    banned = (
        "self.conn.commit()",
        "return nullcontext()",
        'getattr(self.conn, "transaction", None)',
    )

    assert "notification_repository_transaction_required" in text
    assert "def _run_repository_write" in text
    assert [token for token in banned if token in text] == []

    sections = {
        "insert_notification_with_outcome": text.split("    def insert_notification_with_outcome", maxsplit=1)[1].split(
            "\n    def _semantic_signature_duplicate",
            maxsplit=1,
        )[0],
        "mark_read": text.split("    def mark_read", maxsplit=1)[1].split("\n    def mark_all_read", maxsplit=1)[0],
        "mark_all_read": text.split("    def mark_all_read", maxsplit=1)[1].split(
            "\n    def mark_author_read",
            maxsplit=1,
        )[0],
        "mark_author_read": text.split("    def mark_author_read", maxsplit=1)[1].split(
            "\n    def enqueue_delivery",
            maxsplit=1,
        )[0],
        "enqueue_delivery": text.split("    def enqueue_delivery", maxsplit=1)[1].split(
            "\n    def enqueue_or_requeue_delivery",
            maxsplit=1,
        )[0],
        "enqueue_or_requeue_delivery": text.split("    def enqueue_or_requeue_delivery", maxsplit=1)[1].split(
            "\n    def delivery_by_id",
            maxsplit=1,
        )[0],
    }

    assert "_run_repository_write(self.conn, commit, write)" in sections["insert_notification_with_outcome"]
    assert "_run_repository_write(self.conn, True, write)" in sections["mark_read"]
    assert "_run_repository_write(self.conn, True, write)" in sections["mark_all_read"]
    assert "_run_repository_write(self.conn, True, write)" in sections["mark_author_read"]
    assert "_run_delivery_write(self.conn, commit, write)" in sections["enqueue_delivery"]
    assert "_run_delivery_write(self.conn, commit, write)" in sections["enqueue_or_requeue_delivery"]


def test_notification_insert_state_requires_real_cursor_rowcount_without_defaults() -> None:
    text = NOTIFICATION_REPOSITORY.read_text(encoding="utf-8")
    insert_source = text.split("    def insert_notification_with_outcome", maxsplit=1)[1].split(
        "\n    def _semantic_signature_duplicate",
        maxsplit=1,
    )[0]
    enqueue_source = text.split("    def enqueue_delivery", maxsplit=1)[1].split(
        "\n    def enqueue_or_requeue_delivery",
        maxsplit=1,
    )[0]
    banned = (
        "if cursor.rowcount == 0:",
        'getattr(cursor, "rowcount"',
        'getattr(cursor, "rowcount", 0)',
    )

    assert [token for token in banned if token in insert_source + enqueue_source] == []
    assert "def _single_row_write_count(" in text
    assert "rowcount: object = cursor.rowcount" in text
    assert "notification_insert_rowcount_required" in text
    assert "notification_insert_rowcount_invalid" in text
    assert "notification_delivery_enqueue_rowcount_required" in text
    assert "notification_delivery_enqueue_rowcount_invalid" in text
    assert "_single_row_write_count(" in insert_source
    assert "_single_row_write_count(" in enqueue_source


def test_notification_aggregate_update_requires_real_cursor_rowcount_without_defaults() -> None:
    text = NOTIFICATION_REPOSITORY.read_text(encoding="utf-8")
    aggregate_source = text.split("    def _aggregate_notification_row", maxsplit=1)[1].split(
        "\n    def notification_by_id",
        maxsplit=1,
    )[0]
    banned = (
        'getattr(cursor, "rowcount"',
        'getattr(cursor, "rowcount", 0)',
        "cursor.rowcount or 0",
    )
    update_position = aggregate_source.index("UPDATE notifications")
    rowcount_position = aggregate_source.index("_single_row_write_count(")
    return_position = aggregate_source.index("return True")

    assert [token for token in banned if token in aggregate_source] == []
    assert "cursor = self.conn.execute" in aggregate_source
    assert "notification_aggregate_rowcount_required" in aggregate_source
    assert "notification_aggregate_rowcount_invalid" in aggregate_source
    assert update_position < rowcount_position < return_position


def test_notification_delivery_returning_mutations_require_cursor_rowcount_match() -> None:
    text = NOTIFICATION_REPOSITORY.read_text(encoding="utf-8")
    requeue_source = text.split("    def enqueue_or_requeue_delivery", maxsplit=1)[1].split(
        "\n    def delivery_by_id",
        maxsplit=1,
    )[0]
    claim_source = text.split("    def claim_next_delivery", maxsplit=1)[1].split(
        "\n    def complete_delivery",
        maxsplit=1,
    )[0]
    returning_sources = requeue_source + claim_source
    banned = (
        "return dict(row) if row is not None else None",
        'getattr(cursor, "rowcount"',
        'getattr(cursor, "rowcount", 0)',
        "cursor.rowcount or 0",
    )

    assert [token for token in banned if token in returning_sources] == []
    assert "def _optional_returning_row(" in text
    assert "notification_delivery_requeue_rowcount_required" in requeue_source
    assert "notification_delivery_requeue_rowcount_invalid" in requeue_source
    assert "notification_delivery_claim_rowcount_required" in claim_source
    assert "notification_delivery_claim_rowcount_invalid" in claim_source
    assert "_optional_returning_row(" in requeue_source
    assert "_optional_returning_row(" in claim_source


def test_notification_delivery_terminal_mutations_are_claim_scoped_and_rowcount_checked() -> None:
    text = NOTIFICATION_REPOSITORY.read_text(encoding="utf-8")
    complete_source = text.split("    def complete_delivery", maxsplit=1)[1].split(
        "\n    def fail_delivery",
        maxsplit=1,
    )[0]
    fail_source = text.split("    def fail_delivery", maxsplit=1)[1].split(
        "\n    def list_deliveries",
        maxsplit=1,
    )[0]
    claim_predicates = (
        "AND status = 'running'",
        "AND attempt_count = %s",
        "AND updated_at_ms = %s",
    )

    for token in claim_predicates:
        assert token in complete_source
        assert token in fail_source
    assert "_delivery_claim_contract(delivery)" in complete_source
    assert "_delivery_claim_contract(delivery)" in fail_source
    assert "notification_delivery_complete_rowcount_required" in complete_source
    assert "notification_delivery_complete_rowcount_invalid" in complete_source
    assert "notification_delivery_fail_rowcount_required" in fail_source
    assert "notification_delivery_fail_rowcount_invalid" in fail_source
    assert "_single_row_write_count(" in complete_source
    assert "_single_row_write_count(" in fail_source


def test_notification_read_marker_counts_require_real_cursor_rowcount_without_len_rows_fallback() -> None:
    text = NOTIFICATION_REPOSITORY.read_text(encoding="utf-8")
    mark_read_source = text.split("    def mark_read", maxsplit=1)[1].split(
        "\n    def mark_all_read",
        maxsplit=1,
    )[0]
    mark_all_source = text.split("    def mark_all_read", maxsplit=1)[1].split(
        "\n    def mark_author_read",
        maxsplit=1,
    )[0]
    mark_author_source = text.split("    def mark_author_read", maxsplit=1)[1].split(
        "\n    def enqueue_delivery",
        maxsplit=1,
    )[0]
    read_sources = mark_read_source + mark_all_source + mark_author_source
    banned = (
        "return len(rows)",
        'getattr(cursor, "rowcount"',
        'getattr(cursor, "rowcount", 0)',
        "cursor.rowcount or 0",
    )

    assert [token for token in banned if token in read_sources] == []
    assert "def _write_count(" in text
    assert "def _returned_write_count(" in text
    assert "notification_read_mark_rowcount_required" in text
    assert "notification_read_mark_rowcount_invalid" in text
    assert "notification_read_bulk_rowcount_required" in text
    assert "notification_read_bulk_rowcount_invalid" in text
    assert "_single_row_write_count(" in mark_read_source
    assert "_returned_write_count(" in mark_all_source
    assert "_returned_write_count(" in mark_author_source


def test_notification_repository_read_lists_reject_runtime_limit_repairs() -> None:
    text = NOTIFICATION_REPOSITORY.read_text(encoding="utf-8")
    list_deliveries_source = text.split("    def list_deliveries", maxsplit=1)[1].split(
        "\n    def _select_notifications",
        maxsplit=1,
    )[0]
    select_notifications_source = text.split("    def _select_notifications", maxsplit=1)[1].split(
        "\n\ndef _json",
        maxsplit=1,
    )[0]
    combined = list_deliveries_source + select_notifications_source

    banned = ("max(0, int(limit))",)

    assert [token for token in banned if token in combined] == []
    assert "notification_delivery_list_limit_required" in list_deliveries_source
    assert "notification_list_limit_required" in select_notifications_source
    assert "def _required_nonnegative_int(value: Any, *, error_code: str) -> int:" in text


def test_notification_runtime_uses_semantic_signature_not_legacy_in_app_signature() -> None:
    files = (
        SRC / "domains/notifications/services/notification_rules.py",
        SRC / "domains/notifications/repositories/notification_repository.py",
    )

    violations: list[str] = []
    for path in files:
        text = path.read_text(encoding="utf-8")
        if "in_app_signature" in text:
            violations.append(f"{path.relative_to(ROOT)} contains legacy in_app_signature")

    assert violations == []


def test_notification_api_sanitizes_news_high_signal_payloads() -> None:
    text = (SRC / "app/surfaces/api/routes_notifications.py").read_text(encoding="utf-8")
    payload_json_source = text.split("def _notification_payload_json", maxsplit=1)[1].split("\n\n", maxsplit=1)[0]

    assert "_public_notification_payload(" in text
    assert 'payload["payload"] = _json_loads(payload.pop("payload_json"' not in text
    assert 'payload.pop("payload_json", "{}")' not in text
    assert '_notification_payload_json(rule_id, payload.pop("payload_json", None))' in text
    assert "news_high_signal_payload_json_required" in text
    assert "news_high_signal" in text
    assert "_NEWS_HIGH_SIGNAL_PAYLOAD_KEYS" not in text
    assert "public = {key: payload[key] for key in _NEWS_HIGH_SIGNAL_PAYLOAD_KEYS" not in text
    assert '_required_news_mapping(raw_payload, "payload")' in text
    assert '_required_news_mapping(value, "agent_brief")' in text
    assert '_required_news_list(value, "affected_entities")' in text
    assert '_required_news_list(value, "token_impacts")' in text
    assert "_optional_news_payload_text(payload, key)" in text
    assert '_public_news_story_payload(payload["story"])' in text
    assert '_public_news_market_scope_payload(payload["market_scope"])' in text
    assert '_public_news_agent_admission_payload(payload["agent_admission"])' in text
    assert "_required_news_payload_text(" in text
    assert "_required_news_payload_string_list(" in text
    assert "_optional_news_payload_string_list(" in text
    assert "_required_news_payload_mapping(" in text
    assert "_required_news_payload_positive_int(" in text
    assert '_optional_news_payload_bool(payload, "external_push_eligible")' in text
    assert '_optional_news_payload_nonnegative_int(payload, "duplicate_count")' in text
    assert '_required_news_agent_brief_text(payload, "status")' in text
    assert "_optional_news_agent_brief_text(payload, key)" in text
    assert "_optional_news_affected_entity_text(entity, key)" in text
    assert '_optional_news_affected_entity_string_list(entity, "evidence_refs")' in text
    assert "_optional_news_token_impact_text(impact, key)" in text
    assert "news_high_signal_{field_name}_required" in text
    assert "json.loads" not in payload_json_source
    assert "if isinstance(value, Mapping):" in payload_json_source
    assert "**payload" not in text.split("def _public_news_story_payload", maxsplit=1)[1].split("\n\n", maxsplit=1)[0]
    assert (
        "**payload"
        not in text.split("def _public_news_market_scope_payload", maxsplit=1)[1].split(
            "\n\n",
            maxsplit=1,
        )[0]
    )
    assert (
        "**payload"
        not in text.split("def _public_news_agent_admission_payload", maxsplit=1)[1].split(
            "\n\n",
            maxsplit=1,
        )[0]
    )


def test_notification_stale_running_terminalization_is_bounded_and_skip_locked() -> None:
    text = NOTIFICATION_REPOSITORY.read_text(encoding="utf-8")
    claim_source = text.split("    def claim_next_delivery", maxsplit=1)[1].split(
        "\n    def complete_delivery",
        maxsplit=1,
    )[0]
    terminalization_sql = claim_source.split("row = self.conn.execute", maxsplit=1)[0]

    assert "WITH expired AS" in terminalization_sql
    assert "ORDER BY updated_at_ms ASC, delivery_id ASC" in terminalization_sql
    assert "LIMIT %s" in terminalization_sql
    assert "FOR UPDATE SKIP LOCKED" in terminalization_sql
    assert "FROM expired" in terminalization_sql
    assert "delivery.delivery_id = expired.delivery_id" in terminalization_sql
    assert "(stale_before, self.stale_running_terminalization_batch_size, now)" in claim_source
