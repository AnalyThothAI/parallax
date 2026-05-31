from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src" / "gmgn_twitter_intel"
NOTIFICATION_RUNTIME_FILES = (
    SRC / "platform/config/settings.py",
    SRC / "domains/notifications/services/notification_rules.py",
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
            f"{path.relative_to(ROOT)} contains {token!r}"
            for token in BANNED_5MIN_NOTIFICATION_TOKENS
            if token in text
        )

    assert violations == []
