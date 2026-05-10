# Notification and Pulse Dedupe Root Cause Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop notification spam and repeated Pulse thesis agent runs by fixing semantic dedupe boundaries at the notification, job enqueue, and storage layers.

**Architecture:** Keep the current PostgreSQL schema. Aggregate repeated notifications into existing rows, make notification dedup keys reflect user-visible alert units instead of volatile agent signatures, and prevent Pulse jobs from being overwritten or requeued by minor source/timeline churn. Enrichment event extraction is intentionally left unchanged because the investigation showed successful social-event extraction is already one row per event.

**Tech Stack:** Python 3.13, PostgreSQL/Psycopg, pytest, ruff, existing repository/session patterns.

---

## Investigation Baseline

- Last 12h production data showed `signal_pulse_candidate` created 176 notification rows for only 83 Pulse candidates.
- One VVV Pulse candidate emitted 12 notification rows and ran 62 Pulse thesis agent runs with 30 different input hashes.
- `notification_deliveries` had no duplicate `(notification_id, channel_id)` rows, so PushDeer repeats are caused upstream by new notification rows.
- `social_event_extractions` had 120 rows for 120 events; successful watched-account enrichment dedupe is working.

## File Structure

- Modify: `src/gmgn_twitter_intel/storage/notification_repository.py`
  Aggregates existing `dedup_key` conflicts instead of dropping them silently. Preserve the public return contract: return a row only for newly-created notifications so `NotificationWorker` does not enqueue external delivery on aggregates.

- Modify: `src/gmgn_twitter_intel/pipeline/notification_rules.py`
  Add stable semantic dedup helpers for watched activity, watched token alerts, and Signal Pulse. Keep volatile Pulse notification signatures in payload only.

- Modify: `src/gmgn_twitter_intel/settings.py`
  Set explicit default cooldowns for high-volume watched-account notification rules and keep Signal Pulse on status-specific cooldowns.

- Modify: `src/gmgn_twitter_intel/pipeline/pulse_candidate_worker.py`
  Add active-job and material-rerun guards. Remove latest source event churn from asset trigger signatures and make cooldown bypass require material escalation.

- Modify: `src/gmgn_twitter_intel/storage/pulse_repository.py`
  Defend against direct callers resetting active jobs on `ON CONFLICT(candidate_id)` when the job is still pending, running, or retryable failed.

- Modify tests:
  - `tests/test_notification_repository.py`
  - `tests/test_notification_rules.py`
  - `tests/test_settings.py`
  - `tests/test_pulse_candidate_worker.py`
  - `tests/test_pulse_repository.py`

No migration is required. Existing columns `occurrence_count`, `first_seen_at_ms`, and `last_seen_at_ms` already support aggregation.

---

## Task 1: Aggregate Notification Conflicts Without Re-Delivery

**Files:**
- Modify: `tests/test_notification_repository.py:12-47`
- Modify: `src/gmgn_twitter_intel/storage/notification_repository.py:22-86`

- [x] **Step 1: Replace the idempotency test with an aggregation regression test**

In `tests/test_notification_repository.py`, replace `test_insert_notification_is_idempotent_by_dedup_key` with:

```python
def test_insert_notification_aggregates_duplicate_dedup_key_without_returning_new_row(tmp_path):
    repo = repository(tmp_path)

    first = repo.insert_notification(
        dedup_key="rule:event-1",
        rule_id="watched_account_activity",
        severity="info",
        title="toly has new activity",
        body="A watched account posted.",
        entity_type="account",
        entity_key="account:toly",
        author_handle="toly",
        event_id="event-1",
        source_table="events",
        source_id="event-1",
        occurrence_at_ms=1_700_000_000_000,
        payload={"event_id": "event-1", "version": 1},
        channels=["in_app"],
    )
    duplicate = repo.insert_notification(
        dedup_key="rule:event-1",
        rule_id="watched_account_activity",
        severity="info",
        title="toly has new activity",
        body="A watched account posted again.",
        entity_type="account",
        entity_key="account:toly",
        author_handle="toly",
        event_id="event-2",
        source_table="events",
        source_id="event-2",
        occurrence_at_ms=1_700_000_060_000,
        payload={"event_id": "event-2", "version": 2},
        channels=["in_app"],
    )

    rows = repo.list_notifications(limit=10)

    assert first is not None
    assert duplicate is None
    assert len(rows) == 1
    assert rows[0]["notification_id"] == first["notification_id"]
    assert rows[0]["occurrence_count"] == 2
    assert rows[0]["first_seen_at_ms"] == 1_700_000_000_000
    assert rows[0]["last_seen_at_ms"] == 1_700_000_060_000
    assert rows[0]["payload_json"] == {"event_id": "event-2", "version": 2}
```

