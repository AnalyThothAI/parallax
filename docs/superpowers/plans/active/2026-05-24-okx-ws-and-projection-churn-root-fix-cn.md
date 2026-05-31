# OKX WS And Projection Churn Root Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 根治 OKX DEX WS 长跑失败、market tick 放大 Token Radar 投影，以及 Equity/Token Radar read-model 高频无意义 update/delete。

**Architecture:** Hard cut the runtime paths. OKX WS becomes a protocol-compliant connection manager with app-level heartbeat, reconnect/resubscribe, circuit/degraded health, and no naked `recv()` path. Projection writes become content-addressed: current/read-model rows mutate only when public payload changes, market-driven Radar dirties are coalesced, and replace-style page/timeline deletes are removed.

**Tech Stack:** Python 3.12, asyncio, websockets, psycopg/PostgreSQL, Alembic, pytest, Docker Compose.

---

## Scope And Hard-Cut Rules

This plan implements the active spec:

- `docs/superpowers/specs/active/2026-05-24-okx-ws-resilience-root-fix-cn.md`

The user explicitly expanded scope on 2026-05-24 to include projection high-frequency update/delete root cause. This plan treats that as part of the same root-fix release because OKX tick recovery without projection write suppression would reintroduce the CPU failure mode.

Hard-cut rules:

- No feature flag that keeps the old OKX naked `recv()` implementation.
- No compatibility branch that preserves row freshness by timestamp-only updates.
- No worker-level workaround that merely catches errors while leaving provider protocol broken.
- No config-only fix. Runtime config may be restored after code is fixed, but correctness must come from code and tests.
- No secret values in tests, logs, status, CLI output, or docs.

## Current Root Causes

OKX WS:

- `src/parallax/integrations/okx/dex_ws_client.py:81` uses websocket protocol `ping_interval=20`; OKX requires application text `"ping"` and `"pong"`.
- `src/parallax/integrations/okx/dex_ws_client.py:145` exposes a raw `recv()` generator and sends every message to `json.loads()`, so plain text `pong` and service `notice` are not first-class protocol states.
- `src/parallax/domains/asset_market/runtime/market_tick_stream_worker.py:121` bounds worker calls, but provider lifecycle is still not self-healing.

Token Radar churn:

- `src/parallax/domains/asset_market/runtime/market_tick_stream_worker.py:171` and `src/parallax/domains/asset_market/runtime/market_tick_poll_worker.py:262` enqueue Radar dirty targets for every inserted market tick.
- `src/parallax/domains/token_intel/repositories/token_radar_dirty_target_repository.py:138` builds market dirty payload hashes with `now_ms`, so repeated ticks for the same target are always treated as new dirtiness.
- `src/parallax/domains/token_intel/repositories/token_radar_repository.py:479` updates `token_radar_target_features` when only `last_scored_at_ms` advances.
- `src/parallax/domains/token_intel/repositories/token_radar_repository.py:151` updates `token_radar_current_rows` even when payload is unchanged, solely to advance `computed_at_ms`.
- `src/parallax/domains/token_intel/repositories/token_radar_repository.py:627` updates `token_radar_target_first_seen.last_seen_ms` for every publish.
- `src/parallax/domains/pulse_lab/services/pulse_policy_evaluator.py:28` treats `token_radar_current_rows.computed_at_ms` as projection freshness, which currently forces timestamp-only current-row rewrites.

Equity read-model churn:

- `src/parallax/domains/equity_event_intel/repositories/equity_event_repository.py:572` mutates `equity_event_documents.updated_at_ms` for duplicate provider documents even when `content_hash` is unchanged.
- `src/parallax/domains/equity_event_intel/repositories/equity_event_repository.py:681` mutates `equity_company_events.updated_at_ms` for stable duplicates.
- `src/parallax/domains/equity_event_intel/repositories/equity_event_repository.py:1102` deletes and reinserts `equity_event_page_rows`.
- `src/parallax/domains/equity_event_intel/repositories/equity_event_repository.py:2146` deletes and reinserts `equity_company_timeline_rows`.
- `src/parallax/domains/equity_event_intel/repositories/equity_event_repository.py:1418` uses source `updated_at_ms` to decide projection staleness, so duplicate document/event timestamp churn cascades into repeated page/timeline rebuilds.

## Files To Modify

OKX WS:

- Modify: `src/parallax/integrations/okx/dex_ws_client.py`
- Modify: `src/parallax/app/runtime/provider_wiring/okx.py`
- Modify: `src/parallax/domains/asset_market/runtime/market_tick_stream_worker.py`
- Modify: `src/parallax/app/runtime/app.py`
- Modify: `tests/unit/test_okx_dex_ws_client.py`
- Modify: `tests/unit/test_market_tick_stream_worker.py`
- Modify: `tests/unit/test_runtime_readiness.py` or the existing readiness test file found by `rg "_readiness_payload|provider_states"`

Market/Token Radar churn:

- Modify: `src/parallax/domains/token_intel/repositories/token_radar_dirty_target_repository.py`
- Modify: `src/parallax/domains/token_intel/repositories/token_radar_repository.py`
- Modify: `src/parallax/domains/token_intel/services/token_radar_projection.py`
- Modify: `src/parallax/domains/pulse_lab/services/pulse_policy_evaluator.py`
- Modify: `tests/unit/test_token_radar_dirty_target_repository.py`
- Modify: `tests/unit/test_token_radar_repository.py`
- Modify: `tests/integration/test_token_radar_repository.py`
- Modify: `tests/integration/test_token_radar_idempotency.py`
- Modify: `tests/unit/domains/pulse_lab/test_pulse_policy_evaluator.py`

Equity churn:

- Create: `src/parallax/platform/db/alembic/versions/20260524_0091_projection_churn_payload_hashes.py`
- Modify: `src/parallax/domains/equity_event_intel/repositories/equity_event_repository.py`
- Modify: `src/parallax/domains/equity_event_intel/services/page_projection.py`
- Modify: `tests/integration/test_equity_event_repository.py`
- Modify: `tests/integration/test_equity_event_workers.py`
- Modify: `tests/unit/domains/equity_event_intel/test_page_projection.py`
- Modify: `tests/unit/test_postgres_schema.py`
- Modify: `tests/integration/test_postgres_schema_runtime.py`

Ops verification:

- Create: `docs/superpowers/plans/active/2026-05-24-okx-ws-and-projection-churn-root-fix-cn-verification.md` during execution, or use the final Verification section in this plan.
- Modify if needed: `docs/TECH_DEBT.md` only for residual non-trivial follow-ups discovered during verification.

## Task 0: Create Isolated Worktree

**Files:** none

- [ ] **Step 1: Confirm main checkout status**

Run:

```bash
git status --short
git branch --show-current
git worktree list
```

Expected:

- Existing user changes may be present.
- Do not revert them.

- [ ] **Step 2: Create worktree**

Run:

```bash
git worktree add .worktrees/okx-ws-projection-churn-root-fix -b codex/okx-ws-projection-churn-root-fix main
```

