from __future__ import annotations

import secrets
from pathlib import Path
from typing import Any

from parallax.platform.config.settings import load_settings, write_default_config
from parallax.platform.paths.runtime_paths import config_path, workers_config_path


def handle_init(args: object) -> tuple[int, dict[str, Any]]:
    existed = config_path().exists() and workers_config_path().exists()
    path = write_default_config(force=args.force)
    password_path = _ensure_postgres_password_file(path.parent)
    return (
        0,
        {
            "ok": True,
            "data": {
                "config_path": str(path),
                "workers_config_path": str(workers_config_path(path.parent)),
                "app_home": str(path.parent),
                "postgres_password_file": str(password_path),
                "created": args.force or not existed,
            },
        },
    )


def handle_config(_args: object) -> tuple[int, dict[str, Any]]:
    settings = load_settings(require_ws_token=False)
    return (
        0,
        {
            "ok": True,
            "data": {
                "handles": list(settings.handles),
                "handle_count": len(settings.handles),
                "config_path": str(settings.app_home / "config.yaml"),
                "workers_config_path": str(workers_config_path(settings.app_home)),
                "api": {
                    "host": settings.api_host,
                    "port": settings.api_port,
                    "replay_limit": settings.replay_limit,
                    "ws_token_configured": bool(settings.ws_token),
                },
                "store": {
                    "app_home": str(settings.app_home),
                    "engine": "postgresql",
                    "postgres_dsn": _redacted_postgres_dsn(settings.postgres_dsn),
                    "postgres_password_file": (
                        str(settings.postgres_password_file) if settings.postgres_password_file else None
                    ),
                    "pool_min_size": settings.postgres_pool_min_size,
                    "pool_max_size": settings.postgres_pool_max_size,
                    "log_file": str(settings.log_file),
                },
                "upstream": {
                    "channels": list(settings.upstream_channels),
                    "chains": list(settings.upstream_chains),
                },
                "agent_execution": {
                    "llm_configured": settings.llm_configured,
                    "provider": settings.llm_provider,
                    "model": settings.agent_runtime_default_model,
                    "base_url": settings.llm_base_url,
                    "backend": "litellm_sdk",
                    "trace_enabled": settings.llm_trace_enabled,
                    "trace_export_configured": settings.llm_trace_export_configured,
                    "trace_include_sensitive_data": settings.llm_trace_include_sensitive_data,
                },
                "providers": {
                    "gmgn": {
                        "configured": settings.gmgn_configured,
                        "openapi_base_url": settings.gmgn_openapi_base_url,
                        "timeout_seconds": settings.gmgn_timeout_seconds,
                        "token_info_cache_ttl_seconds": settings.gmgn_token_info_cache_ttl_seconds,
                    },
                    "okx": {
                        "dex_base_url": settings.okx_dex_base_url,
                        "dex_chain_indexes": list(settings.okx_dex_chain_indexes),
                        "dex_configured": settings.okx_dex_configured,
                    },
                    "binance": {
                        "enabled": settings.binance_enabled,
                        "web3_base_url": settings.binance_web3_base_url,
                        "cex_profile_base_url": settings.binance_cex_profile_base_url,
                        "usdm_futures_base_url": settings.binance_usdm_futures_base_url,
                        "cex_universe_quote_symbol": settings.binance_cex_universe_quote_symbol,
                        "cex_universe_contract_type": settings.binance_cex_universe_contract_type,
                        "timeout_seconds": settings.binance_timeout_seconds,
                    },
                    "macrodata": {
                        "enabled": settings.macrodata_enabled,
                        "fred_api_key_env": settings.macrodata_fred_api_key_env,
                        "fred_api_key_configured": settings.macrodata_fred_api_key_configured,
                    },
                },
                "notifications": {
                    "enabled": settings.notifications.enabled,
                    "candidate_limit": settings.notifications.candidate_limit,
                    "retention_days": settings.notifications.retention_days,
                    "rules": {
                        rule_id: rule.model_dump(mode="json") for rule_id, rule in settings.notifications.rules.items()
                    },
                    "channels": {
                        channel_id: {
                            "enabled": channel.enabled,
                            "provider": channel.provider,
                            "url_configured": bool(channel.url),
                            "min_severity": channel.min_severity,
                        }
                        for channel_id, channel in settings.notifications.channels.items()
                    },
                },
                "workers": settings.workers.model_dump(mode="json"),
            },
        },
    )


def _ensure_postgres_password_file(app_home: Path) -> Path:
    path = app_home / "postgres_password"
    if not path.exists():
        path.write_text(secrets.token_urlsafe(32) + "\n", encoding="utf-8")
        path.chmod(0o600)
    return path


def _redacted_postgres_dsn(dsn: str) -> str:
    from psycopg import conninfo

    try:
        parts = conninfo.conninfo_to_dict(dsn)
        if parts.get("password"):
            parts["password"] = "********"
        return conninfo.make_conninfo(**parts)
    except Exception:
        return dsn