- [x] **Step 2: Run the failing test**

Run:

```bash
uv run pytest tests/test_notification_repository.py::test_insert_notification_aggregates_duplicate_dedup_key_without_returning_new_row -q
```

Expected: FAIL because duplicate conflicts currently return `None` without updating `occurrence_count` or `last_seen_at_ms`.

- [x] **Step 3: Update `NotificationRepository.insert_notification`**

Keep the existing signature. After the current notification insert statement with `ON CONFLICT(dedup_key) DO NOTHING`, branch on `cursor.rowcount`.

Use this SQL for conflict aggregation:

```sql
UPDATE notifications
SET severity = %s,
    title = %s,
    body = %s,
    author_handle = %s,
    symbol = %s,
    chain = %s,
    address = %s,
    event_id = %s,
    source_table = %s,
    source_id = %s,
    occurrence_count = occurrence_count + 1,
    last_seen_at_ms = GREATEST(last_seen_at_ms, %s),
    payload_json = %s,
    channels_json = %s,
    updated_at_ms = %s
WHERE dedup_key = %s
```

Implementation rule:

```python
if cursor.rowcount == 0:
    update_args = (
        normalized_severity,
        title,
        body,
        author_handle,
        symbol,
        chain,
        address,
        event_id,
        source_table,
        source_id,
        int(occurrence_at_ms),
        _json(payload or {}),
        _json(list(channels)),
        now_ms,
        dedup_key,
    )
    self.conn.execute(update_sql, update_args)
    if commit:
        self.conn.commit()
    return None
```

Return the inserted row only when `cursor.rowcount == 1`. This preserves `NotificationWorker.process_once()` behavior: external deliveries and websocket publishes happen only for new notification rows.

- [x] **Step 4: Run repository tests**

Run:

```bash
uv run pytest tests/test_notification_repository.py -q
```

Expected: PASS.

---

## Task 2: Stabilize Notification Semantic Dedup Keys

**Files:**
- Modify: `tests/test_notification_rules.py:120-170`
- Modify: `tests/test_notification_rules.py:340-370`
- Modify: `tests/test_notification_rules.py:400-470`
- Modify: `tests/test_settings.py:320-335`
- Modify: `src/gmgn_twitter_intel/pipeline/notification_rules.py:80-140`
- Modify: `src/gmgn_twitter_intel/pipeline/notification_rules.py:385-397`
- Modify: `src/gmgn_twitter_intel/pipeline/notification_rules.py:430-445`
- Modify: `src/gmgn_twitter_intel/settings.py:830-870`

- [x] **Step 1: Add watched-account activity cooldown test**

Add to `tests/test_notification_rules.py`:

```python
def test_watched_account_activity_uses_account_action_bucket_when_cooldown_configured():
    notifications = NotificationsConfig(
        rules={"watched_account_activity": {"enabled": True, "channels": ["in_app"], "cooldown_seconds": 300}}
    )
    events = [
        {"event_id": "event-1", "author_handle": "toly", "action": "post", "received_at_ms": NOW_MS, "text": "one"},
        {
            "event_id": "event-2",
            "author_handle": "toly",
            "action": "post",
            "received_at_ms": NOW_MS + 60_000,
            "text": "two",
        },
    ]

    candidates = [
        item for item in engine(events=events, notifications=notifications).evaluate(now_ms=NOW_MS)
        if item.rule_id == "watched_account_activity"
    ]

    assert len(candidates) == 2
    assert candidates[0].dedup_key == candidates[1].dedup_key
    assert candidates[0].dedup_key == f"watched_account_activity:account:toly:post:{NOW_MS // 300_000}"
```