Expected:

- Worktree exists at `.worktrees/okx-ws-projection-churn-root-fix`.
- Branch is `codex/okx-ws-projection-churn-root-fix`.

- [ ] **Step 3: Verify worktree**

Run:

```bash
cd .worktrees/okx-ws-projection-churn-root-fix
git status --short
git branch --show-current
```

Expected:

- Branch: `codex/okx-ws-projection-churn-root-fix`
- Status: clean except copied active spec/plan files if they are intentionally included.

## Task 1: OKX WS Protocol Tests

**Files:**

- Modify: `tests/unit/test_okx_dex_ws_client.py`

- [ ] **Step 1: Add failing heartbeat and pong tests**

Append tests that prove application text `pong` is handled before JSON parsing and text `ping` is sent on idle:

```python
def test_okx_dex_ws_consumes_plain_text_pong_without_json_parse(monkeypatch):
    fake_ws = FakeWebSocket(messages=[_login_ok(), "pong", _price_message("1", "0xabc", price="1.23")])
    connect_calls: list[dict[str, Any]] = []

    def fake_connect(*args, **kwargs):
        return _FakeConnect(fake_ws, connect_calls, args=args, kwargs=kwargs)

    monkeypatch.setattr(dex_ws_client.websockets, "connect", fake_connect)
    provider = OkxDexWebSocketMarketProvider(
        url="wss://example.test",
        api_key="key",
        secret_key="secret",
        passphrase="pass",
        subscription_limit=10,
    )

    async def scenario() -> None:
        await provider.replace_subscriptions([{"chainIndex": "1", "tokenContractAddress": "0xabc"}])
        update = await provider.iter_price_info().__aiter__().__anext__()
        assert update.address == "0xabc"
        await provider.aclose()

    asyncio.run(scenario())

    assert provider.connection_state_payload()["last_pong_at_ms"] is not None
```

```python
def test_okx_dex_ws_sends_plain_text_ping_after_idle(monkeypatch):
    fake_ws = FakeIdleThenPongWebSocket(messages=[_login_ok(), _price_message("1", "0xabc", price="1.23")])
    connect_calls: list[dict[str, Any]] = []

    def fake_connect(*args, **kwargs):
        return _FakeConnect(fake_ws, connect_calls, args=args, kwargs=kwargs)

    monkeypatch.setattr(dex_ws_client.websockets, "connect", fake_connect)
    monkeypatch.setattr(dex_ws_client, "OKX_DEX_WS_IDLE_PING_SECONDS", 0.001, raising=False)
    monkeypatch.setattr(dex_ws_client, "OKX_DEX_WS_PONG_TIMEOUT_SECONDS", 0.05, raising=False)
    provider = OkxDexWebSocketMarketProvider(
        url="wss://example.test",
        api_key="key",
        secret_key="secret",
        passphrase="pass",
        subscription_limit=10,
    )

    async def scenario() -> None:
        await provider.replace_subscriptions([{"chainIndex": "1", "tokenContractAddress": "0xabc"}])
        update = await asyncio.wait_for(provider.iter_price_info().__aiter__().__anext__(), timeout=0.2)
        assert update.price_usd == 1.23
        await provider.aclose()

    asyncio.run(scenario())

    assert "ping" in fake_ws.sent
    assert provider.connection_state_payload()["last_pong_at_ms"] is not None
```

Add the fake websocket helper:

```python
class FakeIdleThenPongWebSocket(FakeWebSocket):
    def __init__(self, *, messages: list[str | BaseException]) -> None:
        super().__init__(messages=messages)
        self._sent_pong = False

    async def recv(self):
        if not self._sent_pong and any(payload == "ping" for payload in self.sent):
            self._sent_pong = True
            return "pong"
        if not self._messages:
            await asyncio.sleep(60)
        return await super().recv()
```

- [ ] **Step 2: Add failing notice reconnect/resubscribe test**

```python
def test_okx_dex_ws_reconnects_and_resubscribes_after_notice(monkeypatch):
    first_ws = FakeWebSocket(messages=[_login_ok(), json.dumps({"event": "notice", "code": "64008", "msg": "service upgrade"})])
    second_ws = FakeWebSocket(messages=[_login_ok(), _price_message("1", "0xabc", price="4.56")])
    sockets = [first_ws, second_ws]
    connect_calls: list[dict[str, Any]] = []

    def fake_connect(*args, **kwargs):
        return _FakeConnect(sockets[len(connect_calls)], connect_calls, args=args, kwargs=kwargs)

    monkeypatch.setattr(dex_ws_client.websockets, "connect", fake_connect)
    provider = OkxDexWebSocketMarketProvider(
        url="wss://example.test",
        api_key="key",
        secret_key="secret",
        passphrase="pass",
        subscription_limit=10,
    )

    async def scenario() -> None:
        await provider.replace_subscriptions([{"chainIndex": "1", "tokenContractAddress": "0xabc"}])
        update = await asyncio.wait_for(provider.iter_price_info().__aiter__().__anext__(), timeout=0.2)
        assert update.price_usd == 4.56
        await provider.aclose()

    asyncio.run(scenario())

    assert len(connect_calls) == 2
    assert _sent_ops(first_ws) == ["login", "subscribe"]
    assert _sent_ops(second_ws) == ["login", "subscribe"]
    assert provider.connection_state_payload()["last_error_category"] == "notice_reconnect"
```

- [ ] **Step 3: Add failing circuit-open test**

```python
def test_okx_dex_ws_circuit_opens_after_recoverable_failures(monkeypatch):
    connect_calls: list[dict[str, Any]] = []

    def failing_connect(*args, **kwargs):
        connect_calls.append({"args": args, "kwargs": kwargs})
        raise TimeoutError("opening handshake timed out")

    monkeypatch.setattr(dex_ws_client.websockets, "connect", failing_connect)
    monkeypatch.setattr(dex_ws_client, "OKX_DEX_WS_CIRCUIT_FAILURES", 2, raising=False)
    provider = OkxDexWebSocketMarketProvider(
        url="wss://example.test",
        api_key="key",
        secret_key="secret",
        passphrase="pass",
        subscription_limit=10,
    )

    async def scenario() -> None:
        for _ in range(2):
            with pytest.raises(TimeoutError):
                await provider.ensure_connected()
        with pytest.raises(OkxDexWsClientError, match="circuit open"):
            await provider.ensure_connected()

    asyncio.run(scenario())

    payload = provider.connection_state_payload()
    assert payload["state"] == "circuit_open"
    assert payload["last_error_category"] == "connect_timeout"
```

- [ ] **Step 4: Run tests and verify failure**

Run:

```bash
uv run pytest tests/unit/test_okx_dex_ws_client.py -q
```

Expected:

- New tests fail because current code parses `pong` as JSON, has no app ping, has no notice reconnect, and has no circuit-open state.

## Task 2: OKX WS Connection Manager Hard Cut

**Files:**

