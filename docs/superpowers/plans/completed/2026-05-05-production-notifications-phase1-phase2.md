# Production Notifications Phase 1/2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a production-grade notification layer for GMGN Twitter Intel, starting with durable in-app web notifications and then adding audited external delivery through Apprise.

**Architecture:** Add a new `notifications` bounded context with SQLite-backed notification facts, rule evaluation, HTTP read APIs, WebSocket live push, and React inbox UI. Phase 2 adds external channel configuration and a retrying delivery worker without changing Phase 1 notification facts or frontend read state.

**Tech Stack:** Python 3.13, FastAPI, SQLite WAL, Pydantic settings, existing repository/worker patterns, React 19, TanStack Query, Zustand, reconnecting-websocket, Sonner for transient toast, Apprise for multi-channel delivery.

---

## Spec

Design spec: `docs/superpowers/specs/2026-05-05-production-notifications-phase1-phase2-design-cn.md`

Phase gates:

- Phase 1 must be fully usable without external channels.
- Phase 2 must not modify Phase 1 rule semantics or frontend read-state semantics.
- Browser Push, Novu, service workers, rule editor UI, and multi-user RBAC are deliberately out of scope.

## File Structure

### Backend files

- Modify: `pyproject.toml`
  - Phase 2 only: add `apprise>=1.10.0`.
- Modify: `src/gmgn_twitter_intel/settings.py`
  - Add `NotificationsConfig`, `NotificationRuleConfig`, `NotificationChannelConfig`.
  - Add redacted config output fields through properties.
- Modify: `src/gmgn_twitter_intel/storage/sqlite_schema.py`
  - Bump `SCHEMA_VERSION` from `11` to `12`.
  - Add notification tables and indexes.
  - Add app table names.
- Modify: `src/gmgn_twitter_intel/storage/sqlite_client.py`
  - Add notification operational probes.
- Create: `src/gmgn_twitter_intel/storage/notification_repository.py`
  - Durable notification facts, read state, delivery state, summaries.
- Create: `src/gmgn_twitter_intel/pipeline/notification_models.py`
  - Small dataclasses for notification inputs/results. Keep this file framework-free.
- Create: `src/gmgn_twitter_intel/pipeline/notification_rules.py`
  - Deterministic rule engine using existing repositories and `TokenFlowService`.
- Create: `src/gmgn_twitter_intel/pipeline/notification_worker.py`
  - Phase 1 rule worker.
- Create: `src/gmgn_twitter_intel/pipeline/notification_delivery.py`
  - Phase 2 external delivery worker and Apprise adapter.
- Modify: `src/gmgn_twitter_intel/api/app.py`
  - Wire repositories/workers into `CliRuntime`.
- Modify: `src/gmgn_twitter_intel/api/http.py`
  - Add `/api/notifications`, `/api/notification-summary`, mark-read endpoints, and Phase 2 delivery audit.
- Modify: `src/gmgn_twitter_intel/api/ws.py`
  - Add `notifications` subscription option and route notification payloads.
- Modify: `src/gmgn_twitter_intel/cli.py`
  - Add config redaction and Phase 2 `notification-deliveries` query command.

### Backend tests

- Create: `tests/test_notification_repository.py`
- Create: `tests/test_notification_rules.py`
- Create: `tests/test_notification_worker.py`
- Create: `tests/test_notification_delivery.py`
- Modify: `tests/test_sqlite_schema.py`
- Modify: `tests/test_api_http.py`
- Modify: `tests/test_api_websocket.py`
- Modify: `tests/test_settings.py`
- Modify: `tests/test_cli.py`

### Frontend files

- Modify: `web/package.json`
- Modify: `web/package-lock.json`
- Modify: `web/src/api/types.ts`
- Modify: `web/src/api/useIntelSocket.ts`
- Modify: `web/src/App.tsx`
- Modify: `web/src/styles.css`
- Create: `web/src/api/notifications.ts`
- Create: `web/src/components/NotificationBell.tsx`
- Create: `web/src/components/NotificationDrawer.tsx`
- Create: `web/src/components/WatchlistNotificationDot.tsx`
- Create: `web/src/components/NotificationToastBridge.tsx`
- Create: `web/src/components/NotificationCenter.test.tsx`

---

## Phase 1: Durable In-App Notifications

### Task 1: Add Notification Settings

**Files:**
- Modify: `src/gmgn_twitter_intel/settings.py`
- Modify: `tests/test_settings.py`
- Modify: `src/gmgn_twitter_intel/cli.py`
- Modify: `tests/test_cli.py`

- [ ] **Step 1: Write settings tests**

Add tests covering defaults, rule overrides, and channel URL redaction:

```python
def test_settings_loads_notification_defaults(tmp_path, monkeypatch):
    config_dir = tmp_path / ".gmgn-twitter-intel"
    config_dir.mkdir()
    (config_dir / "config.yaml").write_text(
        """
ws_token: secret
handles: [toly]
notifications:
  enabled: true
  poll_interval_seconds: 3
  token_flow_limit: 40
  rules:
    hot_quality_token_5m:
      enabled: true
      channels: ["in_app"]
      social_heat_min: 82
      discussion_quality_min: 72
      suppress_chase_risk: true
      cooldown_seconds: 600
  channels:
    pushdeer:
      enabled: true
      provider: apprise
      url: pushdeer://pushKey
      min_severity: high
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("GMGN_TWITTER_INTEL_HOME", str(config_dir))

    settings = load_settings()

    assert settings.notifications.enabled is True
    assert settings.notifications.poll_interval_seconds == 3
    assert settings.notifications.token_flow_limit == 40
    assert settings.notifications.rules["hot_quality_token_5m"].social_heat_min == 82
    assert settings.notifications.channels["pushdeer"].url == "pushdeer://pushKey"
```

Add CLI redaction assertion to `tests/test_cli.py`:

```python
def test_cli_config_redacts_notification_channel_urls(tmp_path, monkeypatch, capsys):
    config_dir = tmp_path / ".gmgn-twitter-intel"
    config_dir.mkdir()
    (config_dir / "config.yaml").write_text(
        """
ws_token: secret
handles: [toly]
notifications:
  channels:
    pushdeer:
      enabled: true
      provider: apprise
      url: pushdeer://pushKey
      min_severity: high
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("GMGN_TWITTER_INTEL_HOME", str(config_dir))

    assert main(["config"]) == 0
    output = capsys.readouterr().out

    assert "pushdeer://pushKey" not in output
    assert '"url_configured": true' in output
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
uv run pytest tests/test_settings.py tests/test_cli.py -q
```

Expected: FAIL because `notifications` settings and redacted config output do not exist.

- [ ] **Step 3: Implement Pydantic config models**

In `settings.py`, add these models near other config models:

```python
SEVERITIES = {"info", "warning", "high", "critical"}
NOTIFICATION_RULE_IDS = {
    "watched_account_activity",
    "watched_account_token_alert",
    "hot_quality_token_5m",
    "quality_token_5m",
    "harness_snapshot_high_score",
}


class NotificationRuleConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    channels: tuple[str, ...] = ("in_app",)
    social_heat_min: int | None = None
    discussion_quality_min: int | None = None
    opportunity_min: int | None = None
    combined_score_min: float | None = None
    suppress_chase_risk: bool = False
    cooldown_seconds: int = 0

    @field_validator("channels", mode="before")
    @classmethod
    def parse_channels(cls, value: Any) -> tuple[str, ...]:
        parsed = tuple(_split_values(value))
        return parsed or ("in_app",)


class NotificationChannelConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    provider: str = "apprise"
    url: str | None = None
    min_severity: str = "warning"
    max_attempts: int = 5

    @field_validator("provider", mode="before")
    @classmethod
    def parse_provider(cls, value: Any) -> str:
        normalized = str(value or "apprise").strip().lower()
        if normalized not in {"apprise", "log"}:
            raise ValueError("notifications channel provider must be 'apprise' or 'log'")
        return normalized

    @field_validator("url", mode="before")
    @classmethod
    def parse_url(cls, value: Any) -> str | None:
        if value is None:
            return None
        normalized = str(value).strip()
        return normalized or None

    @field_validator("min_severity", mode="before")
    @classmethod
    def parse_min_severity(cls, value: Any) -> str:
        normalized = str(value or "warning").strip().lower()
        if normalized not in SEVERITIES:
            raise ValueError("notifications channel min_severity must be info, warning, high, or critical")
        return normalized
```

Add:

```python
def _default_notification_rules() -> dict[str, NotificationRuleConfig]:
    return {
        "watched_account_activity": NotificationRuleConfig(channels=("in_app",)),
        "watched_account_token_alert": NotificationRuleConfig(channels=("in_app",)),
        "hot_quality_token_5m": NotificationRuleConfig(
            channels=("in_app",),
            social_heat_min=80,
            discussion_quality_min=70,
            suppress_chase_risk=True,
            cooldown_seconds=900,
        ),
        "quality_token_5m": NotificationRuleConfig(
            channels=("in_app",),
            social_heat_min=65,
            discussion_quality_min=80,
            cooldown_seconds=900,
        ),
        "harness_snapshot_high_score": NotificationRuleConfig(
            channels=("in_app",),
            combined_score_min=0.8,
            cooldown_seconds=0,
        ),
    }
```

Add:

```python
class NotificationsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    poll_interval_seconds: float = 5.0
    delivery_poll_interval_seconds: float = 5.0
    retention_days: int = 14
    subscriber_key: str = "local"
    token_flow_limit: int = 80
    external_min_severity: str = "warning"
    rules: dict[str, NotificationRuleConfig] = Field(default_factory=_default_notification_rules)
    channels: dict[str, NotificationChannelConfig] = Field(default_factory=dict)

    @field_validator("subscriber_key", mode="before")
    @classmethod
    def parse_subscriber_key(cls, value: Any) -> str:
        normalized = str(value or "local").strip()
        return normalized or "local"

    @field_validator("external_min_severity", mode="before")
    @classmethod
    def parse_external_min_severity(cls, value: Any) -> str:
        normalized = str(value or "warning").strip().lower()
        if normalized not in SEVERITIES:
            raise ValueError("notifications.external_min_severity must be info, warning, high, or critical")
        return normalized

    @field_validator("rules", mode="before")
    @classmethod
    def merge_default_rules(cls, value: Any) -> dict[str, Any]:
        merged = {key: rule.model_dump() for key, rule in _default_notification_rules().items()}
        if isinstance(value, dict):
            for key, raw_rule in value.items():
                if key not in NOTIFICATION_RULE_IDS:
                    raise ValueError(f"unsupported notification rule: {key}")
                base = dict(merged[key])
                if isinstance(raw_rule, dict):
                    base.update(raw_rule)
                merged[key] = base
        return merged
```