- [x] **Step 2: Add watched-token alert semantic cooldown test**

Add to `tests/test_notification_rules.py`:

```python
def test_watched_account_token_alert_uses_asset_author_bucket_when_cooldown_configured():
    notifications = NotificationsConfig(
        rules={"watched_account_token_alert": {"enabled": True, "channels": ["in_app", "pushdeer"], "cooldown_seconds": 900}}
    )
    alerts = [
        {
            "alert_id": "alert-1",
            "received_at_ms": NOW_MS,
            "author_handle": "toly",
            "normalized_value": "TROLL",
            "entity_key": "asset:solana:token:troll",
            "is_first_seen_global": True,
            "is_first_seen_by_author": True,
        },
        {
            "alert_id": "alert-2",
            "received_at_ms": NOW_MS + 120_000,
            "author_handle": "toly",
            "normalized_value": "TROLL",
            "entity_key": "asset:solana:token:troll",
            "is_first_seen_global": False,
            "is_first_seen_by_author": False,
        },
    ]

    candidates = [
        item for item in engine(alerts=alerts, notifications=notifications).evaluate(now_ms=NOW_MS)
        if item.rule_id == "watched_account_token_alert"
    ]

    assert len(candidates) == 2
    assert candidates[0].dedup_key == candidates[1].dedup_key
    assert candidates[0].dedup_key == f"watched_account_token_alert:asset:solana:token:troll:author:toly:{NOW_MS // 900_000}"
```

- [x] **Step 3: Replace Signal Pulse dedup test**

Change `test_signal_pulse_dedup_key_uses_candidate_signature_and_status_cooldown_bucket` to assert signature changes do not change the dedup key inside the same status bucket:

```python
def test_signal_pulse_dedup_key_uses_candidate_status_bucket_not_signature():
    base = pulse_candidate("watch", status="token_watch", updated_at_ms=NOW_MS, evidence_ids=["event-1"])
    changed_signature = pulse_candidate(
        "watch",
        status="token_watch",
        updated_at_ms=NOW_MS + 60_000,
        evidence_ids=["event-1", "event-2"],
        confirmations=["new independent confirmation"],
    )
    status_upgrade = pulse_candidate("watch", status="trade_candidate", updated_at_ms=NOW_MS)

    first = _only_pulse_notification(base)
    second = _only_pulse_notification(changed_signature)
    upgraded = _only_pulse_notification(status_upgrade)

    assert first.payload["notification_signature"] != second.payload["notification_signature"]
    assert first.dedup_key == second.dedup_key
    assert first.dedup_key == f"signal_pulse_candidate:watch:token_watch:{NOW_MS // (30 * 60_000)}"
    assert upgraded.dedup_key == f"signal_pulse_candidate:watch:trade_candidate:{NOW_MS // (15 * 60_000)}"
```

- [x] **Step 4: Implement notification key helpers**

In `src/gmgn_twitter_intel/pipeline/notification_rules.py`, add helpers near the existing private helpers:

```python
def _cooldown_bucket(occurrence_at_ms: int, cooldown_seconds: int) -> int:
    return occurrence_at_ms // (max(1, int(cooldown_seconds)) * 1000)


def _semantic_or_event_activity_key(rule_id: str, *, event_id: str, author_handle: str, action: str, occurrence_at_ms: int, cooldown_seconds: int) -> str:
    if cooldown_seconds <= 0:
        return f"{rule_id}:event:{event_id}"
    author = author_handle or "unknown"
    normalized_action = action or "activity"
    return f"{rule_id}:account:{author}:{normalized_action}:{_cooldown_bucket(occurrence_at_ms, cooldown_seconds)}"


def _semantic_or_alert_key(rule_id: str, *, alert_id: str, entity_key: str, author_handle: str, occurrence_at_ms: int, cooldown_seconds: int) -> str:
    if cooldown_seconds <= 0:
        return f"{rule_id}:alert:{alert_id}"
    identity = entity_key or "unknown"
    author = author_handle or "unknown"
    return f"{rule_id}:{identity}:author:{author}:{_cooldown_bucket(occurrence_at_ms, cooldown_seconds)}"
```