- Modify: `src/parallax/integrations/okx/dex_ws_client.py`
- Modify: `src/parallax/app/runtime/provider_wiring/okx.py`

- [ ] **Step 1: Replace state constants and health payload**

In `dex_ws_client.py`, replace `WS_CONNECTION_STATES` with:

```python
WS_CONNECTION_STATES = frozenset(
    {
        "disconnected",
        "connecting",
        "authenticating",
        "subscribed",
        "streaming",
        "degraded_recoverable",
        "failed_terminal",
        "circuit_open",
    }
)

OKX_DEX_WS_CONNECT_TIMEOUT_SECONDS = 10.0
OKX_DEX_WS_LOGIN_TIMEOUT_SECONDS = 5.0
OKX_DEX_WS_CLOSE_TIMEOUT_SECONDS = 5.0
OKX_DEX_WS_IDLE_PING_SECONDS = 25.0
OKX_DEX_WS_PONG_TIMEOUT_SECONDS = 5.0
OKX_DEX_WS_CIRCUIT_FAILURES = 3
OKX_DEX_WS_CIRCUIT_COOLDOWN_SECONDS = 60.0
```

Add instance fields in `__init__`:

```python
self.last_message_at_ms: int | None = None
self.last_ping_at_ms: int | None = None
self.last_pong_at_ms: int | None = None
self.last_error_category: str | None = None
self.last_error_code: str | None = None
self.reconnect_count = 0
self.data_frame_count = 0
self.tick_count = 0
self._desired_args: list[dict[str, str]] = []
self._acked_args: set[tuple[str, str]] = set()
self._recoverable_failures = 0
self._circuit_open_until_monotonic = 0.0
```

Expand `connection_state_payload()` to return:

```python
return {
    "provider": "okx_dex_ws",
    "state": self.connection_state,
    "last_state_change_at_ms": self.last_state_change_at_ms,
    "last_message_at_ms": self.last_message_at_ms,
    "last_ping_at_ms": self.last_ping_at_ms,
    "last_pong_at_ms": self.last_pong_at_ms,
    "last_error_category": self.last_error_category,
    "last_error_code": self.last_error_code,
    "reconnect_count": self.reconnect_count,
    "desired_subscription_count": len(self._desired_args),
    "acked_subscription_count": len(self._acked_args),
    "data_frame_count": self.data_frame_count,
    "tick_count": self.tick_count,
}
```

- [ ] **Step 2: Disable library protocol ping and implement app heartbeat**

In `ensure_connected()`, use:

```python
websocket = await _await_bounded(
    websockets.connect(
        self.url,
        ping_interval=None,
        open_timeout=OKX_DEX_WS_CONNECT_TIMEOUT_SECONDS,
        close_timeout=OKX_DEX_WS_CLOSE_TIMEOUT_SECONDS,
    ),
    operation="connect",
    timeout_seconds=OKX_DEX_WS_CONNECT_TIMEOUT_SECONDS,
)
```

Add helpers:

```python
async def _recv_message_with_heartbeat(self, websocket: Any) -> Any:
    while True:
        try:
            raw_message = await asyncio.wait_for(
                websocket.recv(),
                timeout=OKX_DEX_WS_IDLE_PING_SECONDS,
            )
        except TimeoutError as exc:
            await self._send_application_ping(websocket)
            try:
                raw_message = await asyncio.wait_for(
                    websocket.recv(),
                    timeout=OKX_DEX_WS_PONG_TIMEOUT_SECONDS,
                )
            except TimeoutError as pong_exc:
                raise OkxDexWsClientError("OKX DEX WS missing application pong") from pong_exc
        self.last_message_at_ms = _now_ms()
        if raw_message == "pong":
            self.last_pong_at_ms = self.last_message_at_ms
            continue
        return raw_message

async def _send_application_ping(self, websocket: Any) -> None:
    await websocket.send("ping")
    self.last_ping_at_ms = _now_ms()
```

- [ ] **Step 3: Classify messages before JSON data conversion**

Add helper:

```python
def _message_event(message: Any) -> str | None:
    if isinstance(message, dict):
        value = message.get("event")
        return str(value) if value is not None else None
    return None
```

Replace the body of `iter_price_info()` so it:

- calls `_recv_message_with_heartbeat`
- ignores `pong` inside the helper
- parses JSON only for non-pong messages
- raises recoverable reconnect on `notice`
- raises terminal error on auth/login code errors
- tracks data frame and tick counts

Use this control shape:

```python
while True:
    try:
        await self.ensure_connected()
        websocket = self._websocket
        if websocket is None:
            raise OkxDexWsClientError("OKX DEX WS connection unavailable")
        raw_message = await self._recv_message_with_heartbeat(websocket)
        message = json.loads(str(raw_message))
        event = _message_event(message)
        if event == "notice":
            await self._recover_connection(category="notice_reconnect", code=_text(message.get("code")))
            continue
        if event == "error":
            category = _error_category(message)
            await self._drop_connection(state="failed_terminal" if category == "auth_error" else "degraded_recoverable")
            raise OkxDexWsClientError(_error_message(message))
        rows = _rows_from_message(message)
        if rows:
            self.data_frame_count += 1
        for row in rows:
            update = _price_info_update_from_row(row)
            if update is None:
                continue
            self.tick_count += 1
            self._set_connection_state("streaming")
            yield update
    except asyncio.CancelledError:
        raise
    except OkxDexWsClientError:
        raise
    except Exception as exc:
        await self._recover_connection(category=_exception_category(exc))
        continue
```

- [ ] **Step 4: Persist desired subscriptions and replay after reconnect**

Change `replace_subscriptions()` to store `self._desired_args = desired_args` before network writes.

Add:

```python
async def _subscribe_desired_args(self) -> None:
    websocket = self._websocket
    if websocket is None or not self._desired_args:
        return
    await websocket.send(json.dumps({"op": "subscribe", "args": self._desired_args}))
    self._subscribed_args = {_arg_key(arg) for arg in self._desired_args}
```

After successful login in `ensure_connected()`, call `_subscribe_desired_args()` before setting `subscribed` when `self._desired_args` exists.

- [ ] **Step 5: Implement circuit breaker**

Add:

```python
def _raise_if_circuit_open(self) -> None:
    if self.connection_state != "circuit_open":
        return
    if time.monotonic() < self._circuit_open_until_monotonic:
        raise OkxDexWsClientError("OKX DEX WS circuit open")
    self._recoverable_failures = 0
    self._set_connection_state("disconnected")
```

Call `_raise_if_circuit_open()` at the start of `ensure_connected()`.

Add `_record_failure(category, code=None, terminal=False)` that:

- sets `last_error_category`
- sets `last_error_code`
- increments `_recoverable_failures` only for non-terminal failures
- sets `failed_terminal` for terminal failures
- sets `circuit_open` and `self._circuit_open_until_monotonic` when recoverable failures reach `OKX_DEX_WS_CIRCUIT_FAILURES`
- otherwise sets `degraded_recoverable`

- [ ] **Step 6: Keep adapter hard-cut simple**