Add `notifications: NotificationsConfig = Field(default_factory=NotificationsConfig)` to `Settings`.

- [ ] **Step 4: Update default config YAML**

Append this block to `default_config_yaml()`:

```yaml
notifications:
  enabled: true
  poll_interval_seconds: 5
  delivery_poll_interval_seconds: 5
  retention_days: 14
  subscriber_key: "local"
  token_flow_limit: 80
  external_min_severity: "warning"
  rules:
    watched_account_activity:
      enabled: true
      channels: ["in_app"]
    watched_account_token_alert:
      enabled: true
      channels: ["in_app"]
    hot_quality_token_5m:
      enabled: true
      channels: ["in_app"]
      social_heat_min: 80
      discussion_quality_min: 70
      suppress_chase_risk: true
      cooldown_seconds: 900
    quality_token_5m:
      enabled: true
      channels: ["in_app"]
      social_heat_min: 65
      discussion_quality_min: 80
      cooldown_seconds: 900
    harness_snapshot_high_score:
      enabled: true
      channels: ["in_app"]
      combined_score_min: 0.8
  channels: {}
```

- [ ] **Step 5: Redact config CLI output**

In `cli.py` `command == "config"`, add:

```python
"notifications": {
    "enabled": settings.notifications.enabled,
    "poll_interval_seconds": settings.notifications.poll_interval_seconds,
    "delivery_poll_interval_seconds": settings.notifications.delivery_poll_interval_seconds,
    "retention_days": settings.notifications.retention_days,
    "subscriber_key": settings.notifications.subscriber_key,
    "token_flow_limit": settings.notifications.token_flow_limit,
    "channels": [
        {
            "key": key,
            "enabled": channel.enabled,
            "provider": channel.provider,
            "min_severity": channel.min_severity,
            "url_configured": bool(channel.url),
        }
        for key, channel in sorted(settings.notifications.channels.items())
    ],
},
```

- [ ] **Step 6: Run settings tests**

Run:

```bash
uv run pytest tests/test_settings.py tests/test_cli.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/gmgn_twitter_intel/settings.py src/gmgn_twitter_intel/cli.py tests/test_settings.py tests/test_cli.py
git commit -m "feat: add notification settings"
```

### Task 2: Add Notification Schema

**Files:**
- Modify: `src/gmgn_twitter_intel/storage/sqlite_schema.py`
- Modify: `src/gmgn_twitter_intel/storage/sqlite_client.py`
- Modify: `tests/test_sqlite_schema.py`

- [ ] **Step 1: Write schema tests**

In `test_sqlite_schema_bootstraps_core_tables`, add assertions:

```python
assert "notification_rules" in names
assert "notifications" in names
assert "notification_reads" in names
assert "notification_deliveries" in names
```

Change migration version assertion:

```python
assert [row["version"] for row in rows] == [12]
```

Add index/constraint test:

```python
def test_notification_schema_enforces_dedupe_key(tmp_path):
    db_path = tmp_path / "twitter_intel.sqlite3"
    conn = connect_sqlite(db_path, read_only=False)
    try:
        migrate(conn)
        now_ms = 1_700_000_000_000
        conn.execute(
            """
            INSERT INTO notification_rules(
              rule_id, name, description, source, enabled, severity, window,
              predicate_json, target_channels_json, cooldown_ms, created_at_ms, updated_at_ms
            )
            VALUES ('hot_quality_token_5m', 'Hot token', 'Hot token', 'token_flow', 1, 'high', '5m', '{}', '["in_app"]', 0, ?, ?)
            """,
            (now_ms, now_ms),
        )
        for notification_id in ("notification-1", "notification-2"):
            conn.execute(
                """
                INSERT INTO notifications(
                  notification_id, rule_id, dedupe_key, source, target_kind, target_id, target_label,
                  event_id, severity, title, body, action_url, payload_json, occurrence_count,
                  first_seen_at_ms, last_seen_at_ms, expires_at_ms, created_at_ms, updated_at_ms
                )
                VALUES (?, 'hot_quality_token_5m', 'same-dedupe', 'token_flow', 'token', 'token:eth:0x1', 'DOG',
                        NULL, 'high', 'DOG hot', 'body', NULL, '{}', 1, ?, ?, NULL, ?, ?)
                """,
                (notification_id, now_ms, now_ms, now_ms, now_ms),
            )
    except Exception as exc:
        error = exc
    finally:
        conn.close()

    assert type(error).__name__ == "IntegrityError"
```

- [ ] **Step 2: Run schema tests to verify failure**

```bash
uv run pytest tests/test_sqlite_schema.py -q
```

Expected: FAIL because tables/version do not exist.

- [ ] **Step 3: Bump schema and app tables**

In `sqlite_schema.py`:

```python
SCHEMA_VERSION = 12
```

Append to `APP_TABLES`:

```python
"notification_rules",
"notifications",
"notification_reads",
"notification_deliveries",
```

- [ ] **Step 4: Add SQL tables and indexes**

Append to `SCHEMA_SQL` before the closing triple quote:

```sql
CREATE TABLE IF NOT EXISTS notification_rules (
  rule_id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  description TEXT NOT NULL,
  source TEXT NOT NULL,
  enabled INTEGER NOT NULL DEFAULT 1,
  severity TEXT NOT NULL,
  window TEXT,
  predicate_json TEXT NOT NULL DEFAULT '{}',
  target_channels_json TEXT NOT NULL DEFAULT '["in_app"]',
  cooldown_ms INTEGER NOT NULL DEFAULT 0,
  created_at_ms INTEGER NOT NULL,
  updated_at_ms INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_notification_rules_source_enabled
  ON notification_rules(source, enabled);

CREATE TABLE IF NOT EXISTS notifications (
  notification_id TEXT PRIMARY KEY,
  rule_id TEXT NOT NULL REFERENCES notification_rules(rule_id) ON DELETE CASCADE,
  dedupe_key TEXT NOT NULL UNIQUE,
  source TEXT NOT NULL,
  target_kind TEXT NOT NULL,
  target_id TEXT NOT NULL,
  target_label TEXT NOT NULL,
  event_id TEXT,
  severity TEXT NOT NULL,
  title TEXT NOT NULL,
  body TEXT NOT NULL,
  action_url TEXT,
  payload_json TEXT NOT NULL DEFAULT '{}',
  occurrence_count INTEGER NOT NULL DEFAULT 1,
  first_seen_at_ms INTEGER NOT NULL,
  last_seen_at_ms INTEGER NOT NULL,
  expires_at_ms INTEGER,
  created_at_ms INTEGER NOT NULL,
  updated_at_ms INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_notifications_created
  ON notifications(created_at_ms DESC);
CREATE INDEX IF NOT EXISTS idx_notifications_target
  ON notifications(target_kind, target_id, created_at_ms DESC);
CREATE INDEX IF NOT EXISTS idx_notifications_rule_created
  ON notifications(rule_id, created_at_ms DESC);
CREATE INDEX IF NOT EXISTS idx_notifications_event
  ON notifications(event_id);

CREATE TABLE IF NOT EXISTS notification_reads (
  subscriber_key TEXT NOT NULL,
  notification_id TEXT NOT NULL REFERENCES notifications(notification_id) ON DELETE CASCADE,
  read_at_ms INTEGER,
  dismissed_at_ms INTEGER,
  created_at_ms INTEGER NOT NULL,
  updated_at_ms INTEGER NOT NULL,
  PRIMARY KEY(subscriber_key, notification_id)
);

CREATE INDEX IF NOT EXISTS idx_notification_reads_notification
  ON notification_reads(notification_id);

CREATE TABLE IF NOT EXISTS notification_deliveries (
  delivery_id TEXT PRIMARY KEY,
  notification_id TEXT NOT NULL REFERENCES notifications(notification_id) ON DELETE CASCADE,
  channel_key TEXT NOT NULL,
  provider TEXT NOT NULL,
  status TEXT NOT NULL,
  attempt_count INTEGER NOT NULL DEFAULT 0,
  max_attempts INTEGER NOT NULL DEFAULT 5,
  next_run_at_ms INTEGER NOT NULL,
  last_error TEXT,
  response_json TEXT,
  created_at_ms INTEGER NOT NULL,
  updated_at_ms INTEGER NOT NULL,
  UNIQUE(notification_id, channel_key)
);

CREATE INDEX IF NOT EXISTS idx_notification_deliveries_status_next
  ON notification_deliveries(status, next_run_at_ms);
CREATE INDEX IF NOT EXISTS idx_notification_deliveries_notification
  ON notification_deliveries(notification_id);
```

- [ ] **Step 5: Update migration label and health probes**

In `migrate()`, change migration name:

```python
(SCHEMA_VERSION, "production_notifications", _now_ms()),
```

In `sqlite_client.py`, append probes:

```python
("notification_rules", "SELECT rule_id FROM notification_rules LIMIT 1"),
("notifications", "SELECT notification_id FROM notifications ORDER BY created_at_ms DESC LIMIT 1"),
("notification_deliveries", "SELECT delivery_id FROM notification_deliveries ORDER BY updated_at_ms DESC LIMIT 1"),
```

- [ ] **Step 6: Run schema tests**

```bash
uv run pytest tests/test_sqlite_schema.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/gmgn_twitter_intel/storage/sqlite_schema.py src/gmgn_twitter_intel/storage/sqlite_client.py tests/test_sqlite_schema.py
git commit -m "feat: add notification schema"
```