Use these helpers in `_watched_account_activity()` and `_watched_account_token_alerts()` instead of always using `event_id` / `alert_id`.

- [x] **Step 5: Implement stable Signal Pulse dedup key**

Change `_signal_pulse_candidates()` so `signature` remains payload-only and the key is:

```python
cooldown_ms = max(0, int(rule.cooldown_seconds)) * 1000 or SIGNAL_PULSE_COOLDOWN_MS[status]
bucket = occurrence_at_ms // cooldown_ms
signature = _pulse_notification_signature(row)
payload = _pulse_payload(row, notification_signature=signature)
dedup_key = f"{SIGNAL_PULSE_RULE_ID}:{candidate_id}:{status}:{bucket}"
```

Keep `_pulse_notification_signature()` unchanged for payload/UI auditability.

- [x] **Step 6: Set default high-volume rule cooldowns**

In `src/gmgn_twitter_intel/settings.py`, update `_default_notification_rule_payloads()`:

```python
"watched_account_activity": {
    "enabled": True,
    "channels": ("in_app",),
    "cooldown_seconds": 300,
},
"watched_account_token_alert": {
    "enabled": True,
    "channels": ("in_app",),
    "cooldown_seconds": 900,
},
```

Keep `signal_pulse_candidate.cooldown_seconds` at `0` so status-specific defaults remain active.

- [x] **Step 7: Run notification rule and settings tests**

Run:

```bash
uv run pytest tests/test_notification_rules.py tests/test_settings.py -q
```

Expected: PASS after updating old assertions that expected event-id-only and signature-based keys.

---

## Task 3: Prevent Pulse Job Churn From Minor Trigger/Timeline Changes

**Files:**
- Modify: `tests/test_pulse_candidate_worker.py:28-110`
- Modify: `tests/test_pulse_candidate_worker.py:151-210`
- Modify: `tests/test_pulse_candidate_worker.py:263-280`
- Modify: `src/gmgn_twitter_intel/pipeline/pulse_candidate_worker.py:365-388`
- Modify: `src/gmgn_twitter_intel/pipeline/pulse_candidate_worker.py:591-623`
- Modify: `src/gmgn_twitter_intel/pipeline/pulse_candidate_worker.py:695-741`

- [x] **Step 1: Add active-job guard test**

Add to `tests/test_pulse_candidate_worker.py`:

```python
def test_existing_pending_job_blocks_signature_churn_reenqueue() -> None:
    repos = FakeRepos()
    first_row = _radar_row(heat=86, event_id="event-1")
    repos.token_radar.rows = [first_row]
    repos.token_targets.rows = [_timeline_row("event-1", NOW_MS - 10_000)]
    worker = PulseCandidateWorker(repository_session=lambda: _session(repos), thesis_client=FakeClient())

    first = worker.scan_triggers_once(now_ms=NOW_MS)
    repos.token_radar.rows = [_radar_row(heat=87, event_id="event-2")]
    repos.token_targets.rows = [_timeline_row("event-2", NOW_MS + 10_000)]
    second = worker.scan_triggers_once(now_ms=NOW_MS + 10_000)

    assert first["asset_enqueued"] == 1
    assert second["asset_skipped"] == 1
    assert len(repos.pulse.jobs) == 1
    assert repos.pulse.jobs[0]["attempt_count"] == 0
    assert repos.pulse.jobs[0]["trigger_signature"] == _asset_trigger_signature(
        row=first_row,
        window="1h",
        scope="all",
        candidate_type="token_target",
    )
```

- [x] **Step 2: Tighten cooldown bypass tests**

Update `test_cooldown_bypass_matrix()` so heat bucket changes and market freshness alone no longer bypass:

```python
assert not _cooldown_bypass({"pulse_status": "token_watch"}, previous, {**previous, "heat_bucket": "90-99"})
assert not _cooldown_bypass({"pulse_status": "token_watch"}, previous, {**previous, "market_status": "fresh"})
assert _cooldown_bypass(existing, previous, {**previous, "trade_candidate_eligible": True})
assert _cooldown_bypass({"pulse_status": "token_watch"}, previous, {**previous, "watched_confirmation": True})
assert _cooldown_bypass({"pulse_status": "token_watch"}, previous, {**previous, "independent_author_count": 7})
```