In `src/parallax/app/runtime/provider_wiring/okx.py`, keep `OkxDexWebSocketMarketProviderAdapter` as the domain adapter but do not add a second legacy provider path. `iter_price_info()` should still delegate to the rewritten provider only.

- [ ] **Step 7: Run OKX tests**

Run:

```bash
uv run pytest tests/unit/test_okx_dex_ws_client.py -q
```

Expected:

- All OKX unit tests pass.
- Existing `test_okx_dex_ws_provider_no_longer_exposes_legacy_stream_price_info_method` still passes.

## Task 3: Market Stream Worker Degraded Result

**Files:**

- Modify: `src/parallax/domains/asset_market/runtime/market_tick_stream_worker.py`
- Modify: `tests/unit/test_market_tick_stream_worker.py`

- [ ] **Step 1: Add failing degraded provider tests**

Add:

```python
def test_market_tick_stream_worker_returns_degraded_when_provider_circuit_open() -> None:
    state = FakeSessionState()
    repos = FakeRepos(state, [tier_row(target_type="chain_token", target_id="solana:TokenA")])
    db = FakeDB(state, repos)
    stream = CircuitOpenDexMarketStream()
    worker = MarketTickStreamWorker(
        pool_bundle=db,
        stream_dex_market=stream,
        stream_cycle_seconds=0.001,
        clock=lambda: 1_800_000_000_100,
    )

    result = asyncio.run(worker.run_once())

    assert result.processed == 0
    assert result.failed == 0
    assert result.skipped == 1
    assert result.notes["degraded"] is True
    assert result.notes["provider_state"] == "circuit_open"
    assert result.notes["failure_category"] == "connect_timeout"
    assert repos.market_ticks.inserted == []
```

Add fake:

```python
class CircuitOpenDexMarketStream:
    async def replace_subscriptions(self, targets) -> None:
        raise RuntimeError("OKX DEX WS circuit open")

    async def iter_price_info(self):
        if False:
            yield

    def connection_state_payload(self):
        return {
            "provider": "okx_dex_ws",
            "state": "circuit_open",
            "last_error_category": "connect_timeout",
        }
```

- [ ] **Step 2: Replace provider exception surface with degraded WorkerResult**

Wrap `_stream_and_persist_ticks()` in `run_once()`:

```python
try:
    stream_result = await self._stream_and_persist_ticks(targets, stream_dex_market=stream_dex_market)
except Exception as exc:
    health = _provider_health(stream_dex_market)
    return WorkerResult(
        skipped=skipped_targets + len(targets),
        notes={
            "reason": "stream_provider_degraded",
            "degraded": True,
            "provider_state": str(health.get("state") or "failed"),
            "failure_category": str(health.get("last_error_category") or type(exc).__name__),
            "targets_selected": len(rows),
            "stream_targets": len(targets),
        },
    )
```

Add:

```python
def _provider_health(provider: Any) -> dict[str, Any]:
    payload = getattr(provider, "connection_state_payload", None)
    if not callable(payload):
        return {}
    try:
        value = payload()
    except Exception:
        return {}
    return value if isinstance(value, dict) else {}
```

- [ ] **Step 3: Change old error-surfacing test**

Replace `test_market_tick_stream_worker_flushes_collected_ticks_before_stream_error_surfaces` expectation from `pytest.raises` to:

```python
result = asyncio.run(worker.run_once())

assert result.processed == 0
assert result.skipped == 1
assert result.notes["degraded"] is True
assert len(repos.market_ticks.inserted) == 1
```

This preserves tick flush but stops treating recoverable provider drops as worker failure.

- [ ] **Step 4: Run worker tests**

Run:

```bash
uv run pytest tests/unit/test_market_tick_stream_worker.py -q
```

Expected:

- All tests pass.

## Task 4: Readiness Shows OKX Degraded Without Failing App

**Files:**

- Modify: `src/parallax/app/runtime/app.py`
- Modify: readiness tests found by `rg "_readiness_payload|provider_states" tests`

- [ ] **Step 1: Add readiness test**

Add or update a unit test:

```python
def test_readiness_allows_okx_ws_circuit_open_when_scheduler_and_db_are_healthy(monkeypatch):
    runtime = FakeRuntime(
        provider_state={
            "provider": "okx_dex_ws",
            "state": "circuit_open",
            "last_error_category": "connect_timeout",
        },
        unhealthy_reasons=[],
        db_ok=True,
    )

    payload, status_code = app_runtime._readiness_payload(runtime, now_ms=1_800_000_000_000)

    assert status_code == 200
    assert payload["ok"] is True
    assert payload["provider_states"]["okx_dex_ws"]["state"] == "circuit_open"
```

- [ ] **Step 2: Keep `_unhealthy_reasons()` provider-agnostic**

Do not add OKX provider state to `_unhealthy_reasons()`. Scheduler/db remain readiness authority. Provider state remains diagnostic payload.

- [ ] **Step 3: Run readiness tests**

Run:

```bash
uv run pytest tests/unit -q -k "readiness or status"
```

Expected:

- Readiness still fails for DB/scheduler unhealthy.
- Readiness does not fail solely because OKX WS is degraded/circuit-open.

## Task 5: Market Dirty Coalescing For Token Radar

**Files:**

- Modify: `src/parallax/domains/token_intel/repositories/token_radar_dirty_target_repository.py`
- Modify: `tests/unit/test_token_radar_dirty_target_repository.py`

- [ ] **Step 1: Add failing SQL contract tests**

Add tests:

```python
def test_enqueue_market_targets_uses_stable_payload_hash_without_now_ms() -> None:
    conn = FakeConn()

    TokenRadarDirtyTargetRepository(conn).enqueue_market_targets(
        [("chain_token", "solana:TokenA")],
        reason="market_tick_current_changed",
        now_ms=1_800_000_000_000,
        commit=False,
    )

    sql = " ".join(conn.sql.split())
    assert "%(now_ms)s::text" not in sql
    assert "market_dirty_min_interval_ms" in sql
    assert "MAX(features.latest_market_observed_at_ms)" in sql
```

```python
def test_enqueue_market_targets_skips_when_target_features_are_market_fresh() -> None:
    conn = FakeConn(rowcount=0)

    written = TokenRadarDirtyTargetRepository(conn).enqueue_market_targets(
        [("chain_token", "solana:TokenA")],
        reason="market_tick_current_changed",
        now_ms=1_800_000_000_000,
        commit=False,
    )

    assert written == 0
```

- [ ] **Step 2: Add market dirty interval constant**

At top of repository:

```python
MARKET_DIRTY_MIN_INTERVAL_MS = 60_000
```

- [ ] **Step 3: Rewrite `enqueue_market_targets()` SQL**

Change the `mapped` CTE flow to include:

```sql
latest_feature AS (
  SELECT
    features.target_type_key,
    features.identity_id,
    MAX(features.latest_market_observed_at_ms) AS latest_market_observed_at_ms
  FROM token_radar_target_features AS features
  JOIN mapped
    ON mapped.target_type_key = features.target_type_key
   AND mapped.identity_id = features.identity_id
  GROUP BY features.target_type_key, features.identity_id
),
eligible AS (
  SELECT mapped.*
  FROM mapped
  LEFT JOIN latest_feature
    ON latest_feature.target_type_key = mapped.target_type_key
   AND latest_feature.identity_id = mapped.identity_id
  WHERE latest_feature.latest_market_observed_at_ms IS NULL
     OR latest_feature.latest_market_observed_at_ms <= %(now_ms)s - %(market_dirty_min_interval_ms)s
)
```

Use `eligible` for the insert.

Change market dirty payload hash to:

```sql
md5(eligible.target_type_key || ':' || eligible.identity_id || ':' || %(dirty_reason)s)
```

Change `ON CONFLICT` to avoid timestamp-only updates:

```sql
ON CONFLICT(target_type_key, identity_id) DO UPDATE SET
  dirty_reason = EXCLUDED.dirty_reason,
  payload_hash = EXCLUDED.payload_hash,
  due_at_ms = LEAST(token_radar_dirty_targets.due_at_ms, EXCLUDED.due_at_ms),
  last_error = NULL
WHERE token_radar_dirty_targets.payload_hash IS DISTINCT FROM EXCLUDED.payload_hash
   OR token_radar_dirty_targets.due_at_ms > EXCLUDED.due_at_ms
   OR token_radar_dirty_targets.last_error IS NOT NULL
```

Pass:

```python
"market_dirty_min_interval_ms": MARKET_DIRTY_MIN_INTERVAL_MS,
```

- [ ] **Step 4: Run dirty target tests**

Run:

```bash
uv run pytest tests/unit/test_token_radar_dirty_target_repository.py -q
```

Expected:

- SQL contract tests pass.
- Existing dirty target enqueue/claim/done tests pass.

## Task 6: Token Radar Target Features No-Op Writes

**Files:**

- Modify: `src/parallax/domains/token_intel/repositories/token_radar_repository.py`
- Modify: `tests/unit/test_token_radar_repository.py`
- Modify: `tests/integration/test_token_radar_repository.py`

- [ ] **Step 1: Add failing unit test for target feature no-op**

Add:

```python
def test_upsert_target_feature_does_not_update_for_timestamp_only_rescore():
    conn = FakeConn()
    repo = TokenRadarRepository(conn)
    row = _valid_feature_row()

    repo.upsert_target_feature(
        projection_version="token-radar-v11-factor-alpha-gated",
        window="1h",
        scope="all",
        row=row,
        computed_at_ms=1_800_000_000_000,
        commit=False,
    )

    sql = " ".join(conn.sqls[-1].split())
    assert "last_scored_at_ms < excluded.last_scored_at_ms" not in sql
    assert "payload_hash IS DISTINCT FROM excluded.payload_hash" in sql
```

- [ ] **Step 2: Remove timestamp-only `WHERE` condition**

In `upsert_target_feature()`, replace:

```sql
WHERE token_radar_target_features.payload_hash IS DISTINCT FROM excluded.payload_hash
   OR token_radar_target_features.last_scored_at_ms < excluded.last_scored_at_ms
```

with:

```sql
WHERE token_radar_target_features.payload_hash IS DISTINCT FROM excluded.payload_hash
```

Return actual rowcount:

```python
cursor = self.conn.execute(..., payload)
...
return int(getattr(cursor, "rowcount", 0) or 0)
```

- [ ] **Step 3: Add integration idempotency test**

Add to `tests/integration/test_token_radar_repository.py`:

```python
def test_upsert_target_feature_unchanged_payload_does_not_advance_updated_at(tmp_path):
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repo = TokenRadarRepository(conn)
        row = _valid_factor_row()
        first = repo.upsert_target_feature(
            projection_version="token-radar-v11-factor-alpha-gated",
            window="1h",
            scope="all",
            row=row,
            computed_at_ms=1_800_000_000_000,
        )
        second = repo.upsert_target_feature(
            projection_version="token-radar-v11-factor-alpha-gated",
            window="1h",
            scope="all",
            row=row,
            computed_at_ms=1_800_000_060_000,
        )
        stored = conn.execute(
            """
            SELECT last_scored_at_ms, updated_at_ms
            FROM token_radar_target_features
            WHERE identity_id = 'asset-1'
            """
        ).fetchone()
    finally:
        conn.close()

    assert first == 1
    assert second == 0
    assert stored["last_scored_at_ms"] == 1_800_000_000_000
    assert stored["updated_at_ms"] == 1_800_000_000_000
```

- [ ] **Step 4: Run repository tests**

Run:

```bash
uv run pytest tests/unit/test_token_radar_repository.py tests/integration/test_token_radar_repository.py -q
```

Expected:

- New no-op target feature tests pass.

## Task 7: Token Radar Current Rows No Timestamp-Only Updates

**Files:**

- Modify: `src/parallax/domains/token_intel/repositories/token_radar_repository.py`
- Modify: `tests/unit/test_token_radar_repository.py`
- Modify: `tests/integration/test_token_radar_repository.py`

- [ ] **Step 1: Add failing integration test for unchanged current row**

Change existing `test_publish_rows_does_not_duplicate_history_or_audit_for_unchanged_payload` expectation:

```python
assert counts["current_computed_at_ms"] == 1_778_000_000_000
```

Add:

```sql
(SELECT count(*) FROM token_radar_target_first_seen WHERE last_seen_ms = 1778000060000) AS first_seen_timestamp_updates
```

Assert:

```python
assert counts["first_seen_timestamp_updates"] == 0
```

- [ ] **Step 2: Change `publish_rows()` to update current rows only on payload change**

In the `ON CONFLICT` for `token_radar_current_rows`, replace unconditional timestamp/rank/payload updates with payload-gated update:

```sql
DO UPDATE SET
  row_id = excluded.row_id,
  computed_at_ms = excluded.computed_at_ms,
  source_max_received_at_ms = excluded.source_max_received_at_ms,
  rank = excluded.rank,
  ...
  payload_hash = excluded.payload_hash,
  listed_at_ms = excluded.listed_at_ms,
  created_at_ms = excluded.created_at_ms
WHERE token_radar_current_rows.payload_hash IS DISTINCT FROM excluded.payload_hash
```

Keep the existing CASE expressions only if they are still needed after the `WHERE`; otherwise simplify them because the update now only runs for changed payloads.

- [ ] **Step 3: Track changed rows for history/audit/first-seen**

In `publish_rows()`, build:

```python
changed_rows: list[dict[str, Any]] = []
for row, previous in change_baselines:
    changed = previous is None or str(previous.get("payload_hash") or "") != str(row["payload_hash"])
    if changed:
        changed_rows.append(row)
```

Call:

```python
self.upsert_first_seen_batch(..., rows=changed_rows, ...)
```

instead of passing all `rows_to_insert`.

- [ ] **Step 4: Keep coverage as freshness source**