### Task 3: Implement Notification Repository

**Files:**
- Create: `src/gmgn_twitter_intel/pipeline/notification_models.py`
- Create: `src/gmgn_twitter_intel/storage/notification_repository.py`
- Create: `tests/test_notification_repository.py`

- [ ] **Step 1: Write repository tests**

Create `tests/test_notification_repository.py`:

```python
from gmgn_twitter_intel.pipeline.notification_models import NotificationInput
from gmgn_twitter_intel.storage.notification_repository import NotificationRepository
from gmgn_twitter_intel.storage.sqlite_client import connect_sqlite
from gmgn_twitter_intel.storage.sqlite_schema import migrate


def open_repo(tmp_path):
    conn = connect_sqlite(tmp_path / "twitter_intel.sqlite3", read_only=False)
    migrate(conn)
    repo = NotificationRepository(conn)
    repo.ensure_default_rules()
    return conn, repo


def notification_input(**overrides):
    data = {
        "rule_id": "watched_account_activity",
        "dedupe_key": "watched_account_activity:toly:event-1",
        "source": "event",
        "target_kind": "account",
        "target_id": "toly",
        "target_label": "@toly",
        "event_id": "event-1",
        "severity": "info",
        "title": "@toly posted",
        "body": "watched account activity",
        "action_url": "/app?q=%40toly",
        "payload": {"handle": "toly"},
        "created_at_ms": 1_700_000_000_000,
    }
    data.update(overrides)
    return NotificationInput(**data)


def test_insert_notification_is_idempotent_by_dedupe_key(tmp_path):
    conn, repo = open_repo(tmp_path)
    try:
        first = repo.insert_notification(notification_input())
        second = repo.insert_notification(notification_input(title="@toly posted again"))
        rows = repo.list_notifications(subscriber_key="local", status="all", kind=None, limit=10)["items"]
    finally:
        conn.close()

    assert first is not None
    assert second is None
    assert len(rows) == 1
    assert rows[0]["occurrence_count"] == 2


def test_summary_counts_unread_watchlist_notifications(tmp_path):
    conn, repo = open_repo(tmp_path)
    try:
        repo.insert_notification(notification_input())
        summary = repo.summary(subscriber_key="local", window_ms=3_600_000, now_ms=1_700_000_100_000)
    finally:
        conn.close()

    assert summary["unread_total"] == 1
    assert summary["by_kind"]["account"] == 1
    assert summary["watchlist"] == [{"handle": "toly", "unread_count": 1, "latest_at_ms": 1_700_000_000_000}]


def test_mark_read_removes_unread_count(tmp_path):
    conn, repo = open_repo(tmp_path)
    try:
        inserted = repo.insert_notification(notification_input())
        assert inserted is not None
        assert repo.mark_read(subscriber_key="local", notification_id=inserted["notification_id"], now_ms=1_700_000_010_000)
        summary = repo.summary(subscriber_key="local", window_ms=3_600_000, now_ms=1_700_000_100_000)
    finally:
        conn.close()

    assert summary["unread_total"] == 0
```

- [ ] **Step 2: Run repository tests to verify failure**

```bash
uv run pytest tests/test_notification_repository.py -q
```

Expected: FAIL because repository and models do not exist.

- [ ] **Step 3: Add notification model dataclasses**

Create `pipeline/notification_models.py`:

```python
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class NotificationInput:
    rule_id: str
    dedupe_key: str
    source: str
    target_kind: str
    target_id: str
    target_label: str
    event_id: str | None
    severity: str
    title: str
    body: str
    action_url: str | None
    payload: dict[str, Any] = field(default_factory=dict)
    created_at_ms: int = 0
    expires_at_ms: int | None = None


@dataclass(frozen=True, slots=True)
class DeliveryResult:
    ok: bool
    response: dict[str, Any] | None = None
    error: str | None = None
```

- [ ] **Step 4: Implement repository**

Create `storage/notification_repository.py` with:

```python
from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from typing import Any

from ..pipeline.notification_models import NotificationInput

DEFAULT_RULES = [
    {
        "rule_id": "watched_account_activity",
        "name": "Watched account activity",
        "description": "A configured watched account posted in the public GMGN stream.",
        "source": "event",
        "severity": "info",
        "window": "1h",
        "predicate": {},
        "channels": ["in_app"],
        "cooldown_ms": 0,
    },
    {
        "rule_id": "watched_account_token_alert",
        "name": "Watched account token alert",
        "description": "A watched account mentioned a token entity.",
        "source": "account_alert",
        "severity": "warning",
        "window": "24h",
        "predicate": {},
        "channels": ["in_app"],
        "cooldown_ms": 0,
    },
    {
        "rule_id": "hot_quality_token_5m",
        "name": "Hot quality token 5m",
        "description": "A token crossed social heat and quality thresholds in the 5m window.",
        "source": "token_flow",
        "severity": "high",
        "window": "5m",
        "predicate": {"social_heat_min": 80, "discussion_quality_min": 70, "suppress_chase_risk": True},
        "channels": ["in_app"],
        "cooldown_ms": 900_000,
    },
    {
        "rule_id": "quality_token_5m",
        "name": "Quality token 5m",
        "description": "A token crossed discussion quality threshold in the 5m window.",
        "source": "token_flow",
        "severity": "warning",
        "window": "5m",
        "predicate": {"social_heat_min": 65, "discussion_quality_min": 80},
        "channels": ["in_app"],
        "cooldown_ms": 900_000,
    },
    {
        "rule_id": "harness_snapshot_high_score",
        "name": "Harness snapshot high score",
        "description": "A harness snapshot crossed the high score threshold.",
        "source": "harness_snapshot",
        "severity": "high",
        "window": "1h",
        "predicate": {"combined_score_min": 0.8},
        "channels": ["in_app"],
        "cooldown_ms": 0,
    },
]


class NotificationRepository:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def ensure_default_rules(self, *, commit: bool = True) -> None:
        now_ms = _now_ms()
        for rule in DEFAULT_RULES:
            self.conn.execute(
                """
                INSERT INTO notification_rules(
                  rule_id, name, description, source, enabled, severity, window,
                  predicate_json, target_channels_json, cooldown_ms, created_at_ms, updated_at_ms
                )
                VALUES (?, ?, ?, ?, 1, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(rule_id) DO UPDATE SET
                  name = excluded.name,
                  description = excluded.description,
                  source = excluded.source,
                  severity = excluded.severity,
                  window = excluded.window,
                  predicate_json = excluded.predicate_json,
                  target_channels_json = excluded.target_channels_json,
                  cooldown_ms = excluded.cooldown_ms,
                  updated_at_ms = excluded.updated_at_ms
                """,
                (
                    rule["rule_id"],
                    rule["name"],
                    rule["description"],
                    rule["source"],
                    rule["severity"],
                    rule["window"],
                    _json(rule["predicate"]),
                    _json(rule["channels"]),
                    rule["cooldown_ms"],
                    now_ms,
                    now_ms,
                ),
            )
        if commit:
            self.conn.commit()
```

Continue the file with `insert_notification`, `list_notifications`, `summary`, `mark_read`, `mark_all_read`, and delivery helpers. Use this behavior:

```python
    def insert_notification(self, notification: NotificationInput, *, commit: bool = True) -> dict[str, Any] | None:
        now_ms = notification.created_at_ms or _now_ms()
        notification_id = _id("notification", notification.dedupe_key)
        try:
            self.conn.execute(
                """
                INSERT INTO notifications(
                  notification_id, rule_id, dedupe_key, source, target_kind, target_id, target_label,
                  event_id, severity, title, body, action_url, payload_json, occurrence_count,
                  first_seen_at_ms, last_seen_at_ms, expires_at_ms, created_at_ms, updated_at_ms
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?, ?)
                """,
                (
                    notification_id,
                    notification.rule_id,
                    notification.dedupe_key,
                    notification.source,
                    notification.target_kind,
                    notification.target_id,
                    notification.target_label,
                    notification.event_id,
                    notification.severity,
                    notification.title,
                    notification.body,
                    notification.action_url,
                    _json(notification.payload),
                    now_ms,
                    now_ms,
                    notification.expires_at_ms,
                    now_ms,
                    now_ms,
                ),
            )
        except sqlite3.IntegrityError:
            self.conn.execute(
                """
                UPDATE notifications
                SET occurrence_count = occurrence_count + 1,
                    last_seen_at_ms = ?,
                    updated_at_ms = ?
                WHERE dedupe_key = ?
                """,
                (now_ms, now_ms, notification.dedupe_key),
            )
            if commit:
                self.conn.commit()
            return None
        if commit:
            self.conn.commit()
        return self.notification_by_id(notification_id, subscriber_key="local")
```

`list_notifications()` must LEFT JOIN `notification_reads` and decode JSON:

```python
    def list_notifications(self, *, subscriber_key: str, status: str, kind: str | None, limit: int) -> dict[str, Any]:
        clauses = []
        params: list[Any] = [subscriber_key]
        if status == "unread":
            clauses.append("nr.read_at_ms IS NULL")
        elif status == "dismissed":
            clauses.append("nr.dismissed_at_ms IS NOT NULL")
        if kind:
            clauses.append("n.target_kind = ?")
            params.append(kind)
        where_clause = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = self.conn.execute(
            f"""
            SELECT n.*, nr.read_at_ms, nr.dismissed_at_ms
            FROM notifications n
            LEFT JOIN notification_reads nr
              ON nr.notification_id = n.notification_id
             AND nr.subscriber_key = ?
            {where_clause}
            ORDER BY n.created_at_ms DESC
            LIMIT ?
            """,
            (*params, max(0, int(limit))),
        ).fetchall()
        return {
            "subscriber_key": subscriber_key,
            "items": [self._decode_notification(dict(row)) for row in rows],
            "unread_count": self.unread_count(subscriber_key=subscriber_key),
        }
```

Use helper functions:

```python
def _now_ms() -> int:
    return int(time.time() * 1000)


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _id(namespace: str, *parts: str) -> str:
    payload = "|".join([namespace, *parts])
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]
    return f"{namespace}:{digest}"
```