Keep hard-risk and status-escalation bypass assertions.

- [x] **Step 3: Update changed-signature rerun test to require a material escalation**

In `test_reenqueue_changed_signature_creates_distinct_run_ids()`, change the second row so it includes a material bypass signal:

```python
repos.token_radar.rows = [_radar_row(heat=96, event_id="event-2", watched_mentions=1)]
```

Add an assertion before that rerun showing non-material event churn is skipped:

```python
repos.token_radar.rows = [_radar_row(heat=87, event_id="event-churn")]
repos.token_targets.rows = [_timeline_row("event-churn", NOW_MS + 1_500)]
skipped = worker.scan_triggers_once(now_ms=NOW_MS + 1_500)
assert skipped["asset_skipped"] == 1
```

- [x] **Step 4: Add `_active_job_blocks_reenqueue`**

In `src/gmgn_twitter_intel/pipeline/pulse_candidate_worker.py`, add:

```python
def _active_job_blocks_reenqueue(existing_job: dict[str, Any] | None, *, now_ms: int) -> bool:
    if not existing_job:
        return False
    status = _clean(existing_job.get("status"))
    if status in {"pending", "running"}:
        return True
    if status == "failed":
        attempt_count = safe_int(existing_job.get("attempt_count"))
        max_attempts = safe_int(existing_job.get("max_attempts")) or 3
        return attempt_count < max_attempts
    return False
```

Call it in `_enqueue_if_due()` immediately after `existing_job` is loaded and before signature comparisons:

```python
if _active_job_blocks_reenqueue(existing_job, now_ms=now_ms):
    return False
```

- [x] **Step 5: Remove volatile source-event fields from asset trigger signature**

In `_asset_trigger_signature()`, remove:

```python
"latest_source_event_id": _latest_source_event_id(row),
"bucketed_latest_seen": _time_bucket_ms(_latest_seen_ms(row), 5 * 60 * 1000),
```

Add propagation because propagation participates in trigger decisions:

```python
"propagation_bucket": metrics["propagation_bucket"],
```

Do not add timeline hashes into the trigger signature; timeline changes are controlled by candidate cooldown and material bypass.

- [x] **Step 6: Tighten `_cooldown_bypass`**

Replace the current heat-bucket and market-fresh bypasses with material escalation only:

```python
if _STATUS_RANK.get(current_status, 0) > _STATUS_RANK.get(previous_status, 0):
    return True
if current.get("trade_candidate_eligible") and previous_status != "trade_candidate":
    return True
if not previous.get("watched_confirmation") and current.get("watched_confirmation"):
    return True
if safe_int(current.get("independent_author_count")) >= safe_int(previous.get("independent_author_count")) + 5:
    return True
if not previous.get("chase_risk") and current.get("chase_risk"):
    return True
return bool(set(current.get("hard_risks") or []) - set(previous.get("hard_risks") or []))
```

Keep social phase out of bypass unless it changes the inferred status. Social phase churn was one of the observed reasons token targets kept re-running.

- [x] **Step 7: Run Pulse worker tests**

Run:

```bash
uv run pytest tests/test_pulse_candidate_worker.py -q
```

Expected: PASS.

---

## Task 4: Preserve Active Pulse Job Retry State In Storage

**Files:**
- Modify: `tests/test_pulse_repository.py`
- Modify: `src/gmgn_twitter_intel/storage/pulse_repository.py:46-75`

- [x] **Step 1: Add repository conflict regression test**

Add to `tests/test_pulse_repository.py`:

