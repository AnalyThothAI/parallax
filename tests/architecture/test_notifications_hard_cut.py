from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src" / "parallax"
NOTIFICATION_RUNTIME_FILES = (
    SRC / "platform/config/settings.py",
    SRC / "domains/notifications/services/notification_rules.py",
    SRC / "domains/notifications/runtime/notification_worker.py",
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

    assert "_public_notification_payload(" in text
    assert 'payload["payload"] = _json_loads(payload.pop("payload_json"' not in text
    assert "news_high_signal" in text
    assert "_NEWS_HIGH_SIGNAL_PAYLOAD_KEYS" in text