- [ ] **Step 5: Run repository tests**

```bash
uv run pytest tests/test_notification_repository.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/gmgn_twitter_intel/pipeline/notification_models.py src/gmgn_twitter_intel/storage/notification_repository.py tests/test_notification_repository.py
git commit -m "feat: add notification repository"
```

### Task 4: Implement Rule Engine

**Files:**
- Create: `src/gmgn_twitter_intel/pipeline/notification_rules.py`
- Create: `tests/test_notification_rules.py`

- [ ] **Step 1: Write rule tests**

Create tests for the five default rules. Use existing test factories from `tests/test_api_http.py` and `tests/test_token_flow_social_heat_contract.py`.

Core assertions:

```python
def test_rule_engine_creates_watched_account_activity_notification(tmp_path):
    runtime = open_notification_runtime(tmp_path)
    try:
        event = make_event("event-toly-1", handle="toly", text="hello")
        runtime.ingest.ingest_event(event, is_watched=True)
        notifications = runtime.engine.evaluate_events(since_ms=0, now_ms=event.received_at_ms + 1)
    finally:
        runtime.close()

    assert [item.rule_id for item in notifications] == ["watched_account_activity"]
    assert notifications[0].dedupe_key == "watched_account_activity:toly:event-toly-1"
    assert notifications[0].target_kind == "account"
```

Add token score test:

```python
def test_rule_engine_creates_hot_quality_token_notification(tmp_path):
    runtime = open_notification_runtime(tmp_path)
    try:
        now_ms = 1_700_000_000_000
        for index, handle in enumerate(["seed", "amp1", "amp2", "amp3", "amp4"]):
            runtime.ingest.ingest_event(
                token_event(
                    f"event-dog-{index}",
                    received_at_ms=now_ms - (index + 1) * 20_000,
                    author_handle=handle,
                    text=f"$DOG 0xd0667d0618dc9b6d2a0a55f428b47c64bcf00416 mcap liquidity breakout {index}",
                ),
                is_watched=index == 0,
            )
        notifications = runtime.engine.evaluate_token_flow(window="5m", now_ms=now_ms)
    finally:
        runtime.close()

    assert any(item.rule_id == "hot_quality_token_5m" for item in notifications)
    hot = next(item for item in notifications if item.rule_id == "hot_quality_token_5m")
    assert hot.target_kind == "token"
    assert hot.payload["scores"]["social_heat"] >= 80
    assert hot.payload["scores"]["discussion_quality"] >= 70
```

Add chase-risk suppression:

```python
def test_rule_engine_suppresses_hot_token_when_chase_risk_is_true(tmp_path):
    runtime = open_notification_runtime(tmp_path)
    try:
        row = token_flow_item(score=88, quality=82, chase_risk=True)
        notifications = runtime.engine.notifications_for_token_item(row, now_ms=1_700_000_000_000)
    finally:
        runtime.close()

    assert all(item.rule_id != "hot_quality_token_5m" for item in notifications)
```

- [ ] **Step 2: Run rule tests to verify failure**

```bash
uv run pytest tests/test_notification_rules.py -q
```

Expected: FAIL because rule engine does not exist.

- [ ] **Step 3: Implement rule engine**

Create `notification_rules.py`:

```python
from __future__ import annotations

import time
from typing import Any

from ..retrieval.token_flow_service import TokenFlowService
from .notification_models import NotificationInput

FIVE_MINUTES_MS = 5 * 60_000


class NotificationRuleEngine:
    def __init__(self, *, evidence, signals, tokens, harness, settings):
        self.evidence = evidence
        self.signals = signals
        self.tokens = tokens
        self.harness = harness
        self.settings = settings

    def evaluate_events(self, *, since_ms: int, now_ms: int | None = None) -> list[NotificationInput]:
        now = now_ms if now_ms is not None else _now_ms()
        rows = self.evidence.recent_events(limit=500, watched_only=True)
        notifications = []
        handles = set(self.settings.handles)
        for event in rows:
            received_at_ms = int(event.get("received_at_ms") or 0)
            handle = str(event.get("author_handle") or "").lower()
            if received_at_ms < since_ms or not handle or handle not in handles:
                continue
            notifications.append(
                NotificationInput(
                    rule_id="watched_account_activity",
                    dedupe_key=f"watched_account_activity:{handle}:{event['event_id']}",
                    source="event",
                    target_kind="account",
                    target_id=handle,
                    target_label=f"@{handle}",
                    event_id=str(event["event_id"]),
                    severity="info",
                    title=f"@{handle} posted",
                    body=str(event.get("text_clean") or event.get("text") or "watched account activity")[:280],
                    action_url=f"/app?q=%40{handle}",
                    payload={"handle": handle, "event_id": event["event_id"]},
                    created_at_ms=received_at_ms or now,
                )
            )
        return notifications
```

Add `evaluate_account_alerts()` using `self.signals.account_alerts(window_ms=..., now_ms=..., limit=500, handles=set(self.settings.handles))`. Build dedupe:

```python
dedupe_key=f"watched_account_token_alert:{alert['event_id']}:{alert['entity_key']}"
```

Add `evaluate_token_flow()`:

```python
    def evaluate_token_flow(self, *, window: str, now_ms: int | None = None) -> list[NotificationInput]:
        now = now_ms if now_ms is not None else _now_ms()
        items = TokenFlowService(signals=self.signals, tokens=self.tokens, harness=self.harness).token_flow(
            window=window,
            limit=self.settings.notifications.token_flow_limit,
            scope="all",
            now_ms=now,
        )
        notifications = []
        for item in items:
            notifications.extend(self.notifications_for_token_item(item, now_ms=now))
        return notifications
```

Add `notifications_for_token_item()` with these predicates:

```python
heat = int(item["social_heat"]["score"])
quality = int(item["discussion_quality"]["score"])
opportunity = int(item["opportunity"]["score"])
chase_risk = bool(item["timing"]["chase_risk"])
identity = item["identity"]
token_id = identity.get("token_id") or identity["identity_key"]
symbol = identity.get("symbol") or token_id
bucket = _bucket_ms(now_ms, FIVE_MINUTES_MS)
score_versions = "+".join(
    [
        item["social_heat"]["score_version"],
        item["discussion_quality"]["score_version"],
        item["opportunity"]["score_version"],
    ]
)
```

Create `hot_quality_token_5m` when `heat >= 80`, `quality >= 70`, and not `chase_risk`. Create `quality_token_5m` when `quality >= 80` and `heat >= 65`.

Add `evaluate_harness_snapshots()` by querying `self.harness.list_snapshots(window_ms=..., limit=500, now_ms=now, horizon="6h")` and emitting for `combined_score >= 0.8`.

- [ ] **Step 4: Run rule tests**

```bash
uv run pytest tests/test_notification_rules.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/gmgn_twitter_intel/pipeline/notification_rules.py tests/test_notification_rules.py
git commit -m "feat: add notification rule engine"
```

### Task 5: Add Notification Worker and Runtime Wiring

**Files:**
- Create: `src/gmgn_twitter_intel/pipeline/notification_worker.py`
- Modify: `src/gmgn_twitter_intel/api/app.py`
- Create: `tests/test_notification_worker.py`

- [ ] **Step 1: Write worker test**

Create:

```python
def test_notification_worker_materializes_and_publishes_new_notifications(tmp_path):
    publisher = RecordingPublisher()
    runtime = open_notification_runtime(tmp_path, publisher=publisher)
    try:
        event = make_event("event-toly-1", handle="toly", text="watched post", received_at_ms=1_700_000_000_000)
        runtime.ingest.ingest_event(event, is_watched=True)
        processed = runtime.worker.run_once(now_ms=1_700_000_000_100)
        rows = runtime.notifications.list_notifications(subscriber_key="local", status="all", kind=None, limit=10)["items"]
    finally:
        runtime.close()

    assert processed >= 1
    assert rows[0]["rule_id"] == "watched_account_activity"
    assert publisher.messages[0]["type"] == "notification"
```

`RecordingPublisher`:

```python
class RecordingPublisher:
    def __init__(self):
        self.messages = []

    async def publish(self, payload):
        self.messages.append(payload)
```

- [ ] **Step 2: Run worker test to verify failure**

```bash
uv run pytest tests/test_notification_worker.py -q
```

Expected: FAIL because worker/runtime are not wired.

- [ ] **Step 3: Implement worker**

Create `notification_worker.py`:

```python
from __future__ import annotations

import asyncio
import time
from threading import RLock
from typing import Any

from loguru import logger

from ..storage.sqlite_client import transaction
from .notification_rules import NotificationRuleEngine


class NotificationWorker:
    def __init__(
        self,
        *,
        engine: NotificationRuleEngine,
        notifications,
        publisher=None,
        write_lock: RLock | None = None,
        poll_interval: float = 5.0,
    ):
        self.engine = engine
        self.notifications = notifications
        self.publisher = publisher
        self.write_lock = write_lock or RLock()
        self.poll_interval = poll_interval
        self._stopped = False

    async def run(self) -> None:
        while not self._stopped:
            try:
                await asyncio.to_thread(self.run_once)
            except Exception as exc:
                logger.exception(f"notification worker failed: {exc}")
            await asyncio.sleep(self.poll_interval)

    def stop(self) -> None:
        self._stopped = True

    def run_once(self, *, now_ms: int | None = None) -> int:
        now = now_ms if now_ms is not None else _now_ms()
        since_ms = max(0, now - 24 * 60 * 60_000)
        candidates = []
        candidates.extend(self.engine.evaluate_events(since_ms=since_ms, now_ms=now))
        candidates.extend(self.engine.evaluate_account_alerts(since_ms=since_ms, now_ms=now))
        candidates.extend(self.engine.evaluate_token_flow(window="5m", now_ms=now))
        candidates.extend(self.engine.evaluate_harness_snapshots(since_ms=since_ms, now_ms=now))
        created = []
        with self.write_lock, transaction(self.notifications.conn):
            self.notifications.ensure_default_rules(commit=False)
            for candidate in candidates:
                row = self.notifications.insert_notification(candidate, commit=False)
                if row is not None:
                    created.append(row)
        if self.publisher is not None:
            for row in created:
                _publish_sync(self.publisher, {"type": "notification", "notification": row})
        return len(created)


def _publish_sync(publisher: Any, payload: dict[str, Any]) -> None:
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        asyncio.run(publisher.publish(payload))
        return
    loop.create_task(publisher.publish(payload))


def _now_ms() -> int:
    return int(time.time() * 1000)
```