```python
def test_enqueue_job_preserves_active_retry_state_on_signature_churn(tmp_path) -> None:
    repo = repository(tmp_path)
    first = repo.enqueue_job(
        candidate_id="candidate-1",
        candidate_type="token_target",
        subject_key="asset-1",
        target_type="Asset",
        target_id="asset-1",
        window="1h",
        scope="all",
        trigger_signature="trigger-1",
        timeline_signature="timeline-1",
        priority=80,
        status="failed",
        attempt_count=2,
        max_attempts=3,
        next_run_at_ms=1_800_000,
        now_ms=1_700_000,
    )
    second = repo.enqueue_job(
        candidate_id="candidate-1",
        candidate_type="token_target",
        subject_key="asset-1",
        target_type="Asset",
        target_id="asset-1",
        window="1h",
        scope="all",
        trigger_signature="trigger-2",
        timeline_signature="timeline-2",
        priority=90,
        status="pending",
        attempt_count=0,
        max_attempts=3,
        next_run_at_ms=1_700_100,
        now_ms=1_700_100,
    )

    assert first["job_id"] == second["job_id"]
    assert second["status"] == "failed"
    assert second["attempt_count"] == 2
    assert second["trigger_signature"] == "trigger-1"
```

- [x] **Step 2: Run failing repository test**

Run:

```bash
uv run pytest tests/test_pulse_repository.py::test_enqueue_job_preserves_active_retry_state_on_signature_churn -q
```

Expected: FAIL because `ON CONFLICT(candidate_id)` currently resets `status`, `attempt_count`, and signatures.

- [x] **Step 3: Add active-state preservation to `enqueue_job` SQL**

In `src/gmgn_twitter_intel/storage/pulse_repository.py`, update `ON CONFLICT(candidate_id) DO UPDATE SET` fields with a terminal-state condition:

```sql
trigger_signature = CASE
  WHEN pulse_agent_jobs.status IN ('pending', 'running', 'failed')
   AND pulse_agent_jobs.attempt_count < pulse_agent_jobs.max_attempts
  THEN pulse_agent_jobs.trigger_signature
  ELSE excluded.trigger_signature
END,
timeline_signature = CASE
  WHEN pulse_agent_jobs.status IN ('pending', 'running', 'failed')
   AND pulse_agent_jobs.attempt_count < pulse_agent_jobs.max_attempts
  THEN pulse_agent_jobs.timeline_signature
  ELSE excluded.timeline_signature
END,
context_json = CASE
  WHEN pulse_agent_jobs.status IN ('pending', 'running', 'failed')
   AND pulse_agent_jobs.attempt_count < pulse_agent_jobs.max_attempts
  THEN pulse_agent_jobs.context_json
  ELSE excluded.context_json
END,
status = CASE
  WHEN pulse_agent_jobs.status IN ('pending', 'running', 'failed')
   AND pulse_agent_jobs.attempt_count < pulse_agent_jobs.max_attempts
  THEN pulse_agent_jobs.status
  ELSE excluded.status
END,
attempt_count = CASE
  WHEN pulse_agent_jobs.status IN ('pending', 'running', 'failed')
   AND pulse_agent_jobs.attempt_count < pulse_agent_jobs.max_attempts
  THEN pulse_agent_jobs.attempt_count
  ELSE excluded.attempt_count
END,
next_run_at_ms = CASE
  WHEN pulse_agent_jobs.status IN ('pending', 'running', 'failed')
   AND pulse_agent_jobs.attempt_count < pulse_agent_jobs.max_attempts
  THEN pulse_agent_jobs.next_run_at_ms
  ELSE excluded.next_run_at_ms
END
```

Leave `priority` eligible for update only if it does not reset execution state:

```sql
priority = GREATEST(pulse_agent_jobs.priority, excluded.priority)
```

- [x] **Step 4: Run Pulse repository tests**

Run:

```bash
uv run pytest tests/test_pulse_repository.py -q
```

Expected: PASS.

---

## Task 5: End-to-End Regression Checks

**Files:**
- Modify: `docs/superpowers/plans/2026-05-10-notification-pulse-dedupe-root-cause.md`
- Create or update after implementation: `docs/superpowers/plans/2026-05-10-notification-pulse-dedupe-root-cause-verification.md`

- [x] **Step 1: Run focused test suite**

Run:

```bash
uv run pytest \
  tests/test_notification_repository.py \
  tests/test_notification_rules.py \
  tests/test_settings.py \
  tests/test_pulse_candidate_worker.py \
  tests/test_pulse_repository.py \
  -q
```

Expected: PASS.

