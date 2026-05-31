from __future__ import annotations

import pytest
from pydantic import ValidationError

from parallax.domains.news_intel.types.news_item_brief import NewsItemBriefPayload


def test_news_item_brief_key_points_are_bounded_text() -> None:
    with pytest.raises(ValidationError):
        NewsItemBriefPayload(
            status="ready",
            direction="bullish",
            decision_class="watch",
            summary_zh="事件摘要",
            market_read_zh="市场解读",
            bull_view={"strength": "moderate", "thesis_zh": "x" * 301, "evidence_refs": ["item:title"]},
            bear_view={"strength": "absent", "thesis_zh": "", "evidence_refs": []},
            affected_assets=[],
            watch_triggers=[],
            invalidation_conditions=[],
            data_gaps=[],
            evidence_refs=["item:title"],
        )


def test_news_item_brief_payload_rejects_legacy_bull_bear_view_shape() -> None:
    with pytest.raises(ValidationError):
        NewsItemBriefPayload(
            status="ready",
            direction="bullish",
            decision_class="watch",
            summary_zh="事件摘要",
            market_read_zh="市场解读",
            bull_bear_view={"bull": "legacy", "bear": "legacy"},
            bull_view={"strength": "moderate", "thesis_zh": "利多叙事", "evidence_refs": ["item:title"]},
            bear_view={"strength": "absent", "thesis_zh": "", "evidence_refs": []},
            affected_assets=[],
            watch_triggers=[],
            invalidation_conditions=[],
            data_gaps=[],
            evidence_refs=["item:title"],
        )