- [ ] **Step 4: Wire runtime**

In `api/app.py`:

- Import `NotificationRuleEngine`, `NotificationWorker`, `NotificationRepository`.
- Add to `CliRuntime`:

```python
notifications: NotificationRepository
read_notifications: NotificationRepository
notification_worker: NotificationWorker | None = None
notification_task: asyncio.Task | None = None
```

- Build repositories:

```python
notifications = NotificationRepository(conn)
read_notifications = NotificationRepository(read_conn)
notifications.ensure_default_rules()
```

- Build worker if enabled:

```python
if settings.notifications.enabled:
    runtime.notification_worker = NotificationWorker(
        engine=NotificationRuleEngine(
            evidence=evidence,
            signals=signals,
            tokens=tokens,
            harness=harness,
            settings=settings,
        ),
        notifications=notifications,
        publisher=hub,
        write_lock=write_lock,
        poll_interval=settings.notifications.poll_interval_seconds,
    )
```

- Start task in `_start_runtime_tasks()`:

```python
if runtime.notification_worker is not None and runtime.notification_task is None:
    runtime.notification_task = asyncio.create_task(runtime.notification_worker.run())
```

- Stop task in `_stop_runtime()`:

```python
if runtime.notification_worker is not None:
    runtime.notification_worker.stop()
```

Add `runtime.notification_task` to cancelled task list.

- [ ] **Step 5: Run worker tests**

```bash
uv run pytest tests/test_notification_worker.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/gmgn_twitter_intel/pipeline/notification_worker.py src/gmgn_twitter_intel/api/app.py tests/test_notification_worker.py
git commit -m "feat: run notification worker"
```

### Task 6: Add Notification HTTP APIs

**Files:**
- Modify: `src/gmgn_twitter_intel/api/http.py`
- Modify: `tests/test_api_http.py`

- [ ] **Step 1: Write API tests**

Add:

```python
def test_api_exposes_notifications_and_summary(tmp_path):
    app = create_app(settings=make_settings(tmp_path), start_collector=False)
    with TestClient(app) as client:
        event = make_event("event-notify", "toly", text="watched notification")
        client.app.state.service.ingest.ingest_event(event, is_watched=True)
        client.app.state.service.notification_worker.run_once(now_ms=event.received_at_ms + 1)

        headers = {"Authorization": "Bearer secret"}
        notifications = client.get("/api/notifications?status=unread&limit=10", headers=headers)
        summary = client.get("/api/notification-summary?window=1h", headers=headers)

    assert notifications.status_code == 200
    assert notifications.json()["data"]["items"][0]["rule_id"] == "watched_account_activity"
    assert summary.status_code == 200
    assert summary.json()["data"]["unread_total"] == 1
    assert summary.json()["data"]["watchlist"][0]["handle"] == "toly"
```

Add mark-read test:

```python
def test_api_marks_notification_read(tmp_path):
    app = create_app(settings=make_settings(tmp_path), start_collector=False)
    with TestClient(app) as client:
        event = make_event("event-read", "toly", text="read me")
        client.app.state.service.ingest.ingest_event(event, is_watched=True)
        client.app.state.service.notification_worker.run_once(now_ms=event.received_at_ms + 1)
        headers = {"Authorization": "Bearer secret"}
        item = client.get("/api/notifications?status=unread&limit=10", headers=headers).json()["data"]["items"][0]
        response = client.post(f"/api/notifications/{item['notification_id']}/read", headers=headers)
        summary = client.get("/api/notification-summary?window=1h", headers=headers)

    assert response.status_code == 200
    assert response.json()["data"]["read"] is True
    assert summary.json()["data"]["unread_total"] == 0
```

- [ ] **Step 2: Run API tests to verify failure**

```bash
uv run pytest tests/test_api_http.py -q
```

Expected: FAIL for missing endpoints.

- [ ] **Step 3: Add API endpoints**

In `create_api_router()` add:

```python
    @router.get("/notifications")
    async def notifications(
        request: Request,
        status: Annotated[str, Query()] = "unread",
        kind: Annotated[str, Query()] = "",
        limit: Annotated[int, Query()] = 50,
    ) -> JSONResponse:
        runtime = _authenticated_runtime(request)
        parsed_status = status if status in {"unread", "all", "dismissed"} else "unread"
        parsed_kind = kind if kind in {"account", "token", "harness_snapshot", "event", "system"} else None
        data = runtime.read_notifications.list_notifications(
            subscriber_key=runtime.settings.notifications.subscriber_key,
            status=parsed_status,
            kind=parsed_kind,
            limit=_limit(limit, maximum=500),
        )
        return _json({"ok": True, "data": data})

    @router.get("/notification-summary")
    async def notification_summary(
        request: Request,
        window: Annotated[str, Query()] = "1h",
    ) -> JSONResponse:
        runtime = _authenticated_runtime(request)
        data = runtime.read_notifications.summary(
            subscriber_key=runtime.settings.notifications.subscriber_key,
            window_ms=_window_ms(_window(window)),
        )
        data["window"] = window
        return _json({"ok": True, "data": data})

    @router.post("/notifications/{notification_id}/read")
    async def mark_notification_read(request: Request, notification_id: str) -> JSONResponse:
        runtime = _authenticated_runtime(request)
        read = runtime.notifications.mark_read(
            subscriber_key=runtime.settings.notifications.subscriber_key,
            notification_id=notification_id,
            now_ms=_now_ms(),
        )
        return _json({"ok": True, "data": {"read": read}})

    @router.post("/notifications/read-all")
    async def mark_all_notifications_read(request: Request) -> JSONResponse:
        runtime = _authenticated_runtime(request)
        body = await request.json() if request.headers.get("content-type", "").startswith("application/json") else {}
        kind = body.get("kind") if isinstance(body, dict) else None
        before_ms = int(body.get("before_ms") or _now_ms()) if isinstance(body, dict) else _now_ms()
        count = runtime.notifications.mark_all_read(
            subscriber_key=runtime.settings.notifications.subscriber_key,
            before_ms=before_ms,
            kind=kind if kind in {"account", "token", "harness_snapshot", "event", "system"} else None,
        )
        return _json({"ok": True, "data": {"read_count": count}})
```

Add helpers:

```python
WINDOW_MS = {"5m": 5 * 60_000, "1h": 60 * 60_000, "4h": 4 * 60 * 60_000, "24h": 24 * 60 * 60_000}

def _window_ms(window: str) -> int:
    return WINDOW_MS[window]

def _now_ms() -> int:
    import time
    return int(time.time() * 1000)
```

- [ ] **Step 4: Run API tests**

```bash
uv run pytest tests/test_api_http.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/gmgn_twitter_intel/api/http.py tests/test_api_http.py
git commit -m "feat: expose notification api"
```

### Task 7: Add WebSocket Notification Routing

**Files:**
- Modify: `src/gmgn_twitter_intel/api/ws.py`
- Modify: `tests/test_api_websocket.py`
- Modify: `web/src/api/useIntelSocket.ts`

- [ ] **Step 1: Write backend WebSocket tests**

Add:

```python
def test_websocket_notification_subscription_receives_live_notifications(tmp_path):
    app = create_app(settings=make_settings(tmp_path), start_collector=False)
    with TestClient(app) as client:
        event = make_event("event-notification-ws", "toly", text="ws notification")
        client.app.state.service.ingest.ingest_event(event, is_watched=True)

        with client.websocket_connect("/ws") as ws:
            ws.send_json({"type": "auth", "token": "secret"})
            assert ws.receive_json()["type"] == "ready"
            ws.send_json({"type": "subscribe", "handles": ["toly"], "replay": 0, "notifications": True})
            client.app.state.service.notification_worker.run_once(now_ms=event.received_at_ms + 1)
            payload = ws.receive_json()

    assert payload["type"] == "notification"
    assert payload["notification"]["rule_id"] == "watched_account_activity"


def test_websocket_without_notification_subscription_does_not_receive_notifications(tmp_path):
    app = create_app(settings=make_settings(tmp_path), start_collector=False)
    with TestClient(app) as client:
        with client.websocket_connect("/ws") as ws:
            ws.send_json({"type": "auth", "token": "secret"})
            assert ws.receive_json()["type"] == "ready"
            ws.send_json({"type": "subscribe", "handles": ["toly"], "replay": 0})
            assert client.app.state.service.hub._payload_matches_subscription(
                {"type": "notification", "notification": {"target_kind": "account", "target_id": "toly"}},
                next(iter(client.app.state.service.hub._clients)),
            ) is False
```

- [ ] **Step 2: Run WebSocket tests to verify failure**

```bash
uv run pytest tests/test_api_websocket.py -q
```

Expected: FAIL for missing subscription field.

- [ ] **Step 3: Update backend WebSocket hub**

In `ClientSubscription`:

```python
notifications: bool = False
```

In `_handle_client_message()`:

```python
client.notifications = bool(message.get("notifications"))
```

At top of `_payload_matches_subscription()`:

```python
if payload.get("type") == "notification":
    return client.notifications
```

This deliberately broadcasts all local notifications to subscribed clients. Phase 1 has one local subscriber and Bearer token auth, so per-handle notification filtering is unnecessary.

- [ ] **Step 4: Update frontend socket hook**

Change `useIntelSocket` return state:

```ts
const [notifications, setNotifications] = useState<NotificationPayload[]>([]);
```

Send subscribe:

```ts
ws.send(
  JSON.stringify({
    type: "subscribe",
    handles: normalizeHandles(handles),
    replay,
    notifications: true
  })
);
```

