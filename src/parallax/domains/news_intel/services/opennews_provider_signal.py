from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def provider_signal_from_opennews_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    ai_rating_value = payload.get("aiRating")
    ai_rating: Mapping[str, Any] = ai_rating_value if isinstance(ai_rating_value, Mapping) else {}
    signal = _optional_text(ai_rating.get("signal"))
    score = _optional_int(ai_rating.get("score"))
    grade = _optional_text(ai_rating.get("grade"))
    status = _optional_text(ai_rating.get("status"))
    if status == "done" or signal or score is not None or grade:
        return {
            "source": "provider",
            "provider": "opennews",
            "status": "ready" if status == "done" or score is not None else "partial",
            "direction": _direction(signal),
            "label_zh": _label_zh(signal),
            "signal": signal,
            "score": score,
            "grade": grade,
            "summary_zh": _optional_text(ai_rating.get("summary")),
            "summary_en": _optional_text(ai_rating.get("enSummary")),
            "method": "opennews.aiRating",
        }
    return {
        "source": "provider",
        "provider": "opennews",
        "status": "partial",
        "direction": "neutral",
        "label_zh": "中性",
        "signal": None,
        "score": None,
        "grade": None,
        "summary_zh": None,
        "summary_en": None,
        "method": "opennews.partial",
    }


def provider_token_impacts_from_opennews_payload(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    coins = payload.get("coins")
    if not isinstance(coins, list):
        return []
    impacts: list[dict[str, Any]] = []
    for coin in coins:
        if not isinstance(coin, Mapping):
            continue
        symbol = _optional_text(coin.get("symbol"))
        if not symbol:
            continue
        impacts.append(
            {
                "symbol": symbol.upper(),
                "market_type": _optional_text(coin.get("market_type")),
                "score": _optional_int(coin.get("score")),
                "signal": _optional_text(coin.get("signal")),
                "grade": _optional_text(coin.get("grade")),
            }
        )
    return impacts


def _direction(signal: str | None) -> str:
    if signal == "long":
        return "bullish"
    if signal == "short":
        return "bearish"
    return "neutral"


def _label_zh(signal: str | None) -> str:
    if signal == "long":
        return "利好"
    if signal == "short":
        return "利空"
    return "中性"


def _optional_text(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


__all__ = ["provider_signal_from_opennews_payload", "provider_token_impacts_from_opennews_payload"]