Do not make `token_radar_current_rows.computed_at_ms` advance for unchanged payloads. `token_radar_projection_coverage` is the projection freshness source after this change.

- [ ] **Step 5: Run current-row tests**

Run:

```bash
uv run pytest tests/unit/test_token_radar_repository.py tests/integration/test_token_radar_repository.py -q
```

Expected:

- Current row timestamp remains stable when payload is stable.
- Rank history and audit remain unchanged on no-op publish.
- First-seen table does not receive timestamp-only updates.

## Task 8: Pulse Reads Coverage Freshness Instead Of Current Row Timestamp

**Files:**

- Modify: `src/parallax/domains/pulse_lab/services/pulse_policy_evaluator.py`
- Modify: `tests/unit/domains/pulse_lab/test_pulse_policy_evaluator.py`

- [ ] **Step 1: Add failing test**

Add test where `token_radar_projection_coverage.computed_at_ms` is fresh while `token_radar_current_rows.computed_at_ms` is older:

```python
def test_pulse_policy_uses_projection_coverage_for_radar_freshness():
    conn = FakePulsePolicyConn(
        coverage_computed_at_ms=1_800_000_060_000,
        current_rows=[
            {
                "window": "1h",
                "scope": "all",
                "row_id": "row-1",
                "subject_key": "Asset:asset-1",
                "decision": "trade_candidate",
                "rank": 1,
                "computed_at_ms": 1_800_000_000_000,
                "source_max_received_at_ms": 1_800_000_000_000,
                "factor_snapshot_json": {"schema_version": "token_factor_snapshot_v3"},
                "source_event_ids_json": ["event-1"],
            }
        ],
    )

    rows = fetch_radar_rows(conn, now_ms=1_800_000_060_000, lookback_hours=1)

    assert len(rows) == 1
    assert rows[0]["row_id"] == "row-1"
```

- [ ] **Step 2: Change `fetch_radar_rows()` query**

Replace the first latest query with coverage:

```sql
SELECT computed_at_ms
FROM token_radar_projection_coverage
WHERE computed_at_ms >= %s
  AND computed_at_ms <= %s
  AND projection_version = %s
  AND "window" = %s
  AND scope = %s
  AND status = 'ready'
ORDER BY computed_at_ms DESC
LIMIT 1
```

Replace row fetch condition:

```sql
WHERE projection_version = %s
  AND "window" = %s
  AND scope = %s
```

Remove `AND computed_at_ms = %s`.

Return row `computed_at_ms` as the content timestamp; coverage timestamp remains freshness and does not need to be duplicated onto every row.

- [ ] **Step 3: Run pulse tests**

Run:

```bash
uv run pytest tests/unit/domains/pulse_lab/test_pulse_policy_evaluator.py -q
```

Expected:

- Pulse still sees fresh Radar rows when coverage is fresh and current row payload is unchanged.

## Task 9: Equity Payload Hash Migration

**Files:**

- Create: `src/parallax/platform/db/alembic/versions/20260524_0091_projection_churn_payload_hashes.py`
- Modify: `tests/unit/test_postgres_schema.py`
- Modify: `tests/integration/test_postgres_schema_runtime.py`

- [ ] **Step 1: Add migration**

Create migration:

```python
"""add payload hashes for projection churn suppression"""

from alembic import op

revision = "20260524_0091"
down_revision = "20260523_0090"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table in (
        "equity_event_page_rows",
        "equity_company_timeline_rows",
        "equity_event_alert_candidates",
        "equity_event_calendar_rows",
    ):
        op.execute(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS payload_hash TEXT NOT NULL DEFAULT ''")
        op.execute(f"CREATE INDEX IF NOT EXISTS idx_{table}_payload_hash ON {table}(payload_hash)")


def downgrade() -> None:
    for table in (
        "equity_event_calendar_rows",
        "equity_event_alert_candidates",
        "equity_company_timeline_rows",
        "equity_event_page_rows",
    ):
        op.execute(f"DROP INDEX IF EXISTS idx_{table}_payload_hash")
        op.execute(f"ALTER TABLE {table} DROP COLUMN IF EXISTS payload_hash")
```

- [ ] **Step 2: Update schema tests**

Add assertions that all four tables include `payload_hash TEXT NOT NULL`.

- [ ] **Step 3: Run schema tests**

Run:

```bash
uv run pytest tests/unit/test_postgres_schema.py tests/integration/test_postgres_schema_runtime.py -q
```

Expected:

- Migration chain validates.
- Runtime schema has payload hash columns.

## Task 10: Equity Source Upserts Stop Timestamp Churn

**Files:**

- Modify: `src/parallax/domains/equity_event_intel/repositories/equity_event_repository.py`
- Modify: `tests/integration/test_equity_event_repository.py`

- [ ] **Step 1: Add document duplicate no-op test**

Add:

```python
def test_upsert_event_document_duplicate_content_does_not_advance_updated_at(postgres_conn) -> None:
    with repository_session(postgres_conn) as repos:
        first = repos.equity_events.upsert_event_document(
            event_document_id="doc-1",
            provider_document_id="provider-doc-1",
            company_id="company-1",
            ticker="AAPL",
            cik="0000320193",
            source_id="sec:aapl",
            source_role="filing",
            document_type="filing",
            form_type="8-K",
            accession_number="0001",
            fiscal_period=None,
            document_url="https://example.test/doc",
            event_time_ms=1_800_000_000_000,
            discovered_at_ms=1_800_000_000_000,
            content_hash="hash-1",
            now_ms=1_800_000_000_000,
            commit=False,
        )
        second = repos.equity_events.upsert_event_document(
            event_document_id="doc-1",
            provider_document_id="provider-doc-1",
            company_id="company-1",
            ticker="AAPL",
            cik="0000320193",
            source_id="sec:aapl",
            source_role="filing",
            document_type="filing",
            form_type="8-K",
            accession_number="0001",
            fiscal_period=None,
            document_url="https://example.test/doc",
            event_time_ms=1_800_000_000_000,
            discovered_at_ms=1_800_000_060_000,
            content_hash="hash-1",
            now_ms=1_800_000_060_000,
            commit=False,
        )

    assert first["updated_at_ms"] == 1_800_000_000_000
    assert second["updated_at_ms"] == 1_800_000_000_000
    assert second["status"] == "duplicate"
```

- [ ] **Step 2: Add company event duplicate no-op test**

Add a test that calls `upsert_company_event()` twice with identical public fields and later `now_ms`, then asserts `updated_at_ms` remains the first value.

- [ ] **Step 3: Implement CTE no-op upserts**

For `upsert_event_document()` and `upsert_company_event()`, replace unconditional `ON CONFLICT DO UPDATE` timestamp mutation with CTE shape:

```sql
WITH upserted AS (
  INSERT ...
  ON CONFLICT (...) DO UPDATE SET ...
  WHERE existing.public_field IS DISTINCT FROM EXCLUDED.public_field
     OR existing.content_hash IS DISTINCT FROM EXCLUDED.content_hash
  RETURNING *, CASE WHEN xmax = 0 THEN 'inserted' ELSE 'updated' END AS status
),
existing AS (
  SELECT *, 'duplicate' AS status
  FROM table
  WHERE primary_key = %s
    AND NOT EXISTS (SELECT 1 FROM upserted)
)
SELECT * FROM upserted
UNION ALL
SELECT * FROM existing
```

For documents, public fields are:

- `company_id`
- `ticker`
- `cik`
- `source_id`
- `source_role`
- `document_type`
- `form_type`
- `accession_number`
- `fiscal_period`
- `document_url`
- `event_time_ms`
- `content_hash`

For company events, public fields are:

- `company_id`
- `ticker`
- `primary_document_id`
- `event_type`
- `priority`
- `source_role`
- `fiscal_period`
- `event_time_ms`
- `lifecycle_status`
- `validation_status`
- `summary`

- [ ] **Step 4: Run equity repository tests**

Run:

```bash
uv run pytest tests/integration/test_equity_event_repository.py -q
```

Expected:

- Duplicate source fetch no longer advances `updated_at_ms`.

## Task 11: Equity Read Models Use Payload Hash Upsert, Not Replace Delete/Insert

**Files:**

- Modify: `src/parallax/domains/equity_event_intel/services/page_projection.py`
- Modify: `src/parallax/domains/equity_event_intel/repositories/equity_event_repository.py`
- Modify: `tests/unit/domains/equity_event_intel/test_page_projection.py`
- Modify: `tests/integration/test_equity_event_repository.py`
- Modify: `tests/integration/test_equity_event_workers.py`

- [ ] **Step 1: Add payload hash to page projection builders**

In `page_projection.py`, add:

```python
import hashlib
import json


def _projection_payload_hash(payload: Mapping[str, Any]) -> str:
    stable = {
        key: value
        for key, value in payload.items()
        if key not in {"computed_at_ms"}
    }
    encoded = json.dumps(stable, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()
```

At the end of each builder for page, timeline, alert, and calendar rows:

```python
row["payload_hash"] = _projection_payload_hash(row)
```

- [ ] **Step 2: Add unit tests for stable hash**

Add:

```python
def test_equity_event_page_row_payload_hash_ignores_computed_at_ms():
    first = build_equity_event_page_row(..., computed_at_ms=1_800_000_000_000)
    second = build_equity_event_page_row(..., computed_at_ms=1_800_000_060_000)

    assert first["payload_hash"] == second["payload_hash"]
```

Use existing fixtures in `tests/unit/domains/equity_event_intel/test_page_projection.py` for the `...` payloads.

- [ ] **Step 3: Replace `replace_page_rows()` delete-first logic**

Change `replace_page_rows()`:

- Delete only scoped rows not present in incoming row ids:

```sql
DELETE FROM equity_event_page_rows
WHERE company_event_id = ANY(%s::text[])
  AND NOT (row_id = ANY(%s::text[]))
```

- Insert/update each payload with:

```sql
ON CONFLICT (row_id) DO UPDATE SET
  company_event_id = EXCLUDED.company_event_id,
  story_id = EXCLUDED.story_id,
  company_id = EXCLUDED.company_id,
  ticker = EXCLUDED.ticker,
  company_name = EXCLUDED.company_name,
  event_type = EXCLUDED.event_type,
  priority = EXCLUDED.priority,
  source_role = EXCLUDED.source_role,
  latest_event_at_ms = EXCLUDED.latest_event_at_ms,
  lifecycle_status = EXCLUDED.lifecycle_status,
  headline = EXCLUDED.headline,
  summary = EXCLUDED.summary,
  facts_json = EXCLUDED.facts_json,
  documents_json = EXCLUDED.documents_json,
  brief_json = EXCLUDED.brief_json,
  computed_at_ms = EXCLUDED.computed_at_ms,
  projection_version = EXCLUDED.projection_version,
  payload_hash = EXCLUDED.payload_hash
WHERE equity_event_page_rows.payload_hash IS DISTINCT FROM EXCLUDED.payload_hash
   OR equity_event_page_rows.projection_version IS DISTINCT FROM EXCLUDED.projection_version
```

- [ ] **Step 4: Replace `replace_company_timeline_rows()` delete-first logic**

Use the same pattern:

```sql
DELETE FROM equity_company_timeline_rows
WHERE (company_id = ANY(%s::text[]) OR company_event_id = ANY(%s::text[]))
  AND NOT (row_id = ANY(%s::text[]))
```

Then `ON CONFLICT (row_id) DO UPDATE ... WHERE payload_hash IS DISTINCT`.

- [ ] **Step 5: Apply same hash-gated upsert to alert and calendar rows**

Update `replace_alert_candidates()` and `replace_calendar_rows()` so:

- they delete stale scoped rows not present in incoming row ids
- they do not delete matching rows before insert
- their `ON CONFLICT` update runs only when `payload_hash` or `projection_version` changes

- [ ] **Step 6: Add integration no-churn tests**

Add to `tests/integration/test_equity_event_repository.py`:

```python
def test_equity_event_replace_page_rows_does_not_delete_or_update_identical_payload(postgres_conn) -> None:
    with repository_session(postgres_conn) as repos:
        row = _page_row(company_event_id="event-1", computed_at_ms=1_800_000_000_000)
        repos.equity_events.replace_page_rows(rows=[row], company_event_ids=("event-1",))
        second = {**row, "computed_at_ms": 1_800_000_060_000}
        repos.equity_events.replace_page_rows(rows=[second], company_event_ids=("event-1",))
        stored = repos.conn.execute(
            """
            SELECT computed_at_ms, payload_hash
            FROM equity_event_page_rows
            WHERE row_id = %s
            """,
            (row["row_id"],),
        ).fetchone()

    assert stored["computed_at_ms"] == 1_800_000_000_000
```

Add equivalent timeline-row test.

- [ ] **Step 7: Run equity projection tests**

Run:

```bash
uv run pytest \
  tests/unit/domains/equity_event_intel/test_page_projection.py \
  tests/integration/test_equity_event_repository.py \
  tests/integration/test_equity_event_workers.py \
  -q
```

Expected:

- Stable projections do not delete/reinsert or update timestamp-only rows.
- Legitimate source content changes still rebuild page/timeline/alert/calendar rows.

## Task 12: Token Radar End-To-End Idempotency

**Files:**

- Modify: `tests/integration/test_token_radar_idempotency.py`

- [ ] **Step 1: Add high-frequency market tick idempotency test**

Add a test that:

- seeds one resolved token target
- inserts multiple market ticks within `MARKET_DIRTY_MIN_INTERVAL_MS`
- runs `TokenRadarProjection.rebuild_dirty_targets()` twice
- asserts second run does not update current rows or first-seen rows when no payload changed

Use SQL counters:

```sql
SELECT
  (SELECT count(*) FROM token_radar_rank_history) AS rank_history_count,
  (SELECT count(*) FROM token_radar_snapshot_audit) AS snapshot_audit_count,
  (SELECT count(*) FROM token_radar_current_rows) AS current_count,
  (SELECT max(computed_at_ms) FROM token_radar_current_rows) AS current_computed_at_ms,
  (SELECT max(updated_at_ms) FROM token_radar_target_first_seen) AS first_seen_updated_at_ms
```

Assertions:

```python
assert after_second["rank_history_count"] == after_first["rank_history_count"]
assert after_second["snapshot_audit_count"] == after_first["snapshot_audit_count"]
assert after_second["current_count"] == after_first["current_count"]
assert after_second["current_computed_at_ms"] == after_first["current_computed_at_ms"]
assert after_second["first_seen_updated_at_ms"] == after_first["first_seen_updated_at_ms"]
```

- [ ] **Step 2: Run idempotency tests**

Run:

```bash
uv run pytest tests/integration/test_token_radar_idempotency.py -q
```

Expected:

- Repeated market ticks inside the coalescing interval do not amplify into repeated read-model writes.

## Task 13: Remove Or Update Tests That Encode Old Churn Contract

**Files:**

- Modify: any tests failing because they expected timestamp-only updates.

- [ ] **Step 1: Run targeted suite**

Run:

```bash
uv run pytest \
  tests/unit/test_okx_dex_ws_client.py \
  tests/unit/test_market_tick_stream_worker.py \
  tests/unit/test_token_radar_dirty_target_repository.py \
  tests/unit/test_token_radar_repository.py \
  tests/integration/test_token_radar_repository.py \
  tests/integration/test_token_radar_idempotency.py \
  tests/unit/domains/pulse_lab/test_pulse_policy_evaluator.py \
  tests/unit/domains/equity_event_intel/test_page_projection.py \
  tests/integration/test_equity_event_repository.py \
  tests/integration/test_equity_event_workers.py \
  -q
```

Expected:

- Failures should be limited to tests that assumed timestamp-only churn.

- [ ] **Step 2: Update stale expectations**

Allowed expectation updates:

- `computed_at_ms` remains old when payload hash is unchanged.
- `updated_at_ms` remains old when payload hash is unchanged.
- changed payload still writes new timestamps.
- coverage tables, not current rows, indicate projection freshness.

Forbidden expectation updates:

- Do not accept duplicate history/audit rows.
- Do not accept delete-first page/timeline behavior.
- Do not accept OKX provider exceptions as normal worker failure.

## Task 14: Live Smoke Command

**Files:**

- Create: `scripts/smoke_okx_ws.py`
- Modify: `docs/SETUP.md` only if the script becomes an operator-facing documented command.

- [ ] **Step 1: Add smoke script**

Create a script that:

- loads active settings with the same config path resolution as `uv run parallax config`
- never prints secrets
- selects top N stream targets from DB
- connects/login/subscribes to OKX WS
- waits for data or sends app `ping`
- prints only redacted status and counts

Command:

```bash
uv run python scripts/smoke_okx_ws.py --limit 10 --timeout-seconds 30
```

Expected output shape:

```text
config_path=/Users/qinghuan/.parallax/config.yaml
workers_config_path=/Users/qinghuan/.parallax/workers.yaml
credentials_present=true
targets=10
login_ok=true
subscribe_acked=10
data_frames>=1
application_pong=true
```

- [ ] **Step 2: Run smoke only when credentials are present**

If `uv run parallax config` reports missing OKX WS credentials, skip live smoke and record skip reason in verification.

## Task 15: Full Verification

**Files:**

- Write verification notes in this plan's Verification section or in `docs/superpowers/plans/active/2026-05-24-okx-ws-and-projection-churn-root-fix-cn-verification.md`.

- [ ] **Step 1: Run full check**

Run:

```bash
make check-all
```

Expected:

- Exit 0.

- [ ] **Step 2: Rebuild docker**

Run:

```bash
docker compose up -d --build --force-recreate app
```

Expected:

- App starts.
- Postgres remains healthy.

- [ ] **Step 3: Check readiness and provider status**

Run:

```bash
curl -s http://127.0.0.1:8765/readyz
curl -s http://127.0.0.1:8765/api/status
```

Expected:

- `ok=true` when DB/scheduler are healthy.
- `provider_states.okx_dex_ws` includes heartbeat/circuit fields.
- If OKX WS is degraded and market poll is healthy, readiness remains ok.

- [ ] **Step 4: Measure DB churn deltas**

Before a 10 minute run:

```sql
SELECT relname, n_tup_ins, n_tup_upd, n_tup_del
FROM pg_stat_user_tables
WHERE relname IN (
  'token_radar_current_rows',
  'token_radar_target_features',
  'token_radar_target_first_seen',
  'token_radar_dirty_targets',
  'token_radar_rank_history_202605',
  'token_radar_snapshot_audit_202605',
  'equity_event_page_rows',
  'equity_company_timeline_rows',
  'equity_event_alert_candidates',
  'equity_event_calendar_rows'
)
ORDER BY relname;
```

After 10 minutes, run the same query.

Expected:

- Stable duplicate equity fetch cycles produce zero or near-zero `equity_event_page_rows` / `equity_company_timeline_rows` delete deltas.
- Token Radar unchanged publish cycles do not advance `token_radar_current_rows.n_tup_upd` linearly with every worker cycle.
- `token_radar_target_first_seen.n_tup_upd` no longer grows on unchanged publish.
- Rank history/audit grows only on rank enter/exit/decision/payload changes, not every refresh.

- [ ] **Step 5: Run OKX live smoke**

Run:

```bash
uv run python scripts/smoke_okx_ws.py --limit 10 --timeout-seconds 30
```

Expected:

- Credentials are reported as present booleans only.
- Login succeeds.
- Subscribe succeeds.
- App-level `ping`/`pong` succeeds.
- Data frames are received, or timeout is reported as provider-data-timeout with heartbeat still healthy.

## Self-Review Checklist

- [ ] Spec G1: app-level heartbeat is implemented by Task 1 and Task 2.
- [ ] Spec G2: close/timeout/notice/error classification is implemented by Task 2.
- [ ] Spec G3: reconnect resubscribe is implemented by Task 2.
- [ ] Spec G4: bounded worker cycle is implemented by Task 3.
- [ ] Spec G5: degraded WS does not fail app readiness by Task 4.
- [ ] Spec G6: health payload is implemented by Task 2 and surfaced by Task 4.
- [ ] Spec G7 and user scope extension: projection CPU write amplification is handled by Tasks 5 through 12.
- [ ] No compatibility path keeps old OKX naked recv.
- [ ] No timestamp-only update path remains for the named projection tables.
- [ ] `make check-all` passes before completion is claimed.

## Verification

To be filled during execution. Required final evidence:

- `make check-all` full output.
- Targeted pytest outputs.
- Docker rebuild output.
- `/readyz` and `/api/status` redacted payload summary.
- 10 minute `pg_stat_user_tables` before/after deltas.
- OKX live smoke output with no secrets.