Handle payload:

```ts
if (payload.type === "notification") {
  setNotifications((current) => [payload as NotificationPayload, ...current].slice(0, 100));
  return;
}
```

Return:

```ts
return { status, events, notifications, lastMessageAt };
```

- [ ] **Step 5: Run backend WebSocket tests**

```bash
uv run pytest tests/test_api_websocket.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/gmgn_twitter_intel/api/ws.py tests/test_api_websocket.py web/src/api/useIntelSocket.ts
git commit -m "feat: stream notifications over websocket"
```

### Task 8: Add Frontend Notification Types and API Helpers

**Files:**
- Modify: `web/src/api/types.ts`
- Create: `web/src/api/notifications.ts`

- [ ] **Step 1: Add TypeScript types**

In `types.ts`:

```ts
export type NotificationSeverity = "info" | "warning" | "high" | "critical";
export type NotificationKind = "account" | "token" | "harness_snapshot" | "event" | "system";
export type NotificationStatus = "unread" | "all" | "dismissed";

export type NotificationRecord = {
  notification_id: string;
  rule_id: string;
  dedupe_key: string;
  source: string;
  target_kind: NotificationKind;
  target_id: string;
  target_label: string;
  event_id?: string | null;
  severity: NotificationSeverity;
  title: string;
  body: string;
  action_url?: string | null;
  payload: Record<string, unknown>;
  occurrence_count: number;
  first_seen_at_ms: number;
  last_seen_at_ms: number;
  created_at_ms: number;
  updated_at_ms: number;
  read_at_ms?: number | null;
  dismissed_at_ms?: number | null;
};

export type NotificationsData = {
  subscriber_key: string;
  items: NotificationRecord[];
  unread_count: number;
};

export type NotificationSummaryData = {
  window: WindowKey;
  unread_total: number;
  highest_severity?: NotificationSeverity | null;
  by_kind: Partial<Record<NotificationKind, number>>;
  watchlist: Array<{ handle: string; unread_count: number; latest_at_ms: number }>;
};

export type NotificationPayload = {
  type: "notification";
  notification: NotificationRecord;
};
```

- [ ] **Step 2: Add API helper module**

Create `web/src/api/notifications.ts`:

```ts
import { getApi } from "./client";
import type { ApiResponse, NotificationKind, NotificationsData, NotificationStatus, NotificationSummaryData, WindowKey } from "./types";

export function getNotifications({
  token,
  status,
  kind,
  limit = 50
}: {
  token: string;
  status: NotificationStatus;
  kind?: NotificationKind | "all";
  limit?: number;
}): Promise<ApiResponse<NotificationsData>> {
  return getApi<NotificationsData>("/api/notifications", {
    token,
    params: {
      status,
      kind: kind && kind !== "all" ? kind : undefined,
      limit
    }
  });
}

export function getNotificationSummary({
  token,
  window
}: {
  token: string;
  window: WindowKey;
}): Promise<ApiResponse<NotificationSummaryData>> {
  return getApi<NotificationSummaryData>("/api/notification-summary", {
    token,
    params: { window }
  });
}

export function markNotificationRead({ token, notificationId }: { token: string; notificationId: string }) {
  return getApi<{ read: boolean }>(`/api/notifications/${encodeURIComponent(notificationId)}/read`, {
    token,
    method: "POST"
  });
}
```

If `getApi` does not support `method`, extend `web/src/api/client.ts` with an optional `method?: "GET" | "POST"` and body-safe fetch options.

- [ ] **Step 3: Run frontend typecheck**

```bash
cd web && npm run typecheck
```

Expected: PASS after `getApi` method support is added if needed.

- [ ] **Step 4: Commit**

```bash
git add web/src/api/types.ts web/src/api/notifications.ts web/src/api/client.ts
git commit -m "feat: add notification api types"
```

### Task 9: Add Frontend Bell, Drawer, Red Dots, and Toast Bridge

**Files:**
- Modify: `web/package.json`
- Modify: `web/package-lock.json`
- Modify: `web/src/App.tsx`
- Modify: `web/src/styles.css`
- Create: `web/src/components/NotificationBell.tsx`
- Create: `web/src/components/NotificationDrawer.tsx`
- Create: `web/src/components/WatchlistNotificationDot.tsx`
- Create: `web/src/components/NotificationToastBridge.tsx`
- Create: `web/src/components/NotificationCenter.test.tsx`

- [ ] **Step 1: Install Sonner**

```bash
cd web && npm install sonner@^2.0.7
```

Expected: `web/package.json` and `web/package-lock.json` update.

- [ ] **Step 2: Write frontend tests**

Create tests that mock `getApi` and render `App`:

```tsx
it("renders notification bell and watchlist unread dot", async () => {
  mockApi({
    "/api/bootstrap": { ws_token: "secret", handles: ["toly"], replay_limit: 25 },
    "/api/notification-summary": {
      window: "1h",
      unread_total: 2,
      highest_severity: "high",
      by_kind: { account: 1, token: 1 },
      watchlist: [{ handle: "toly", unread_count: 1, latest_at_ms: 1_700_000_000_000 }]
    },
    "/api/notifications": {
      subscriber_key: "local",
      unread_count: 2,
      items: [
        {
          notification_id: "notification-1",
          rule_id: "watched_account_activity",
          dedupe_key: "d1",
          source: "event",
          target_kind: "account",
          target_id: "toly",
          target_label: "@toly",
          severity: "info",
          title: "@toly posted",
          body: "watched post",
          payload: { handle: "toly" },
          occurrence_count: 1,
          first_seen_at_ms: 1_700_000_000_000,
          last_seen_at_ms: 1_700_000_000_000,
          created_at_ms: 1_700_000_000_000,
          updated_at_ms: 1_700_000_000_000,
          read_at_ms: null,
          dismissed_at_ms: null
        }
      ]
    }
  });

  render(<App />);

  expect(await screen.findByLabelText("notifications")).toHaveTextContent("2");
  expect(await screen.findByLabelText("@toly unread notifications")).toHaveTextContent("1");
});
```

- [ ] **Step 3: Create `NotificationBell`**

Component props:

```ts
type NotificationBellProps = {
  unreadTotal: number;
  highestSeverity?: NotificationSeverity | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
};
```

Render a lucide `Bell` icon button with `aria-label="notifications"`, count badge, and severity class.

- [ ] **Step 4: Create `NotificationDrawer`**

Props:

```ts
type NotificationDrawerProps = {
  open: boolean;
  isLoading: boolean;
  items: NotificationRecord[];
  filter: NotificationStatus;
  onFilterChange: (filter: NotificationStatus) => void;
  onClose: () => void;
  onSelect: (notification: NotificationRecord) => void;
  onMarkRead: (notification: NotificationRecord) => void;
};
```

Render:

- title row with unread count;
- segmented buttons `Unread`, `All`;
- list of notifications;
- severity chip;
- title/body;
- relative time using existing `formatRelativeTime`.

- [ ] **Step 5: Create `WatchlistNotificationDot`**

Props:

```ts
type WatchlistNotificationDotProps = {
  handle: string;
  summary?: NotificationSummaryData;
};
```

Find watchlist count by lowercased handle. If count > 0 render:

```tsx
<span className="watchlist-notification-dot" aria-label={`@${handle} unread notifications`}>
  {count > 9 ? "9+" : count}
</span>
```

- [ ] **Step 6: Create `NotificationToastBridge`**

Use `sonner`:

```tsx
import { toast, Toaster } from "sonner";

export function NotificationToastBridge({ notifications, onSelect }: Props) {
  const seenRef = useRef(new Set<string>());
  useEffect(() => {
    for (const payload of notifications) {
      const item = payload.notification;
      if (seenRef.current.has(item.notification_id)) continue;
      seenRef.current.add(item.notification_id);
      if (item.severity === "warning" || item.severity === "high" || item.severity === "critical") {
        toast(item.title, {
          description: item.body,
          action: { label: "Open", onClick: () => onSelect(item) }
        });
      }
    }
  }, [notifications, onSelect]);
  return <Toaster position="top-right" richColors closeButton />;
}
```

- [ ] **Step 7: Wire App queries and mutations**

In `App.tsx`:

- Add `notificationDrawerOpen` and `notificationFilter` local state.
- Add summary query:

```ts
const notificationSummaryQuery = useQuery({
  queryKey: ["notification-summary", "1h"],
  queryFn: () => getNotificationSummary({ token, window: "1h" }),
  enabled: Boolean(token),
  refetchInterval: 10_000
});
```

- Add notifications query:

```ts
const notificationsQuery = useQuery({
  queryKey: ["notifications", notificationFilter],
  queryFn: () => getNotifications({ token, status: notificationFilter, limit: 80 }),
  enabled: Boolean(token && notificationDrawerOpen)
});
```

- On socket notifications:

```ts
useEffect(() => {
  if (!socket.notifications.length) return;
  void queryClient.invalidateQueries({ queryKey: ["notification-summary"] });
  void queryClient.invalidateQueries({ queryKey: ["notifications"] });
}, [queryClient, socket.notifications]);
```

- Add `NotificationBell` next to refresh button.
- Add `NotificationDrawer` near end of `<main>`.
- Add `NotificationToastBridge`.
- Add `WatchlistNotificationDot` inside watchlist button.

- [ ] **Step 8: Add styles**

Add CSS classes:

```css
.notification-bell {
  position: relative;
}

.notification-badge {
  min-width: 18px;
  height: 18px;
  border-radius: 999px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 11px;
  font-weight: 700;
}

.notification-drawer {
  position: fixed;
  top: 0;
  right: 0;
  width: min(420px, 100vw);
  height: 100dvh;
  z-index: 40;
}

.watchlist-notification-dot {
  margin-left: auto;
  min-width: 16px;
  height: 16px;
  border-radius: 999px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 10px;
  font-weight: 700;
}
```

Adapt colors to existing cockpit palette; do not introduce a new one-note theme.

- [ ] **Step 9: Run frontend tests and build**

```bash
cd web && npm test
cd web && npm run typecheck
cd web && npm run build
```