- [x] **Step 2: Run full verification commands**

Run:

```bash
uv run ruff check .
uv run pytest
uv run python -m compileall src tests
```

Expected: all PASS.

- [ ] **Step 3: Run local production-shape smoke probes**

After restarting the service with the patched code, run:

```bash
curl -s http://127.0.0.1:8765/readyz | jq '.ok'
```

Expected:

```json
true
```

Probe notification duplication after at least one notification worker cycle:

```sql
WITH recent AS (
  SELECT *
  FROM notifications
  WHERE created_at_ms >= (extract(epoch from now()) * 1000)::bigint - 60 * 60 * 1000
)
SELECT rule_id,
       count(*) AS rows,
       count(DISTINCT source_id) AS sources,
       max(occurrence_count) AS max_occurrences
FROM recent
GROUP BY rule_id
ORDER BY rows DESC;
```

Expected: `signal_pulse_candidate` rows should not exceed distinct Pulse sources by more than status/cooldown transitions, and repeated same-status updates should increase `occurrence_count` instead of creating new rows.

Probe Pulse thesis churn:

```sql
WITH recent AS (
  SELECT *
  FROM pulse_agent_runs
  WHERE started_at_ms >= (extract(epoch from now()) * 1000)::bigint - 60 * 60 * 1000
)
SELECT candidate_id,
       count(*) AS runs,
       count(DISTINCT input_hash) AS input_hashes
FROM recent
GROUP BY candidate_id
HAVING count(*) > 3
ORDER BY runs DESC;
```

Expected: no hot candidate should accumulate repeated runs from minor source/timeline churn inside the configured cooldown. Failures may still retry up to `max_attempts`.

- [x] **Step 4: Write verification artifact**

Create `docs/superpowers/plans/2026-05-10-notification-pulse-dedupe-root-cause-verification.md` with:

```markdown
# Notification and Pulse Dedupe Root Cause Verification

**Date:** 2026-05-10
**Branch:** codex/dedupe-investigation

## Commands

- `uv run ruff check .` — result:
- `uv run pytest` — result:
- `uv run python -m compileall src tests` — result:

## Focused Regression Evidence

- Notification conflict aggregation:
- Signal Pulse stable dedup:
- Pulse active-job guard:
- Pulse storage active-state preservation:

## Live Smoke Evidence

- `/readyz`:
- Notification duplicate probe:
- Pulse run churn probe:

## Risks

- Watched-account activity will aggregate in-app notifications by account/action bucket, reducing row volume but also hiding individual posts behind `occurrence_count`.
- Signal Pulse same-status thesis updates inside a cooldown bucket will update payload without new PushDeer delivery.
- Agent retries for model errors still run up to `max_attempts`; this is expected and not treated as duplicate analysis.
```

---

## Rollout

1. Merge code without schema migration.
2. Restart the single ASGI worker so notification and Pulse workers use the patched dedupe logic.
3. Monitor the 1h SQL probes above.
4. Compare PushDeer volume against the previous 12h baseline: repeated same candidate/status notifications should collapse into `occurrence_count`.

## Rollback

1. Revert the code commit.
2. Restart the single ASGI worker.
3. No database rollback is needed because the plan only updates existing notification rows and preserves schema.
4. If aggregation obscures rows operators still need, query `payload_json`, `first_seen_at_ms`, `last_seen_at_ms`, and `occurrence_count` for the affected `dedup_key`.

## Acceptance Criteria

- Same `dedup_key` updates `occurrence_count` and `last_seen_at_ms` but returns `None` to `NotificationWorker`, so no duplicate external delivery is enqueued.
- Signal Pulse dedup no longer includes volatile `notification_signature`.
- Same candidate/status/cooldown Signal Pulse updates aggregate into one row.
- Existing pending/running/retryable failed Pulse jobs are not overwritten by new trigger/timeline signatures.
- Minor token-target source-event churn does not rerun Pulse thesis agent inside cooldown.
- Material escalation still reruns: status upgrade, trade eligibility, new watched confirmation, large independent-author jump, chase risk, or new hard risk.
- Watched-account enrichment remains unchanged and keeps one successful extraction per event.
