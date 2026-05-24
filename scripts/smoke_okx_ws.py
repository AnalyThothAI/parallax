from __future__ import annotations

import argparse
import asyncio
import json
import time
from collections.abc import Mapping, Sequence
from typing import Any

from gmgn_twitter_intel.app.runtime.provider_wiring.okx import okx_chain_index
from gmgn_twitter_intel.integrations.okx.dex_ws_client import OkxDexWebSocketMarketProvider
from gmgn_twitter_intel.platform.config.settings import Settings, load_settings
from gmgn_twitter_intel.platform.db.postgres_client import connect_postgres, with_password_from_file
from gmgn_twitter_intel.platform.paths.runtime_paths import config_path, workers_config_path


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Redacted OKX DEX WebSocket smoke check")
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--timeout-seconds", type=float, default=30.0)
    args = parser.parse_args(argv)

    settings = load_settings(require_ws_token=False)
    active_config_path = config_path(settings.app_home)
    active_workers_path = workers_config_path(settings.app_home)
    credentials_present = bool(settings.okx_dex_ws_configured)

    print(f"config_path={active_config_path}")
    print(f"workers_config_path={active_workers_path}")
    print(f"credentials_present={_bool(credentials_present)}")

    if not credentials_present:
        print("skipped=missing_okx_dex_ws_credentials")
        return 0

    targets = _load_targets(settings, limit=max(1, int(args.limit)))
    print(f"targets={len(targets)}")
    if not targets:
        print("skipped=no_tier1_chain_token_targets")
        return 0

    try:
        result = asyncio.run(_smoke(settings, targets=targets, timeout_seconds=max(1.0, args.timeout_seconds)))
    except Exception as exc:
        print("login_ok=false")
        print("subscribe_acked=0")
        print("data_frames=0")
        print("application_pong=false")
        print(f"error_class={type(exc).__name__}")
        return 1

    for key, value in result.items():
        print(f"{key}={value}")
    return 0 if result.get("login_ok") == "true" and result.get("application_pong") == "true" else 1


def _load_targets(settings: Settings, *, limit: int) -> list[dict[str, str]]:
    dsn = with_password_from_file(settings.postgres_dsn, settings.postgres_password_file)
    with connect_postgres(dsn, connect_timeout_seconds=settings.postgres_connect_timeout_seconds) as conn:
        rows = conn.execute(
            """
            SELECT target_id
              FROM token_capture_tier
             WHERE tier = 1
               AND target_type = 'chain_token'
             ORDER BY score DESC, updated_at_ms DESC, target_id ASC
             LIMIT %s
            """,
            (limit,),
        ).fetchall()
    targets: list[dict[str, str]] = []
    for row in rows:
        target = _target_from_id(str(row["target_id"]))
        if target is not None:
            targets.append(target)
    return targets


def _target_from_id(target_id: str) -> dict[str, str] | None:
    if ":" not in target_id:
        return None
    chain_id, address = target_id.rsplit(":", 1)
    chain_index = okx_chain_index(chain_id)
    if not chain_index or not address:
        return None
    return {"chainIndex": chain_index, "tokenContractAddress": address.strip()}


async def _smoke(
    settings: Settings,
    *,
    targets: list[dict[str, str]],
    timeout_seconds: float,
) -> dict[str, str]:
    provider = OkxDexWebSocketMarketProvider(
        url=settings.okx_dex_ws_url,
        api_key=settings.okx_dex_api_key or "",
        secret_key=settings.okx_dex_secret_key or "",
        passphrase=settings.okx_dex_passphrase or "",
        subscription_limit=len(targets),
    )
    data_frames = 0
    try:
        await asyncio.wait_for(provider.replace_subscriptions(targets), timeout=timeout_seconds)
        application_pong = await _send_application_ping(provider, timeout_seconds=min(5.0, timeout_seconds))
        data_frames = await _wait_for_data(provider, timeout_seconds=timeout_seconds)
        state = provider.connection_state_payload()
        return {
            "login_ok": "true",
            "subscribe_acked": str(state.get("acked_subscription_count") or 0),
            "data_frames": str(max(data_frames, int(state.get("data_frame_count") or 0))),
            "application_pong": _bool(application_pong or bool(state.get("last_pong_at_ms"))),
            "provider_state": str(state.get("state") or ""),
            "last_error_category": str(state.get("last_error_category") or ""),
            "reconnect_count": str(state.get("reconnect_count") or 0),
        }
    finally:
        await provider.aclose()


async def _send_application_ping(provider: OkxDexWebSocketMarketProvider, *, timeout_seconds: float) -> bool:
    websocket = getattr(provider, "_websocket", None)
    if websocket is None:
        return False
    provider.last_ping_at_ms = _now_ms()
    await websocket.send("ping")
    deadline = time.monotonic() + max(0.1, timeout_seconds)
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return False
        raw = await asyncio.wait_for(websocket.recv(), timeout=remaining)
        provider.last_message_at_ms = _now_ms()
        if str(raw).strip().lower() == "pong":
            provider.last_pong_at_ms = provider.last_message_at_ms
            return True
        _count_data_frame(provider, raw)


async def _wait_for_data(provider: OkxDexWebSocketMarketProvider, *, timeout_seconds: float) -> int:
    count = 0
    iterator = provider.iter_price_info().__aiter__()
    deadline = time.monotonic() + max(0.1, timeout_seconds)
    while count < 1:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        try:
            await asyncio.wait_for(iterator.__anext__(), timeout=remaining)
        except TimeoutError:
            break
        count += 1
    return count


def _count_data_frame(provider: OkxDexWebSocketMarketProvider, raw: Any) -> None:
    try:
        message = json.loads(str(raw))
    except json.JSONDecodeError:
        return
    if not isinstance(message, Mapping):
        return
    if message.get("event"):
        return
    if message.get("data") or message.get("arg"):
        provider.data_frame_count += 1


def _bool(value: bool) -> str:
    return "true" if value else "false"


def _now_ms() -> int:
    return int(time.time() * 1000)


if __name__ == "__main__":
    raise SystemExit(main())