Expected: PASS.

- [ ] **Step 10: Commit**

```bash
git add web/package.json web/package-lock.json web/src/App.tsx web/src/styles.css web/src/components/NotificationBell.tsx web/src/components/NotificationDrawer.tsx web/src/components/WatchlistNotificationDot.tsx web/src/components/NotificationToastBridge.tsx web/src/components/NotificationCenter.test.tsx
git commit -m "feat: add in-app notification center"
```

### Task 10: Phase 1 Verification Gate

**Files:**
- Modify only if tests reveal a bug.

- [ ] **Step 1: Run Python verification**

```bash
uv run pytest
uv run ruff check .
uv run python -m compileall src tests
```

Expected: all pass.

- [ ] **Step 2: Run frontend verification**

```bash
cd web && npm test
cd web && npm run typecheck
cd web && npm run build
```

Expected: all pass.

- [ ] **Step 3: Manual runtime smoke**

Start service:

```bash
uv run gmgn-twitter-intel serve
```

Open:

```text
http://127.0.0.1:8765/app
```

Verify:

- Bell appears in topbar.
- Watchlist handles can show red dot after notifications exist.
- Drawer opens and mark-read clears count.
- Existing Token Radar, Live Tape, and Signal Lab still render.

- [ ] **Step 4: Commit fixes if needed**

If any verification command fails, fix the failing behavior and commit the minimal patch:

```bash
git add <changed-files>
git commit -m "fix: stabilize phase 1 notifications"
```

---

## Phase 2: External Delivery Through Apprise

### Task 11: Add Apprise Dependency and Delivery Settings Tests

**Files:**
- Modify: `pyproject.toml`
- Modify: `uv.lock`
- Modify: `tests/test_settings.py`

- [ ] **Step 1: Add dependency**

```bash
uv add "apprise>=1.10.0"
```

Expected: `pyproject.toml` includes `apprise>=1.10.0` and `uv.lock` updates.

- [ ] **Step 2: Extend settings tests**

Add assertion:

```python
assert settings.notifications.channels["pushdeer"].provider == "apprise"
assert settings.notifications.channels["pushdeer"].min_severity == "high"
assert settings.notifications.channels["pushdeer"].max_attempts == 5
```

- [ ] **Step 3: Run settings tests**

```bash
uv run pytest tests/test_settings.py -q
```

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml uv.lock tests/test_settings.py
git commit -m "feat: add apprise dependency"
```

### Task 12: Add Delivery Repository Methods

**Files:**
- Modify: `src/gmgn_twitter_intel/storage/notification_repository.py`
- Modify: `tests/test_notification_repository.py`

- [ ] **Step 1: Write delivery repository tests**

Add:

```python
def test_enqueue_and_claim_delivery(tmp_path):
    conn, repo = open_repo(tmp_path)
    try:
        inserted = repo.insert_notification(notification_input(severity="high"))
        assert inserted is not None
        count = repo.enqueue_deliveries(
            notification=inserted,
            channels=[{"key": "pushdeer", "provider": "apprise", "max_attempts": 5}],
            now_ms=1_700_000_000_000,
        )
        claimed = repo.claim_pending_delivery(now_ms=1_700_000_000_001)
    finally:
        conn.close()

    assert count == 1
    assert claimed["channel_key"] == "pushdeer"
    assert claimed["status"] == "running"
    assert claimed["attempt_count"] == 1


def test_fail_delivery_retries_then_marks_dead(tmp_path):
    conn, repo = open_repo(tmp_path)
    try:
        inserted = repo.insert_notification(notification_input(severity="high"))
        repo.enqueue_deliveries(
            notification=inserted,
            channels=[{"key": "pushdeer", "provider": "apprise", "max_attempts": 1}],
            now_ms=1_700_000_000_000,
        )
        claimed = repo.claim_pending_delivery(now_ms=1_700_000_000_001)
        repo.fail_delivery(delivery_id=claimed["delivery_id"], error="boom", now_ms=1_700_000_000_002)
        rows = repo.list_deliveries(limit=10, status=None)
    finally:
        conn.close()

    assert rows[0]["status"] == "dead"
    assert rows[0]["last_error"] == "boom"
```

- [ ] **Step 2: Run tests to verify failure**

```bash
uv run pytest tests/test_notification_repository.py -q
```

Expected: FAIL for missing delivery methods.

- [ ] **Step 3: Implement delivery methods**

Add to repository:

```python
    def enqueue_deliveries(self, *, notification: dict[str, Any], channels: list[dict[str, Any]], now_ms: int | None = None, commit: bool = True) -> int:
        now = now_ms if now_ms is not None else _now_ms()
        inserted = 0
        for channel in channels:
            delivery_id = _id("notification_delivery", notification["notification_id"], channel["key"])
            try:
                self.conn.execute(
                    """
                    INSERT INTO notification_deliveries(
                      delivery_id, notification_id, channel_key, provider, status, attempt_count,
                      max_attempts, next_run_at_ms, last_error, response_json, created_at_ms, updated_at_ms
                    )
                    VALUES (?, ?, ?, ?, 'pending', 0, ?, ?, NULL, NULL, ?, ?)
                    """,
                    (
                        delivery_id,
                        notification["notification_id"],
                        channel["key"],
                        channel["provider"],
                        int(channel.get("max_attempts") or 5),
                        now,
                        now,
                        now,
                    ),
                )
                inserted += 1
            except sqlite3.IntegrityError:
                continue
        if commit:
            self.conn.commit()
        return inserted
```

`claim_pending_delivery()` uses `BEGIN IMMEDIATE` caller lock when possible; inside method:

```python
row = self.conn.execute(
    """
    SELECT nd.*, n.title, n.body, n.severity, n.payload_json, n.target_label, n.action_url
    FROM notification_deliveries nd
    JOIN notifications n ON n.notification_id = nd.notification_id
    WHERE nd.status IN ('pending', 'failed')
      AND nd.next_run_at_ms <= ?
    ORDER BY nd.next_run_at_ms, nd.created_at_ms
    LIMIT 1
    """,
    (now_ms,),
).fetchone()
```

If row exists, update:

```sql
UPDATE notification_deliveries
SET status='running', attempt_count=attempt_count+1, updated_at_ms=?
WHERE delivery_id=?
```

`fail_delivery()`:

- If `attempt_count >= max_attempts`, status `dead`.
- Else status `failed`, `next_run_at_ms = now_ms + min(300000, 1000 * 2 ** attempt_count)`.

- [ ] **Step 4: Run repository tests**

```bash
uv run pytest tests/test_notification_repository.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/gmgn_twitter_intel/storage/notification_repository.py tests/test_notification_repository.py
git commit -m "feat: add notification delivery persistence"
```

### Task 13: Implement Apprise Delivery Worker

**Files:**
- Create: `src/gmgn_twitter_intel/pipeline/notification_delivery.py`
- Modify: `src/gmgn_twitter_intel/api/app.py`
- Create: `tests/test_notification_delivery.py`

- [ ] **Step 1: Write delivery tests with fake adapter**

Create:

```python
from gmgn_twitter_intel.pipeline.notification_delivery import NotificationDeliveryWorker
from gmgn_twitter_intel.pipeline.notification_models import DeliveryResult


class FakeAdapter:
    def __init__(self, result):
        self.result = result
        self.sent = []

    def send(self, *, channel, delivery):
        self.sent.append((channel, delivery))
        return self.result


def test_delivery_worker_marks_success(tmp_path):
    conn, repo = open_repo(tmp_path)
    try:
        inserted = repo.insert_notification(notification_input(severity="high"))
        repo.enqueue_deliveries(
            notification=inserted,
            channels=[{"key": "pushdeer", "provider": "apprise", "max_attempts": 5}],
            now_ms=1_700_000_000_000,
        )
        adapter = FakeAdapter(DeliveryResult(ok=True, response={"provider": "fake"}))
        worker = NotificationDeliveryWorker(
            notifications=repo,
            settings=delivery_settings("pushdeer://pushKey"),
            adapter=adapter,
        )
        assert worker.run_once(now_ms=1_700_000_000_001) == 1
        rows = repo.list_deliveries(limit=10, status=None)
    finally:
        conn.close()

    assert rows[0]["status"] == "sent"
    assert adapter.sent[0][0].url == "pushdeer://pushKey"
```

Add failure test for `DeliveryResult(ok=False, error="provider failed")`.

- [ ] **Step 2: Run tests to verify failure**

```bash
uv run pytest tests/test_notification_delivery.py -q
```

Expected: FAIL because worker does not exist.

- [ ] **Step 3: Implement delivery worker**

Create `notification_delivery.py`:

```python
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from threading import RLock
from typing import Any

from apprise import Apprise, NotifyFormat
from loguru import logger

from ..storage.sqlite_client import transaction
from .notification_models import DeliveryResult


@dataclass(frozen=True, slots=True)
class RuntimeNotificationChannel:
    key: str
    provider: str
    url: str
    min_severity: str
    max_attempts: int


class AppriseDeliveryAdapter:
    def send(self, *, channel: RuntimeNotificationChannel, delivery: dict[str, Any]) -> DeliveryResult:
        apobj = Apprise()
        if not apobj.add(channel.url):
            return DeliveryResult(ok=False, error="invalid_apprise_url")
        ok = apobj.notify(
            title=f"[GMGN] {delivery['severity'].upper()} {delivery['title']}",
            body=_delivery_body(delivery),
            body_format=NotifyFormat.MARKDOWN,
        )
        return DeliveryResult(ok=bool(ok), response={"provider": "apprise", "channel": channel.key} if ok else None, error=None if ok else "apprise_notify_failed")
```

Add worker:

```python
class NotificationDeliveryWorker:
    def __init__(self, *, notifications, settings, adapter=None, write_lock: RLock | None = None, poll_interval: float = 5.0):
        self.notifications = notifications
        self.settings = settings
        self.adapter = adapter or AppriseDeliveryAdapter()
        self.write_lock = write_lock or RLock()
        self.poll_interval = poll_interval
        self._stopped = False

    async def run(self) -> None:
        while not self._stopped:
            try:
                await asyncio.to_thread(self.run_once)
            except Exception as exc:
                logger.exception(f"notification delivery worker failed: {exc}")
            await asyncio.sleep(self.poll_interval)

    def stop(self) -> None:
        self._stopped = True

    def run_once(self, *, now_ms: int | None = None) -> int:
        now = now_ms if now_ms is not None else _now_ms()
        with self.write_lock, transaction(self.notifications.conn):
            delivery = self.notifications.claim_pending_delivery(now_ms=now)
        if delivery is None:
            return 0
        channel = self._channel_for_delivery(delivery)
        if channel is None:
            self.notifications.fail_delivery(delivery_id=delivery["delivery_id"], error="channel_not_configured", now_ms=now)
            return 1
        result = self.adapter.send(channel=channel, delivery=delivery)
        if result.ok:
            self.notifications.complete_delivery(delivery_id=delivery["delivery_id"], response=result.response)
        else:
            self.notifications.fail_delivery(delivery_id=delivery["delivery_id"], error=result.error or "delivery_failed", now_ms=now)
        return 1
```

`_channel_for_delivery()` reads `settings.notifications.channels[delivery["channel_key"]]`, requires enabled and url.

`_delivery_body()`:

```python
def _delivery_body(delivery: dict[str, Any]) -> str:
    lines = [delivery["body"]]
    if delivery.get("target_label"):
        lines.append(f"Target: `{delivery['target_label']}`")
    if delivery.get("action_url"):
        lines.append(f"Open: {delivery['action_url']}")
    return "\n\n".join(lines)
```

- [ ] **Step 4: Wire runtime**

In `api/app.py`, add `notification_delivery_worker` and `notification_delivery_task` to `CliRuntime`.

Build it only when at least one configured channel is enabled and not `in_app`:

```python
external_channels_enabled = any(channel.enabled for channel in settings.notifications.channels.values())
if settings.notifications.enabled and external_channels_enabled:
    runtime.notification_delivery_worker = NotificationDeliveryWorker(
        notifications=notifications,
        settings=settings,
        write_lock=write_lock,
        poll_interval=settings.notifications.delivery_poll_interval_seconds,
    )
```

Start/stop like other workers.

- [ ] **Step 5: Run delivery tests**

```bash
uv run pytest tests/test_notification_delivery.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/gmgn_twitter_intel/pipeline/notification_delivery.py src/gmgn_twitter_intel/api/app.py tests/test_notification_delivery.py
git commit -m "feat: deliver notifications via apprise"
```

### Task 14: Enqueue External Deliveries from Notification Worker

**Files:**
- Modify: `src/gmgn_twitter_intel/pipeline/notification_worker.py`
- Modify: `tests/test_notification_worker.py`

- [ ] **Step 1: Write enqueue test**

Add:

```python
def test_notification_worker_enqueues_external_delivery_for_high_severity(tmp_path):
    runtime = open_notification_runtime(
        tmp_path,
        notification_channels={
            "pushdeer": {"enabled": True, "provider": "apprise", "url": "pushdeer://pushKey", "min_severity": "high"}
        },
    )
    try:
        inserted = runtime.notifications.insert_notification(
            notification_input(rule_id="hot_quality_token_5m", severity="high", target_kind="token", target_id="token:eth:dog")
        )
        runtime.worker.enqueue_deliveries_for_notification(inserted)
        deliveries = runtime.notifications.list_deliveries(limit=10, status=None)
    finally:
        runtime.close()

    assert deliveries[0]["channel_key"] == "pushdeer"
    assert deliveries[0]["status"] == "pending"
```

- [ ] **Step 2: Implement severity/channel filtering**

In `NotificationWorker`, add:

```python
SEVERITY_RANK = {"info": 0, "warning": 1, "high": 2, "critical": 3}

def enabled_external_channels_for(self, notification: dict[str, Any]) -> list[dict[str, Any]]:
    channels = []
    severity_rank = SEVERITY_RANK.get(str(notification.get("severity")), 0)
    for key, channel in self.engine.settings.notifications.channels.items():
        if not channel.enabled:
            continue
        if SEVERITY_RANK.get(channel.min_severity, 1) > severity_rank:
            continue
        channels.append({"key": key, "provider": channel.provider, "max_attempts": channel.max_attempts})
    return channels
```

After `insert_notification()` returns a new row:

```python
channels = self.enabled_external_channels_for(row)
if channels:
    self.notifications.enqueue_deliveries(notification=row, channels=channels, now_ms=now, commit=False)
```

- [ ] **Step 3: Run worker tests**

```bash
uv run pytest tests/test_notification_worker.py -q
```

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add src/gmgn_twitter_intel/pipeline/notification_worker.py tests/test_notification_worker.py
git commit -m "feat: enqueue external notification deliveries"
```

### Task 15: Add Delivery Audit API and CLI

**Files:**
- Modify: `src/gmgn_twitter_intel/api/http.py`
- Modify: `src/gmgn_twitter_intel/cli.py`
- Modify: `tests/test_api_http.py`
- Modify: `tests/test_cli.py`

- [ ] **Step 1: Add tests**

API:

```python
def test_api_exposes_notification_deliveries(tmp_path):
    app = create_app(settings=make_settings(tmp_path), start_collector=False)
    with TestClient(app) as client:
        headers = {"Authorization": "Bearer secret"}
        response = client.get("/api/notification-deliveries?limit=10", headers=headers)

    assert response.status_code == 200
    assert response.json()["data"]["items"] == []
```

CLI:

```python
def test_cli_notification_deliveries_outputs_json(tmp_path, monkeypatch, capsys):
    write_runtime_config(tmp_path, monkeypatch)
    assert main(["notification-deliveries", "--limit", "5"]) == 0
    assert '"items": []' in capsys.readouterr().out
```

- [ ] **Step 2: Implement repository list method**

Add `list_deliveries(limit, status)` returning delivery rows ordered by `updated_at_ms DESC`.

- [ ] **Step 3: Add API endpoint**

```python
    @router.get("/notification-deliveries")
    async def notification_deliveries(
        request: Request,
        limit: Annotated[int, Query()] = 50,
        status: Annotated[str, Query()] = "",
    ) -> JSONResponse:
        runtime = _authenticated_runtime(request)
        parsed_status = status if status in {"pending", "running", "sent", "failed", "dead", "skipped"} else None
        return _json({"ok": True, "data": {"items": runtime.read_notifications.list_deliveries(limit=_limit(limit, maximum=500), status=parsed_status)}})
```

- [ ] **Step 4: Add CLI subcommand**

In `build_parser()`:

```python
notification_deliveries = subcommands.add_parser("notification-deliveries", help="inspect external notification delivery audit")
notification_deliveries.add_argument("--status", choices=("pending", "running", "sent", "failed", "dead", "skipped"), default=None)
notification_deliveries.add_argument("--limit", type=int, default=50)
```

In `main()` repository branch:

```python
if command == "notification-deliveries":
    _emit(
        {
            "ok": True,
            "data": {
                "items": notifications.list_deliveries(limit=args.limit, status=args.status),
            },
        },
        stdout,
    )
    return 0
```

Update `_repositories()` to include `NotificationRepository`.

- [ ] **Step 5: Run tests**

```bash
uv run pytest tests/test_api_http.py tests/test_cli.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/gmgn_twitter_intel/api/http.py src/gmgn_twitter_intel/cli.py tests/test_api_http.py tests/test_cli.py
git commit -m "feat: expose notification delivery audit"
```

### Task 16: Phase 2 Verification Gate

**Files:**
- Modify only if verification reveals a bug.

- [ ] **Step 1: Run Python verification**

```bash
uv run pytest
uv run ruff check .
uv run python -m compileall src tests
```

Expected: all pass.

- [ ] **Step 2: Run frontend verification**

```bash
cd web && npm test
cd web && npm run typecheck
cd web && npm run build
```

Expected: all pass.

- [ ] **Step 3: Dry-run external channel**

Configure a log channel:

```yaml
notifications:
  channels:
    local_log:
      enabled: true
      provider: log
      min_severity: warning
```

Start service:

```bash
uv run gmgn-twitter-intel serve
```

Create or wait for a warning/high notification. Then inspect:

```bash
uv run gmgn-twitter-intel notification-deliveries --limit 20
```

Expected: delivery rows move to `sent` for log provider.

- [ ] **Step 4: Real PushDeer smoke**

Configure:

```yaml
notifications:
  channels:
    pushdeer:
      enabled: true
      provider: apprise
      url: "pushdeer://pushKey"
      min_severity: high
```

Trigger or wait for `hot_quality_token_5m` or `harness_snapshot_high_score`. Inspect:

```bash
uv run gmgn-twitter-intel notification-deliveries --status sent --limit 20
```

Expected: one sent row and one PushDeer device notification.

- [ ] **Step 5: Commit fixes if needed**

```bash
git add <changed-files>
git commit -m "fix: stabilize external notification delivery"
```

---

## Final Full Verification

Run:

```bash
uv run pytest
uv run ruff check .
uv run python -m compileall src tests
cd web && npm test
cd web && npm run typecheck
cd web && npm run build
```

Expected: all pass.

## Residual Risks

- Token-flow notification rules depend on query-time scoring. The worker makes them durable, but thresholds should be tuned after live data observation.
- External channel URL syntax is delegated to Apprise. Invalid URLs are caught as delivery failures, not settings failures, because Apprise provider-specific validation may require runtime parsing.
- PushDeer/Telegram/WeCom provider limits vary. The delivery worker retries conservatively and marks dead after max attempts.
- Browser background push remains intentionally absent. Users who need background mobile notifications should use Phase 2 external channels.

## Execution Choice

Plan complete and saved to `docs/superpowers/plans/2026-05-05-production-notifications-phase1-phase2.md`. Two execution options:

1. **Subagent-Driven (recommended)** - dispatch a fresh subagent per task, review between tasks, fast iteration.
2. **Inline Execution** - execute tasks in this session using executing-plans, batch execution with checkpoints.

Choose one before implementation starts.
