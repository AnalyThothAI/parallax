from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from collections.abc import Mapping, Sequence
from typing import Any

from psycopg.types.json import Jsonb

from parallax.domains.news_intel.types import NewsSourceConfig
from parallax.domains.news_intel.types.news_canonical_identity import (
    PROVIDER_GLOBAL_ARTICLE_ID_TYPES,
    CanonicalIdentity,
    provider_global_article_key,
)
from parallax.domains.news_intel.types.news_extraction import NewsEntity, NewsFactCandidate, NewsTokenMention
from parallax.domains.news_intel.types.news_item_agent_admission import NewsItemAgentAdmission
from parallax.domains.news_intel.types.news_market_scope import NewsMarketScope
from parallax.domains.news_intel.types.news_material_identity import (
    material_title_fingerprint,
    material_title_is_eligible,
    provider_symbol_set,
    symbol_sets_compatible,
)
from parallax.domains.news_intel.types.news_story_identity import NewsStoryIdentity
from parallax.domains.news_intel.types.news_url_identity import url_identity_kind
from parallax.domains.news_intel.types.source_classification import normalize_string_tuple
from parallax.platform.current_read_model_payload_hash import stable_current_payload_hash
from parallax.platform.db.write_contract import expect_mutation_count, returning_mutation_count
from parallax.platform.validation import require_nonnegative_int, require_positive_int

_REDACTED = "<redacted>"
_SECRET_ERROR_KEYS = (
    "api[_-]?key",
    "access[_-]?token",
    "refresh[_-]?token",
    "bearer[_-]?token",
    "token",
    "secret",
    "authorization",
    "cookie",
    "key",
    "password",
    "passphrase",
)
_SECRET_ERROR_KEY_PATTERN = "|".join(_SECRET_ERROR_KEYS)
_SECRET_QUERY_RE = re.compile(
    rf"([?&](?:{_SECRET_ERROR_KEY_PATTERN})=)"
    r"[^&#\s]+",
    re.IGNORECASE,
)
_SECRET_KEY_VALUE_RE = re.compile(
    rf"((?<![A-Za-z0-9_])(?:{_SECRET_ERROR_KEY_PATTERN})\s*[:=]\s*)([\"']?)[^\"'\s,;}}&]+([\"']?)",
    re.IGNORECASE,
)
_SECRET_QUOTED_KEY_VALUE_RE = re.compile(
    rf"((?<![A-Za-z0-9_])(?:{_SECRET_ERROR_KEY_PATTERN})\s*[:=]\s*)([\"']).*?\2",
    re.IGNORECASE,
)
_SECRET_HEADER_RE = re.compile(r"\b(authorization|cookie)\s*:\s*[^\r\n]+", re.IGNORECASE)
_BEARER_RE = re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]+", re.IGNORECASE)
_URL_USERINFO_RE = re.compile(r"([a-z][a-z0-9+.-]*://)[^/@\s]+@", re.IGNORECASE)
_CHECK_QUOTED_VALUE_RE = re.compile(r"'((?:''|[^'])*)'(?:\s*::\s*[A-Za-z_][A-Za-z0-9_]*)?")
_PUBLICATION_METADATA_FIELDS = {"computed_at_ms", "updated_at_ms", "projected_at_ms", "payload_hash"}
_NEWS_PAGE_SIGNAL_SQL = "LOWER(signal_json -> 'display_signal' ->> 'direction') = %s"
_MACRO_EVENT_FLOW_FIELDS = (
    "window",
    "window_label",
    "severity",
    "severity_label",
    "category",
    "category_label",
    "impact",
    "impact_label",
    "watch",
)
_NEWS_ITEM_WORKER_COLUMNS = (
    "news_item_id",
    "provider_item_id",
    "source_id",
    "source_domain",
    "canonical_url",
    "title",
    "summary",
    "body_text",
    "language",
    "published_at_ms",
    "fetched_at_ms",
    "content_hash",
    "title_fingerprint",
    "lifecycle_status",
    "processing_attempts",
    "processing_error",
    "processed_at_ms",
    "created_at_ms",
    "updated_at_ms",
    "content_class",
    "content_tags_json",
    "content_classification_json",
    "provider_signal_json",
    "provider_token_impacts_json",
    "canonical_item_key",
    "dedup_key_kind",
    "dedup_key_confidence",
    "url_identity_kind",
    "canonical_policy_version",
    "duplicate_observation_count",
    "source_ids_json",
    "source_domains_json",
    "provider_article_keys_json",
    "processing_lease_owner",
    "processing_leased_until_ms",
    "processing_next_due_at_ms",
    "processing_terminal_error",
    "story_key",
    "story_identity_json",
    "story_identity_version",
    "agent_admission_status",
    "agent_admission_reason",
    "agent_admission_json",
    "agent_admission_version",
    "agent_representative_news_item_id",
    "agent_admission_computed_at_ms",
    "market_scope_json",
)
_NEWS_ITEM_WORKER_COLUMNS_SQL = ",\n".join(f"                items.{column}" for column in _NEWS_ITEM_WORKER_COLUMNS)
_NEWS_ITEM_WORKER_JSON_SQL = (
    "jsonb_build_object(\n"
    + ",\n".join(f"                  '{column}', items.{column}" for column in _NEWS_ITEM_WORKER_COLUMNS)
    + "\n                )"
)
_MATERIAL_MATCH_WINDOW_MS = 600_000
_STORY_PROJECTION_WINDOW_MS = 72 * 60 * 60 * 1000


def _required_news_high_signal_since_ms(value: Any) -> int:
    return require_nonnegative_int(
        value,
        error_code="news_high_signal_notification_since_ms_required",
    )


def _optional_returning_row(cursor: Any, row: Any | None) -> dict[str, Any] | None:
    returning_mutation_count(cursor, row, error_code="news_repository_rowcount_invalid")
    return dict(row) if row is not None else None


def _required_returning_row(cursor: Any, row: Any | None) -> dict[str, Any]:
    expect_mutation_count(cursor, expected=1, error_code="news_repository_rowcount_invalid")
    if row is None:
        raise TypeError("news_repository_rowcount_invalid")
    return dict(row)


def _source_payload(source: NewsSourceConfig | Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(source, NewsSourceConfig):
        return {
            "source_id": source.source_id,
            "provider_type": source.provider_type,
            "feed_url": source.feed_url,
            "source_domain": source.source_domain,
            "source_name": source.source_name,
            "source_role": source.source_role,
            "trust_tier": source.trust_tier,
            "managed_by_config": source.managed_by_config,
            "enabled": source.enabled,
            "refresh_interval_seconds": source.refresh_interval_seconds,
            "coverage_tags": source.coverage_tags,
            "asset_universe": source.asset_universe,
            "authority_scope": source.authority_scope or {},
            "fetch_policy": source.fetch_policy or {},
            "cost_policy": source.cost_policy or {},
        }
    payload = dict(source)
    payload["coverage_tags"] = normalize_string_tuple(payload.get("coverage_tags"))
    payload["asset_universe"] = normalize_string_tuple(payload.get("asset_universe"))
    payload["authority_scope"] = _optional_news_source_policy_mapping(payload.get("authority_scope"), "authority_scope")
    payload["fetch_policy"] = _optional_news_source_policy_mapping(payload.get("fetch_policy"), "fetch_policy")
    payload["cost_policy"] = _optional_news_source_policy_mapping(payload.get("cost_policy"), "cost_policy")
    return payload


def news_source_config_payload_hash(source: NewsSourceConfig | Mapping[str, Any]) -> str:
    payload = _source_payload(source)
    return _news_source_config_payload_hash(
        _normalized_news_source_config_payload(
            source_id=payload["source_id"],
            provider_type=payload["provider_type"],
            feed_url=payload["feed_url"],
            source_domain=payload["source_domain"],
            source_name=payload["source_name"],
            source_role=payload.get("source_role", "observed_source"),
            trust_tier=payload.get("trust_tier", "standard"),
            managed_by_config=payload.get("managed_by_config", True),
            enabled=payload.get("enabled", True),
            refresh_interval_seconds=payload.get("refresh_interval_seconds", 300),
            coverage_tags=payload.get("coverage_tags", ()),
            asset_universe=payload.get("asset_universe", ()),
            authority_scope=payload.get("authority_scope"),
            fetch_policy=payload.get("fetch_policy"),
            cost_policy=payload.get("cost_policy"),
        )
    )


def _normalized_news_source_config_payload(
    *,
    source_id: str,
    provider_type: str,
    feed_url: str,
    source_domain: str,
    source_name: str,
    source_role: str = "observed_source",
    trust_tier: str = "standard",
    managed_by_config: bool = True,
    enabled: bool = True,
    refresh_interval_seconds: int = 300,
    coverage_tags: object = (),
    asset_universe: object = (),
    authority_scope: Mapping[str, Any] | None = None,
    fetch_policy: Mapping[str, Any] | None = None,
    cost_policy: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "source_id": str(source_id),
        "provider_type": str(provider_type),
        "feed_url": str(feed_url),
        "source_domain": str(source_domain),
        "source_name": str(source_name),
        "source_role": str(source_role),
        "trust_tier": str(trust_tier),
        "managed_by_config": bool(managed_by_config),
        "enabled": bool(enabled),
        "refresh_interval_seconds": require_positive_int(
            refresh_interval_seconds,
            error_code="news_source_refresh_interval_seconds_required",
        ),
        "coverage_tags_json": list(normalize_string_tuple(coverage_tags)),
        "asset_universe_json": list(normalize_string_tuple(asset_universe)),
        "authority_scope_json": _optional_news_source_policy_mapping(authority_scope, "authority_scope"),
        "fetch_policy_json": _optional_news_source_policy_mapping(fetch_policy, "fetch_policy"),
        "cost_policy_json": _optional_news_source_policy_mapping(cost_policy, "cost_policy"),
    }


def _news_source_config_payload_hash(payload: Mapping[str, Any]) -> str:
    return stable_current_payload_hash(dict(payload))


def _optional_source_config_payload_hash(value: Any, *, field_name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.startswith("sha256:") or len(value) != 71:
        raise ValueError(f"news_source_{field_name}_required")
    try:
        int(value.removeprefix("sha256:"), 16)
    except ValueError as exc:
        raise ValueError(f"news_source_{field_name}_required") from exc
    return value


def _optional_news_source_policy_mapping(value: Any, field_name: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise ValueError(f"news_source_{field_name}_required")
    return dict(value)


def news_page_cursor(row: Mapping[str, Any]) -> str:
    return f"{int(row['latest_at_ms'])}:{row['row_id']}"


def _decode_page_cursor(cursor: str | None) -> tuple[int | None, str | None]:
    if not cursor:
        return None, None
    raw_time, separator, row_id = str(cursor).partition(":")
    if not separator:
        return None, str(cursor)
    try:
        cursor_time = int(raw_time)
    except ValueError:
        return None, str(cursor)
    return cursor_time, row_id


def _news_page_row_filter_sql(
    *,
    status: str | None = None,
    signal: str | None = None,
    q: str | None = None,
) -> tuple[str, list[Any]]:
    filters: list[str] = []
    filter_params: list[Any] = []
    if status:
        filters.append("lifecycle_status = %s")
        filter_params.append(str(status))
    if signal:
        filters.append(_NEWS_PAGE_SIGNAL_SQL)
        filter_params.append(str(signal).strip().lower())
    query_text = str(q).strip() if q is not None else ""
    if query_text:
        filters.append("search_text ILIKE %s")
        filter_params.append(f"%{query_text}%")
    filter_sql = " AND " + " AND ".join(filters) if filters else ""
    return filter_sql, filter_params


def _page_row_payload(row: Mapping[str, Any]) -> dict[str, Any]:
    payload = dict(row)
    payload["latest_at_ms"] = _required_page_positive_int(payload, "latest_at_ms")
    payload["computed_at_ms"] = _required_page_positive_int(payload, "computed_at_ms")
    payload["headline"] = _required_page_string(payload, "headline")
    payload["canonical_url"] = _required_page_string(payload, "canonical_url")
    payload["summary"] = _required_page_string(payload, "summary")
    payload["source_domain"] = _required_page_string(payload, "source_domain")
    payload["token_lanes_json"] = _json(_required_page_list(payload, "token_lanes"))
    payload["fact_lanes_json"] = _json(_required_page_list(payload, "fact_lanes"))
    payload["representative_news_item_id"] = _required_page_text(payload, "representative_news_item_id")
    payload["story_key"] = _required_page_text(payload, "story_key")
    payload["story_json"] = _json(_required_page_mapping(payload, "story"))
    payload["token_impacts_json"] = _json(_required_page_list(payload, "token_impacts"))
    payload["content_class"] = _required_page_text(payload, "content_class")
    payload["content_tags_json"] = _json(_required_page_list(payload, "content_tags"))
    payload["content_classification_json"] = _json(_required_page_mapping(payload, "content_classification"))
    payload["source_json"] = _json(_required_page_mapping(payload, "source"))
    agent_brief = _required_page_mapping(payload, "agent_brief")
    agent_brief_status = _required_page_nested_text(agent_brief, "agent_brief", "status")
    agent_status = _required_page_text(payload, "agent_status")
    if agent_status != agent_brief_status:
        raise ValueError("news_page_row_payload_invalid:agent_status_mismatch")
    if agent_status == "ready":
        _required_page_nested_text(agent_brief, "agent_brief", "direction")
        _required_page_nested_text(agent_brief, "agent_brief", "decision_class")
    signal = _required_page_mapping(payload, "signal")
    payload["signal_json"] = _json(signal)
    payload["provider_rating_json"] = _json(_required_page_mapping(payload, "provider_rating"))
    payload["agent_brief_json"] = _json(agent_brief)
    payload["agent_status"] = agent_status
    payload["agent_brief_computed_at_ms"] = _optional_page_positive_int(payload, "agent_brief_computed_at_ms")
    payload["market_scope_json"] = _json(_required_page_mapping(payload, "market_scope"))
    macro_event_flow = _required_page_optional_macro_event_flow(payload)
    payload["macro_event_flow_json"] = _json(macro_event_flow) if macro_event_flow is not None else None
    agent_admission = _agent_admission_mapping_payload(_required_page_mapping(payload, "agent_admission"))
    payload["agent_admission_status"] = _required_page_text(payload, "agent_admission_status")
    payload["agent_admission_reason"] = _required_page_text(payload, "agent_admission_reason")
    payload["agent_representative_news_item_id"] = _required_page_text(payload, "agent_representative_news_item_id")
    _require_page_agent_admission_match(
        payload,
        agent_admission,
        payload_field="agent_admission_status",
        admission_field="status",
    )
    _require_page_agent_admission_match(
        payload,
        agent_admission,
        payload_field="agent_admission_reason",
        admission_field="reason",
    )
    _require_page_agent_admission_match(
        payload,
        agent_admission,
        payload_field="agent_representative_news_item_id",
        admission_field="representative_news_item_id",
    )
    payload["agent_admission_json"] = _json(agent_admission)
    return payload


def _required_page_text(payload: Mapping[str, Any], field_name: str) -> str:
    if field_name not in payload:
        raise ValueError(f"news_page_row_payload_required:{field_name}")
    value = payload[field_name]
    if not isinstance(value, str) or not value:
        raise ValueError(f"news_page_row_payload_invalid:{field_name}")
    return value


def _required_page_string(payload: Mapping[str, Any], field_name: str) -> str:
    if field_name not in payload:
        raise ValueError(f"news_page_row_payload_required:{field_name}")
    value = payload[field_name]
    if not isinstance(value, str):
        raise ValueError(f"news_page_row_payload_invalid:{field_name}")
    return value


def _required_page_mapping(payload: Mapping[str, Any], field_name: str) -> dict[str, Any]:
    if field_name not in payload:
        raise ValueError(f"news_page_row_payload_required:{field_name}")
    value = payload[field_name]
    if not isinstance(value, Mapping):
        raise ValueError(f"news_page_row_payload_invalid:{field_name}")
    return dict(value)


def _required_page_list(payload: Mapping[str, Any], field_name: str) -> list[Any]:
    if field_name not in payload:
        raise ValueError(f"news_page_row_payload_required:{field_name}")
    value = payload[field_name]
    if not isinstance(value, list):
        raise ValueError(f"news_page_row_payload_invalid:{field_name}")
    return list(value)


def _required_page_positive_int(payload: Mapping[str, Any], field_name: str) -> int:
    if field_name not in payload:
        raise ValueError(f"news_page_row_payload_required:{field_name}")
    value = payload[field_name]
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ValueError(f"news_page_row_payload_invalid:{field_name}")
    return value


def _optional_page_positive_int(payload: Mapping[str, Any], field_name: str) -> int | None:
    value = payload.get(field_name)
    if value is None:
        return None
    return _required_page_positive_int(payload, field_name)


def _required_page_nonnegative_int(payload: Mapping[str, Any], field_name: str) -> int:
    if field_name not in payload:
        raise ValueError(f"news_page_row_payload_required:{field_name}")
    value = payload[field_name]
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"news_page_row_payload_invalid:{field_name}")
    if value < 0:
        raise ValueError(f"news_page_row_payload_invalid:{field_name}")
    return value


def _required_page_optional_macro_event_flow(payload: Mapping[str, Any]) -> dict[str, Any] | None:
    field_name = "macro_event_flow"
    if field_name not in payload:
        raise ValueError(f"news_page_row_payload_required:{field_name}")
    value = payload[field_name]
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise ValueError(f"news_page_row_payload_invalid:{field_name}")
    event_flow = dict(value)
    for event_field in _MACRO_EVENT_FLOW_FIELDS:
        if not str(event_flow.get(event_field) or "").strip():
            raise ValueError(f"news_page_row_payload_invalid:{field_name}.{event_field}")
    return event_flow


def _required_projected_page_text(projected: Mapping[str, Any], field_name: str) -> str:
    if field_name not in projected:
        raise ValueError(f"news_item_detail_projection_required:{field_name}")
    value = projected[field_name]
    if not isinstance(value, str) or not value:
        raise ValueError(f"news_item_detail_projection_invalid:{field_name}")
    return value


def _required_projected_page_mapping(projected: Mapping[str, Any], field_name: str) -> dict[str, Any]:
    if field_name not in projected:
        raise ValueError(f"news_item_detail_projection_required:{field_name}")
    value = projected[field_name]
    if not isinstance(value, Mapping):
        raise ValueError(f"news_item_detail_projection_invalid:{field_name}")
    return dict(value)


def _required_projected_page_list(projected: Mapping[str, Any], field_name: str) -> list[Any]:
    if field_name not in projected:
        raise ValueError(f"news_item_detail_projection_required:{field_name}")
    value = projected[field_name]
    if not isinstance(value, list):
        raise ValueError(f"news_item_detail_projection_invalid:{field_name}")
    return list(value)


def _required_news_item_detail_list(row: Mapping[str, Any], field_name: str) -> list[Any]:
    if field_name not in row:
        raise ValueError(f"news_item_detail_evidence_required:{field_name}")
    value = row[field_name]
    if not isinstance(value, list):
        raise ValueError(f"news_item_detail_evidence_invalid:{field_name}")
    return list(value)


def _required_page_projection_input_list(row: Mapping[str, Any], field_name: str) -> list[Any]:
    return _required_repository_json_list(
        row,
        field_name,
        error_prefix="news_page_projection_input_evidence",
    )


def _required_agent_admission_context_list(row: Mapping[str, Any], field_name: str) -> list[Any]:
    return _required_repository_json_list(row, field_name, error_prefix="news_agent_admission_context")


def _required_repository_json_list(row: Mapping[str, Any], field_name: str, *, error_prefix: str) -> list[Any]:
    if field_name not in row:
        raise ValueError(f"{error_prefix}_required:{field_name}")
    value = row[field_name]
    if not isinstance(value, list):
        raise ValueError(f"{error_prefix}_invalid:{field_name}")
    return list(value)


def _required_positive_news_item_source_watermark(row: Mapping[str, Any]) -> int:
    field_name = "source_watermark_ms"
    if field_name not in row:
        raise ValueError(f"news_item_source_watermark_required:{field_name}")
    value = row[field_name]
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"news_item_source_watermark_required:{field_name}")
    return int(value)


def _required_story_brief_target_source_updated_at_ms(row: Mapping[str, Any]) -> int:
    field_name = "source_updated_at_ms"
    if field_name not in row:
        raise ValueError("news_story_brief_target_source_updated_at_ms_required")
    value = row[field_name]
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError("news_story_brief_target_source_updated_at_ms_required")
    return int(value)


def _required_source_sync_cursor_nonnegative_int(row: Mapping[str, Any], field_name: str) -> int:
    if field_name not in row:
        raise ValueError(f"news_source_sync_cursor_{field_name}_required")
    value = row[field_name]
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"news_source_sync_cursor_{field_name}_required")
    return int(value)


def _required_news_dedup_diagnostics_nonnegative_int(row: Mapping[str, Any], field_name: str) -> int:
    if field_name not in row:
        raise ValueError(f"news_dedup_diagnostics_{field_name}_required")
    value = row[field_name]
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"news_dedup_diagnostics_{field_name}_required")
    return int(value)


def _required_news_dedup_diagnostics_list(row: Mapping[str, Any], field_name: str) -> list[Any]:
    if field_name not in row:
        raise ValueError(f"news_dedup_diagnostics_{field_name}_required")
    value = row[field_name]
    if not isinstance(value, list):
        raise ValueError(f"news_dedup_diagnostics_{field_name}_required")
    return list(value)


def _required_news_dedup_diagnostics_mapping(row: Mapping[str, Any], field_name: str) -> dict[str, Any]:
    if field_name not in row:
        raise ValueError(f"news_dedup_diagnostics_{field_name}_required")
    value = row[field_name]
    if not isinstance(value, Mapping):
        raise ValueError(f"news_dedup_diagnostics_{field_name}_required")
    return dict(value)


def _projected_news_page_row_payload(
    row: Mapping[str, Any],
    *,
    require_full_sections: bool,
    require_macro_event_flow: bool = False,
) -> dict[str, Any]:
    payload = dict(row)
    for field_name in (
        "row_id",
        "news_item_id",
        "representative_news_item_id",
        "story_key",
        "content_class",
        "agent_admission_status",
        "agent_admission_reason",
        "agent_representative_news_item_id",
        "projection_version",
    ):
        payload[field_name] = _required_news_page_row_text(payload, field_name)
    for field_name in (
        "story",
        "signal",
        "provider_rating",
        "source",
        "market_scope",
        "agent_admission",
    ):
        payload[field_name] = _required_news_page_row_mapping(payload, field_name)
    for field_name in ("source_ids", "source_domains", "token_impacts", "content_tags"):
        payload[field_name] = _required_news_page_row_list(payload, field_name)
    if require_full_sections:
        payload["content_classification"] = _required_news_page_row_mapping(payload, "content_classification")
        payload["token_lanes"] = _required_news_page_row_list(payload, "token_lanes")
        payload["fact_lanes"] = _required_news_page_row_list(payload, "fact_lanes")
    if require_macro_event_flow or payload.get("macro_event_flow") is not None:
        payload["macro_event_flow"] = _required_news_page_row_macro_event_flow(payload)
    else:
        payload.pop("macro_event_flow", None)
    payload["agent_brief"] = _public_agent_brief_payload(_required_news_page_row_mapping(payload, "agent_brief"))
    return payload


def _required_news_page_row_text(projected: Mapping[str, Any], field_name: str) -> str:
    if field_name not in projected:
        raise ValueError(f"news_page_row_projection_required:{field_name}")
    value = projected[field_name]
    if not isinstance(value, str) or not value:
        raise ValueError(f"news_page_row_projection_invalid:{field_name}")
    return value


def _required_news_page_row_mapping(projected: Mapping[str, Any], field_name: str) -> dict[str, Any]:
    if field_name not in projected:
        raise ValueError(f"news_page_row_projection_required:{field_name}")
    value = projected[field_name]
    if not isinstance(value, Mapping):
        raise ValueError(f"news_page_row_projection_invalid:{field_name}")
    return dict(value)


def _required_news_page_row_list(projected: Mapping[str, Any], field_name: str) -> list[Any]:
    if field_name not in projected:
        raise ValueError(f"news_page_row_projection_required:{field_name}")
    value = projected[field_name]
    if not isinstance(value, list):
        raise ValueError(f"news_page_row_projection_invalid:{field_name}")
    return list(value)


def _required_news_page_row_macro_event_flow(projected: Mapping[str, Any]) -> dict[str, Any]:
    field_name = "macro_event_flow"
    if field_name not in projected:
        raise ValueError(f"news_page_row_projection_required:{field_name}")
    value = projected[field_name]
    if not isinstance(value, Mapping):
        raise ValueError(f"news_page_row_projection_invalid:{field_name}")
    event_flow = dict(value)
    for event_field in _MACRO_EVENT_FLOW_FIELDS:
        if not str(event_flow.get(event_field) or "").strip():
            raise ValueError(f"news_page_row_projection_invalid:{field_name}.{event_field}")
    return event_flow


def _story_projection_payload(*, story_key: str, member_payloads: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    member_items = [_required_story_projection_member_item(payload) for payload in member_payloads]
    if not member_items:
        raise ValueError("news_story_projection_member_item_required")
    member_news_item_ids = [_required_story_projection_text(item, "news_item_id") for item in member_items]
    source_ids = sorted(
        {
            str(source_id)
            for item in member_items
            for source_id in _required_story_projection_list(item, "source_ids_json")
            if str(source_id or "")
        }
    )
    source_domains = sorted(
        {
            str(source_domain)
            for item in member_items
            for source_domain in _required_story_projection_list(item, "source_domains_json")
            if str(source_domain or "")
        }
    )
    provider_article_keys = sorted(
        {
            str(provider_key)
            for item in member_items
            for provider_key in _required_story_projection_list(item, "provider_article_keys_json")
            if str(provider_key or "")
        }
    )
    published_at_ms_values = [
        _required_story_projection_nonnegative_int(item, "published_at_ms") for item in member_items
    ]
    latest_at_ms = max(published_at_ms_values)
    earliest_at_ms = min(published_at_ms_values)
    representative_news_item_id = member_news_item_ids[0]
    story_identity = _required_story_projection_mapping(member_items[0], "story_identity_json")
    return {
        "story_key": story_key,
        "representative_news_item_id": representative_news_item_id,
        "member_news_item_ids": member_news_item_ids,
        "member_count": len(member_news_item_ids),
        "source_ids": source_ids,
        "source_domains": source_domains,
        "provider_article_keys": provider_article_keys,
        "latest_at_ms": latest_at_ms,
        "earliest_at_ms": earliest_at_ms,
        "story_identity_json": story_identity,
    }


def _required_story_projection_member_item(payload: Mapping[str, Any]) -> dict[str, Any]:
    value = payload.get("item")
    if not isinstance(value, Mapping):
        raise ValueError("news_story_projection_item_required")
    return dict(value)


def _required_story_projection_payload_list(payload: Mapping[str, Any], field_name: str) -> list[Any]:
    if field_name not in payload:
        raise ValueError(f"news_story_projection_{field_name}_required")
    value = payload[field_name]
    if not isinstance(value, list):
        raise ValueError(f"news_story_projection_{field_name}_required")
    return list(value)


def _required_story_projection_text(item: Mapping[str, Any], field_name: str) -> str:
    if field_name not in item:
        raise ValueError(f"news_story_projection_{field_name}_required")
    text = str(item[field_name]).strip()
    if not text:
        raise ValueError(f"news_story_projection_{field_name}_required")
    return text


def _required_story_projection_list(item: Mapping[str, Any], field_name: str) -> list[Any]:
    if field_name not in item:
        raise ValueError(f"news_story_projection_{field_name}_required")
    value = item[field_name]
    if isinstance(value, str) or not isinstance(value, list | tuple):
        raise ValueError(f"news_story_projection_{field_name}_required")
    return list(value)


def _required_story_projection_mapping(item: Mapping[str, Any], field_name: str) -> dict[str, Any]:
    if field_name not in item:
        raise ValueError(f"news_story_projection_{field_name}_required")
    value = item[field_name]
    if not isinstance(value, Mapping) or not value:
        raise ValueError(f"news_story_projection_{field_name}_required")
    return dict(value)


def _required_story_projection_nonnegative_int(item: Mapping[str, Any], field_name: str) -> int:
    if field_name not in item:
        raise ValueError(f"news_story_projection_{field_name}_required")
    value = item[field_name]
    if isinstance(value, bool):
        raise ValueError(f"news_story_projection_{field_name}_required")
    try:
        resolved = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"news_story_projection_{field_name}_required") from exc
    if resolved < 0:
        raise ValueError(f"news_story_projection_{field_name}_required")
    return resolved


def _required_story_item_text(item: Mapping[str, Any], field_name: str) -> str:
    if field_name not in item:
        raise ValueError(f"news_story_brief_target_{field_name}_required")
    text = str(item[field_name]).strip()
    if not text:
        raise ValueError(f"news_story_brief_target_{field_name}_required")
    return text


def _required_story_item_mapping(item: Mapping[str, Any], field_name: str) -> dict[str, Any]:
    if field_name not in item:
        raise ValueError(f"news_story_brief_target_{field_name}_required")
    value = item[field_name]
    if not isinstance(value, Mapping) or not value:
        raise ValueError(f"news_story_brief_target_{field_name}_required")
    return dict(value)


def _required_story_item_json_value(item: Mapping[str, Any], field_name: str) -> object:
    if field_name not in item:
        raise ValueError(f"news_story_brief_target_{field_name}_required")
    value = item[field_name]
    if isinstance(value, Mapping):
        if not value:
            raise ValueError(f"news_story_brief_target_{field_name}_required")
        return dict(value)
    if isinstance(value, list | tuple | set):
        if not value:
            raise ValueError(f"news_story_brief_target_{field_name}_required")
        return list(value)
    if isinstance(value, str) and value.strip():
        return value
    raise ValueError(f"news_story_brief_target_{field_name}_required")


def _story_brief_target_list(row: Mapping[str, Any], field_name: str) -> list[Any]:
    value = row.get(field_name)
    if value is None:
        return []
    if isinstance(value, str) or not isinstance(value, list | tuple):
        raise ValueError(f"news_story_brief_target_{field_name}_required")
    return list(value)


def _required_agent_admission_item_text(item: Mapping[str, Any], field_name: str) -> str:
    value = item.get(field_name)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"news_agent_admission_{field_name}_required")
    return value.strip()


def _apply_page_row_summary(payload: dict[str, Any], summary: Mapping[str, Any]) -> None:
    if summary:
        payload["canonical_item_key"] = _required_page_text(summary, "canonical_item_key")
        payload["duplicate_count"] = _required_page_nonnegative_int(summary, "duplicate_observation_count")
        payload["source_ids_json"] = _json(_required_page_list(summary, "source_ids_json"))
        payload["source_domains_json"] = _json(_required_page_list(summary, "source_domains_json"))
        payload["provider_article_keys_json"] = _json(_required_page_list(summary, "provider_article_keys_json"))
        return
    payload["canonical_item_key"] = _required_page_text(payload, "canonical_item_key")
    payload["duplicate_count"] = _required_page_nonnegative_int(payload, "duplicate_count")
    payload["source_ids_json"] = _json(_required_page_list(payload, "source_ids_json"))
    payload["source_domains_json"] = _json(_required_page_list(payload, "source_domains_json"))
    payload["provider_article_keys_json"] = _json(_required_page_list(payload, "provider_article_keys_json"))


def _agent_publishable_summary(agent_brief: Mapping[str, Any], *, brief_json: Mapping[str, Any]) -> bool:
    value = agent_brief.get("summary_zh")
    if value is None and "summary_zh" in brief_json:
        value = brief_json.get("summary_zh")
    if not isinstance(value, str):
        return False
    return bool(value.strip())


def _required_json_mapping(payload: Mapping[str, Any], field_name: str, *, label: str) -> dict[str, Any]:
    if field_name not in payload:
        raise ValueError(f"unsupported {label} shape: missing {field_name}")
    value = payload[field_name]
    if not isinstance(value, Mapping):
        raise ValueError(f"unsupported {label} shape: {field_name} must be mapping")
    return dict(value)


def _required_json_list(payload: Mapping[str, Any], field_name: str, *, label: str) -> list[Any]:
    if field_name not in payload:
        raise ValueError(f"unsupported {label} shape: missing {field_name}")
    value = payload[field_name]
    if isinstance(value, str) or not isinstance(value, list | tuple):
        raise ValueError(f"unsupported {label} shape: {field_name} must be list")
    return list(value)


def _required_member_news_item_ids(payload: Mapping[str, Any], *, label: str) -> list[str]:
    ids = _member_news_item_ids(_required_json_list(payload, "member_news_item_ids_json", label=label))
    if not ids:
        raise ValueError(f"unsupported {label} shape: member_news_item_ids_json must be non-empty")
    return ids


def _entity_payload(entity: NewsEntity) -> dict[str, Any]:
    if not isinstance(entity, NewsEntity):
        raise ValueError("unsupported news entity payload shape")
    return {
        "entity_id": str(entity.entity_id),
        "news_item_id": str(entity.news_item_id),
        "entity_type": str(entity.entity_type),
        "raw_value": str(entity.raw_value),
        "normalized_value": str(entity.normalized_value),
        "chain": entity.chain,
        "span_start": int(entity.span_start),
        "span_end": int(entity.span_end),
        "text_surface": str(entity.text_surface),
        "confidence": float(entity.confidence),
        "extraction_policy_version": str(entity.extraction_policy_version),
        "created_at_ms": int(entity.created_at_ms),
    }


def _mention_payload(mention: NewsTokenMention) -> dict[str, Any]:
    if not isinstance(mention, NewsTokenMention):
        raise ValueError("unsupported news token mention payload shape")
    return {
        "mention_id": str(mention.mention_id),
        "news_item_id": str(mention.news_item_id),
        "entity_id": mention.entity_id,
        "observed_symbol": mention.observed_symbol,
        "chain_id": mention.chain_id,
        "address": mention.address,
        "resolution_status": str(mention.resolution_status),
        "target_type": mention.target_type,
        "target_id": mention.target_id,
        "display_symbol": mention.display_symbol,
        "display_name": mention.display_name,
        "reason_codes_json": _json(list(mention.reason_codes)),
        "candidate_targets_json": _json([dict(candidate) for candidate in mention.candidate_targets]),
        "evidence_strength": str(mention.evidence_strength),
        "confidence": float(mention.confidence),
        "created_at_ms": int(mention.created_at_ms),
    }


def _fact_payload(candidate: NewsFactCandidate) -> dict[str, Any]:
    if not isinstance(candidate, NewsFactCandidate):
        raise ValueError("unsupported news fact candidate payload shape")
    return {
        "fact_candidate_id": str(candidate.fact_candidate_id),
        "news_item_id": str(candidate.news_item_id),
        "event_type": str(candidate.event_type),
        "claim": str(candidate.claim),
        "realis": str(candidate.realis),
        "evidence_quote": str(candidate.evidence_quote),
        "evidence_span_start": int(candidate.evidence_span_start),
        "evidence_span_end": int(candidate.evidence_span_end),
        "source_role": str(candidate.source_role),
        "required_slots_json": _json(dict(candidate.required_slots)),
        "affected_targets_json": _json([dict(target) for target in candidate.affected_targets]),
        "validation_status": str(candidate.validation_status),
        "rejection_reasons_json": _json(list(candidate.rejection_reasons)),
        "extraction_method": str(candidate.extraction_method),
        "policy_version": str(candidate.policy_version),
        "created_at_ms": int(candidate.created_at_ms),
        "updated_at_ms": int(candidate.updated_at_ms),
    }


def _story_agent_run_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    response_json = payload["response_json"]
    label = "news story agent run payload"
    return {
        "run_id": str(payload["run_id"]),
        "story_brief_key": str(payload["story_brief_key"]),
        "story_key": str(payload["story_key"]),
        "story_identity_version": str(payload["story_identity_version"]),
        "representative_news_item_id": str(payload["representative_news_item_id"]),
        "member_news_item_ids_json": _json(_required_member_news_item_ids(payload, label=label)),
        "provider": str(payload["provider"]),
        "model": str(payload["model"]),
        "backend": _required_payload_text(payload, "backend", label=label),
        "execution_trace_id": payload.get("execution_trace_id"),
        "workflow_name": str(payload["workflow_name"]),
        "agent_name": str(payload["agent_name"]),
        "lane": str(payload["lane"]),
        "artifact_version_hash": str(payload["artifact_version_hash"]),
        "prompt_version": str(payload["prompt_version"]),
        "schema_version": str(payload["schema_version"]),
        "validator_version": str(payload["validator_version"]),
        "guardrail_version": str(payload["guardrail_version"]),
        "input_hash": str(payload["input_hash"]),
        "output_hash": payload.get("output_hash"),
        "execution_started": bool(payload["execution_started"]),
        "status": str(payload["status"]),
        "outcome": str(payload["outcome"]),
        "error_class": payload.get("error_class"),
        "error": _compact_error(payload.get("error")),
        "request_json": _json(_required_json_mapping(payload, "request_json", label=label)),
        "response_json": _json(response_json) if response_json is not None else None,
        "validation_errors_json": _json(_required_json_list(payload, "validation_errors_json", label=label)),
        "trace_metadata_json": _json(_required_json_mapping(payload, "trace_metadata_json", label=label)),
        "usage_json": _json(_required_json_mapping(payload, "usage_json", label=label)),
        "latency_ms": _required_payload_nonnegative_int(payload, "latency_ms", label=label),
        "started_at_ms": int(payload["started_at_ms"]),
        "finished_at_ms": int(payload["finished_at_ms"]),
        "created_at_ms": int(payload["created_at_ms"]),
    }


def _story_agent_brief_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    status = str(payload["status"])
    brief_json = _required_json_mapping(payload, "brief_json", label="news story agent brief payload")
    if status == "ready" and not _agent_publishable_summary(payload, brief_json=brief_json):
        raise ValueError("ready news story agent brief requires publishable summary")
    return {
        "story_brief_key": str(payload["story_brief_key"]),
        "story_key": str(payload["story_key"]),
        "story_identity_version": str(payload["story_identity_version"]),
        "representative_news_item_id": str(payload["representative_news_item_id"]),
        "member_news_item_ids_json": _json(
            _required_member_news_item_ids(payload, label="news story agent brief payload")
        ),
        "agent_run_id": str(payload["agent_run_id"]),
        "status": status,
        "direction": str(payload["direction"]),
        "decision_class": str(payload["decision_class"]),
        "brief_json": _json(brief_json),
        "input_hash": str(payload["input_hash"]),
        "artifact_version_hash": str(payload["artifact_version_hash"]),
        "prompt_version": str(payload["prompt_version"]),
        "schema_version": str(payload["schema_version"]),
        "validator_version": str(payload["validator_version"]),
        "computed_at_ms": int(payload["computed_at_ms"]),
        "created_at_ms": int(payload["created_at_ms"]),
        "updated_at_ms": int(payload["updated_at_ms"]),
    }


def _member_news_item_ids(value: Any) -> list[str]:
    return list(dict.fromkeys(str(item) for item in value if str(item)))


def _source_status_payload(row: Mapping[str, Any]) -> dict[str, Any]:
    latest_fetch_run = _optional_source_status_present_mapping(row, "latest_fetch_run_json")
    latest_item_published_at_ms = _optional_int(row.get("latest_item_published_at_ms"))
    latest_item_fetched_at_ms = _optional_int(row.get("latest_item_fetched_at_ms"))
    last_success_at_ms = _optional_int(row.get("last_success_at_ms"))
    last_seen_at_ms = _max_optional_int(
        latest_item_fetched_at_ms,
        last_success_at_ms,
    )
    source_id = _required_source_status_text(row, "source_id")
    provider_type = _required_source_status_text(row, "provider_type")
    source_domain = _required_source_status_text(row, "source_domain")
    source_name = _required_source_status_text(row, "source_name")
    source_role = _required_source_status_text(row, "source_role")
    trust_tier = _required_source_status_text(row, "trust_tier")
    source_quality_status = _required_source_status_text(row, "source_quality_status")
    enabled = _required_source_status_bool(row, "enabled")
    managed_by_config = _required_source_status_bool(row, "managed_by_config")
    refresh_interval_seconds = _required_source_status_nonnegative_int(row, "refresh_interval_seconds")
    item_count = _required_source_status_nonnegative_int(row, "item_count")
    sync_high_watermark_ms = _required_source_status_nonnegative_int(row, "sync_high_watermark_ms")
    sync_overlap_ms = _required_source_status_nonnegative_int(row, "sync_overlap_ms")
    next_fetch_after_ms = _required_source_status_nonnegative_int(row, "next_fetch_after_ms")
    consecutive_failures = _required_source_status_nonnegative_int(row, "consecutive_failures")
    last_error = _compact_error(row.get("last_error"))
    return {
        "source_id": source_id,
        "provider_type": provider_type,
        "source_domain": source_domain,
        "source_name": source_name,
        "source_role": source_role,
        "trust_tier": trust_tier,
        "coverage_tags": _required_source_status_text_list(row, "coverage_tags_json"),
        "source_quality_status": source_quality_status,
        "enabled": enabled,
        "managed_by_config": managed_by_config,
        "refresh_interval_seconds": refresh_interval_seconds,
        "item_count": item_count,
        "latest_item_published_at_ms": latest_item_published_at_ms,
        "latest_item_fetched_at_ms": latest_item_fetched_at_ms,
        "last_seen_at_ms": last_seen_at_ms,
        "latest_fetch_run": _latest_fetch_run_payload(latest_fetch_run),
        "sync_high_watermark_ms": sync_high_watermark_ms,
        "sync_overlap_ms": sync_overlap_ms,
        "sync_diagnostics": _optional_source_status_mapping(row, "sync_diagnostics_json"),
        "dedup_diagnostics": _optional_source_status_mapping(row, "dedup_diagnostics_json"),
        "provider_health": _provider_health_payload(
            enabled=enabled,
            consecutive_failures=consecutive_failures,
            source_quality_status=source_quality_status,
            last_error=last_error,
            last_success_at_ms=last_success_at_ms,
            last_seen_at_ms=last_seen_at_ms,
        ),
        "provider_capability_tags": _provider_capability_tags(
            provider_type=provider_type,
            source_role=source_role,
            trust_tier=trust_tier,
        ),
        "last_fetch_at_ms": _optional_int(row.get("last_fetch_at_ms")),
        "last_success_at_ms": last_success_at_ms,
        "next_fetch_after_ms": next_fetch_after_ms,
        "consecutive_failures": consecutive_failures,
        "last_error": last_error,
    }


def _optional_source_status_mapping(row: Mapping[str, Any], field_name: str) -> dict[str, Any]:
    value = row.get(field_name)
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise ValueError(f"news_source_status_{field_name}_required")
    return dict(value)


def _optional_source_status_present_mapping(row: Mapping[str, Any], field_name: str) -> dict[str, Any] | None:
    value = row.get(field_name)
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise ValueError(f"news_source_status_{field_name}_required")
    return dict(value)


def _required_source_status_bool(row: Mapping[str, Any], field_name: str) -> bool:
    value = row.get(field_name)
    if not isinstance(value, bool):
        raise ValueError(f"news_source_status_{field_name}_required")
    return value


def _required_source_status_nonnegative_int(row: Mapping[str, Any], field_name: str) -> int:
    value = row.get(field_name)
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError(f"news_source_status_{field_name}_required")
    return value


def _required_source_status_text(row: Mapping[str, Any], field_name: str) -> str:
    value = row.get(field_name)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"news_source_status_{field_name}_required")
    return value.strip()


def _required_source_status_text_list(row: Mapping[str, Any], field_name: str) -> list[str]:
    value = row.get(field_name)
    if not isinstance(value, list | tuple):
        raise ValueError(f"news_source_status_{field_name}_required")
    tags: list[str] = []
    for item in value:
        if not isinstance(item, str):
            raise ValueError(f"news_source_status_{field_name}_required")
        text = item.strip()
        if text:
            tags.append(text)
    return tags


def _source_material_changed(existing: Mapping[str, Any], payload: Mapping[str, Any]) -> bool:
    fields = (
        "provider_type",
        "feed_url",
        "source_domain",
        "source_name",
        "source_role",
        "trust_tier",
        "managed_by_config",
        "enabled",
        "refresh_interval_seconds",
        "coverage_tags_json",
        "asset_universe_json",
        "authority_scope_json",
        "fetch_policy_json",
        "cost_policy_json",
        "config_payload_hash",
        "terminal_config_payload_hash",
    )
    for field in fields:
        if _comparable_source_value(existing.get(field)) != _comparable_source_value(payload.get(field)):
            return True
    return False


def _provider_article_id(
    *,
    explicit: str | None,
    explicit_key: str | None,
    provider_type: str,
    payload: Mapping[str, Any],
) -> str:
    normalized_provider_type = str(provider_type or "").strip().lower()
    if normalized_provider_type not in PROVIDER_GLOBAL_ARTICLE_ID_TYPES:
        return ""
    if explicit is not None:
        return str(explicit).strip()
    article_id_from_key = _provider_article_id_from_global_key(
        provider_type=normalized_provider_type,
        provider_article_key=explicit_key,
    )
    if article_id_from_key:
        return article_id_from_key
    for field_name in ("provider_article_id", "article_id", "id"):
        value = str(payload.get(field_name) or "").strip()
        if value:
            return value
    return ""


def _provider_article_id_from_global_key(*, provider_type: str, provider_article_key: str | None) -> str:
    normalized_provider_type = str(provider_type or "").strip().lower()
    normalized_key = str(provider_article_key or "").strip()
    prefix = f"{normalized_provider_type}:"
    if not normalized_provider_type or not normalized_key.lower().startswith(prefix):
        return ""
    article_id = normalized_key[len(prefix) :].strip()
    if provider_global_article_key(provider_type=normalized_provider_type, provider_article_id=article_id) != (
        f"{normalized_provider_type}:{article_id}" if article_id else ""
    ):
        return ""
    return article_id


def _provider_payload_status(*, explicit: str | None, payload: Mapping[str, Any]) -> str:
    normalized = str(explicit or "").strip().lower()
    if normalized in {"partial", "ready"}:
        return normalized
    provider_signal = _json_dict(payload.get("provider_signal"))
    if str(provider_signal.get("status") or "").strip().lower() == "ready":
        return "ready"
    ai_rating = _json_dict(payload.get("aiRating"))
    if str(ai_rating.get("status") or "").strip().lower() == "done":
        return "ready"
    return "partial"


def _merge_provider_payload_status(*, existing: str, incoming: str) -> str:
    if str(existing or "").strip().lower() == "ready":
        return "ready"
    if str(incoming or "").strip().lower() == "ready":
        return "ready"
    return "partial"


def _provider_published_at_ms(payload: Mapping[str, Any]) -> int | None:
    for field_name in ("published_at_ms", "published_ms", "ts"):
        value = _numeric_payload_ms(payload.get(field_name))
        if value is not None:
            return value
    return None


def _numeric_payload_ms(value: Any) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    raw = str(value).strip()
    if not raw.isdigit():
        return None
    return int(raw)


def _canonical_identity_with_evidence(
    identity: CanonicalIdentity,
    evidence: Mapping[str, Any],
) -> CanonicalIdentity:
    return CanonicalIdentity(
        canonical_item_key=identity.canonical_item_key,
        news_item_id=identity.news_item_id,
        dedup_key_kind=identity.dedup_key_kind,
        dedup_key_confidence=identity.dedup_key_confidence,
        url_identity_kind=identity.url_identity_kind,
        match_type=identity.match_type,
        match_confidence=identity.match_confidence,
        evidence={**dict(identity.evidence), **dict(evidence)},
    )


def _material_window_bucket_ms_for_published_at(published_at_ms: int) -> int:
    value = int(published_at_ms)
    return value - (value % _MATERIAL_MATCH_WINDOW_MS)


def _material_window_bucket_ms_values_for_match_window(published_at_ms: int) -> tuple[int, ...]:
    start_ms = _material_window_bucket_ms_for_published_at(int(published_at_ms) - _MATERIAL_MATCH_WINDOW_MS)
    end_ms = _material_window_bucket_ms_for_published_at(int(published_at_ms) + _MATERIAL_MATCH_WINDOW_MS)
    return tuple(range(start_ms, end_ms + _MATERIAL_MATCH_WINDOW_MS, _MATERIAL_MATCH_WINDOW_MS))


def _material_symbol_key_for_impacts(provider_token_impacts: object) -> str:
    return ",".join(sorted(provider_symbol_set(provider_token_impacts)))


def _current_policy_material_duplicate_groups(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    keyed_rows: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        provider_type = _required_current_policy_material_text(row, "provider_type").lower()
        if provider_type != "opennews":
            continue
        source_id = _required_current_policy_material_text(row, "source_id")
        news_item_id = _required_current_policy_material_text(row, "news_item_id")
        title = _required_current_policy_material_text(row, "title")
        published_at_ms = _required_current_policy_material_positive_int(row, "published_at_ms")
        provider_token_impacts = _required_current_policy_material_impacts(row, "provider_token_impacts_json")
        fingerprint = material_title_fingerprint(title)
        if not material_title_is_eligible(fingerprint):
            continue
        payload = dict(row)
        payload["provider_type"] = provider_type
        payload["source_id"] = source_id
        payload["news_item_id"] = news_item_id
        payload["title"] = title
        payload["published_at_ms"] = published_at_ms
        payload["material_title_fingerprint"] = fingerprint
        payload["material_symbols"] = provider_symbol_set(provider_token_impacts)
        keyed_rows[(source_id, fingerprint)].append(payload)

    groups: list[dict[str, Any]] = []
    for (source_id, fingerprint), source_rows in sorted(keyed_rows.items()):
        clusters: list[list[dict[str, Any]]] = []
        for row in sorted(
            source_rows,
            key=lambda value: (int(value["published_at_ms"]), str(value["news_item_id"])),
        ):
            cluster = _current_policy_matching_material_cluster(clusters, row)
            if cluster is None:
                clusters.append([row])
            else:
                cluster.append(row)
        for cluster in clusters:
            candidate_ids = [str(row["news_item_id"]) for row in cluster]
            news_item_ids = list(dict.fromkeys(news_item_id for news_item_id in candidate_ids if news_item_id))
            if len(news_item_ids) <= 1:
                continue
            groups.append(
                {
                    "source_id": source_id,
                    "title_fingerprint": fingerprint,
                    "row_count": len(news_item_ids),
                    "duplicate_rows": len(news_item_ids) - 1,
                    "news_item_ids": news_item_ids,
                }
            )
    return sorted(
        groups,
        key=lambda group: (
            -int(group["duplicate_rows"]),
            str(group["source_id"]),
            str(group["title_fingerprint"]),
        ),
    )


def _current_policy_matching_material_cluster(
    clusters: Sequence[list[dict[str, Any]]],
    row: Mapping[str, Any],
) -> list[dict[str, Any]] | None:
    row_published_at = int(row["published_at_ms"])
    row_symbols = set(row["material_symbols"])
    for cluster in clusters:
        if any(
            abs(row_published_at - int(candidate["published_at_ms"])) <= _MATERIAL_MATCH_WINDOW_MS
            and symbol_sets_compatible(row_symbols, set(candidate["material_symbols"]))
            for candidate in cluster
        ):
            return cluster
    return None


def _required_current_policy_material_text(row: Mapping[str, Any], field_name: str) -> str:
    value = row.get(field_name)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"news_dedup_current_policy_material_{field_name}_required")
    return value.strip()


def _required_current_policy_material_positive_int(row: Mapping[str, Any], field_name: str) -> int:
    value = row.get(field_name)
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ValueError(f"news_dedup_current_policy_material_{field_name}_required")
    return value


def _required_current_policy_material_impacts(row: Mapping[str, Any], field_name: str) -> object:
    if field_name not in row:
        raise ValueError(f"news_dedup_current_policy_material_{field_name}_required")
    value = row[field_name]
    if isinstance(value, str) or not isinstance(value, Mapping | list | tuple):
        raise ValueError(f"news_dedup_current_policy_material_{field_name}_required")
    return value


def _distinct_old_news_item_ids(old_news_item_ids: Sequence[str], *, news_item_id: str) -> list[str]:
    return [
        item_id
        for item_id in dict.fromkeys(str(item_id) for item_id in old_news_item_ids if str(item_id or "").strip())
        if item_id != str(news_item_id)
    ]


def _representative_payload_should_replace(existing: Mapping[str, Any], incoming: Mapping[str, Any]) -> bool:
    existing_ready = _representative_payload_ready(existing)
    incoming_ready = _representative_payload_ready(incoming)
    if incoming_ready != existing_ready:
        return incoming_ready

    existing_url_rank = _representative_url_rank(existing.get("canonical_url"))
    incoming_url_rank = _representative_url_rank(incoming.get("canonical_url"))
    if incoming_url_rank != existing_url_rank:
        return incoming_url_rank > existing_url_rank

    if str(incoming.get("provider_item_id") or "") == str(existing.get("provider_item_id") or ""):
        return True

    return _representative_tie_breaker(incoming) < _representative_tie_breaker(existing)


def _representative_payload_ready(payload: Mapping[str, Any]) -> bool:
    provider_signal = _json_dict(payload.get("provider_signal_json"))
    signal_status = str(provider_signal.get("status") or "").strip().lower()
    if signal_status:
        return signal_status == "ready"
    return str(payload.get("provider_payload_status") or "").strip().lower() == "ready"


def _representative_url_rank(value: Any) -> int:
    canonical_url = str(value or "").strip()
    if not canonical_url or canonical_url.startswith("opennews://item/"):
        return 0
    kind = url_identity_kind(canonical_url)
    if kind == "article":
        return 2
    if canonical_url.startswith(("http://", "https://")):
        return 1
    return 0


def _representative_tie_breaker(payload: Mapping[str, Any]) -> tuple[str, str, str, str]:
    return (
        str(payload.get("provider_article_key") or ""),
        str(payload.get("source_id") or ""),
        _representative_payload_hash(payload),
        str(payload.get("provider_item_id") or ""),
    )


def _representative_payload_hash(payload: Mapping[str, Any]) -> str:
    material = {
        "canonical_url": str(payload.get("canonical_url") or ""),
        "title": str(payload.get("title") or ""),
        "summary": str(payload.get("summary") or ""),
        "body_text": str(payload.get("body_text") or ""),
    }
    return hashlib.sha256(json.dumps(material, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _news_item_content_changed(existing: Mapping[str, Any], payload: Mapping[str, Any]) -> bool:
    fields = (
        "canonical_url",
        "title",
        "summary",
        "body_text",
        "language",
        "published_at_ms",
        "content_hash",
        "title_fingerprint",
    )
    for field_name in fields:
        if existing.get(field_name) != payload.get(field_name):
            return True
    return _json_dict(existing.get("provider_signal_json")) != _json_dict(
        payload.get("provider_signal_json")
    ) or _json_list(existing.get("provider_token_impacts_json")) != _json_list(
        payload.get("provider_token_impacts_json")
    )


def _news_item_aggregate_changed(existing: Mapping[str, Any], updated: Mapping[str, Any]) -> bool:
    return (
        _required_news_item_aggregate_nonnegative_int(existing, "duplicate_observation_count")
        != _required_news_item_aggregate_nonnegative_int(updated, "duplicate_observation_count")
        or _required_news_item_aggregate_list(existing, "source_ids_json")
        != _required_news_item_aggregate_list(updated, "source_ids_json")
        or _required_news_item_aggregate_list(existing, "source_domains_json")
        != _required_news_item_aggregate_list(updated, "source_domains_json")
        or _required_news_item_aggregate_list(existing, "provider_article_keys_json")
        != _required_news_item_aggregate_list(updated, "provider_article_keys_json")
    )


def _required_news_item_aggregate_nonnegative_int(row: Mapping[str, Any], field_name: str) -> int:
    value = row.get(field_name)
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError(f"news_item_aggregate_{field_name}_required")
    return int(value)


def _required_news_item_aggregate_list(row: Mapping[str, Any], field_name: str) -> list[Any]:
    value = row.get(field_name)
    if isinstance(value, str) or not isinstance(value, Sequence):
        raise ValueError(f"news_item_aggregate_{field_name}_required")
    return list(value)


def _news_item_edge_changed(existing: Mapping[str, Any], payload: Mapping[str, Any]) -> bool:
    fields = (
        "news_item_id",
        "source_id",
        "provider_article_key",
        "match_type",
        "match_confidence",
        "policy_version",
    )
    for field_name in fields:
        if existing.get(field_name) != payload.get(field_name):
            return True
    return _json_dict(existing.get("evidence_json")) != _json_dict(payload.get("evidence_json"))


def _comparable_source_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _comparable_source_value(item) for key, item in sorted(value.items())}
    if isinstance(value, list | tuple | set):
        return [_comparable_source_value(item) for item in value]
    return value


def _market_scope_payload(value: NewsMarketScope) -> dict[str, object]:
    if not isinstance(value, NewsMarketScope):
        raise ValueError("unsupported market scope payload shape")
    payload = {
        "scope": value.scope,
        "primary": value.primary,
        "status": value.status,
        "reason": value.reason,
        "basis": value.basis,
        "version": value.version,
    }
    return {
        "scope": _required_payload_list(payload, "scope", label="market scope payload"),
        "primary": _required_payload_text(payload, "primary", label="market scope payload"),
        "status": _required_payload_text(payload, "status", label="market scope payload"),
        "reason": _required_payload_text(payload, "reason", label="market scope payload"),
        "basis": _required_payload_mapping(payload, "basis", label="market scope payload"),
        "version": _required_payload_text(payload, "version", label="market scope payload"),
    }


def _agent_admission_payload(value: NewsItemAgentAdmission) -> dict[str, object]:
    if not isinstance(value, NewsItemAgentAdmission):
        raise ValueError("unsupported agent admission payload shape")
    return {
        "eligible": bool(value.eligible),
        "status": _required_payload_text({"status": value.status}, "status", label="agent admission payload"),
        "reason": _required_payload_text({"reason": value.reason}, "reason", label="agent admission payload"),
        "representative_news_item_id": _required_payload_text(
            {"representative_news_item_id": value.representative_news_item_id},
            "representative_news_item_id",
            label="agent admission payload",
        ),
        "basis": _required_payload_mapping({"basis": value.basis}, "basis", label="agent admission payload"),
        "version": _required_payload_text({"version": value.version}, "version", label="agent admission payload"),
    }


def _story_identity_payload(value: NewsStoryIdentity) -> dict[str, object]:
    if not isinstance(value, NewsStoryIdentity):
        raise ValueError("unsupported story identity payload shape")
    payload = {
        "story_key": value.story_key,
        "confidence": value.confidence,
        "basis": value.basis,
        "version": value.version,
    }
    return {
        "story_key": _required_payload_text(payload, "story_key", label="story identity payload"),
        "confidence": _required_payload_text(payload, "confidence", label="story identity payload"),
        "basis": _required_payload_mapping(payload, "basis", label="story identity payload"),
        "version": _required_payload_text(payload, "version", label="story identity payload"),
    }


def _agent_admission_mapping_payload(payload: Mapping[str, Any]) -> dict[str, object]:
    status = _required_page_nested_text(payload, "agent_admission", "status")
    reason = _required_page_nested_text(payload, "agent_admission", "reason")
    representative_news_item_id = _required_page_nested_text(
        payload,
        "agent_admission",
        "representative_news_item_id",
    )
    basis = _required_page_nested_mapping(payload, "agent_admission", "basis")
    version = _required_page_nested_text(payload, "agent_admission", "version")
    eligible = bool(payload.get("eligible")) if "eligible" in payload else status in {"eligible", "eligible_refresh"}
    return {
        "eligible": eligible,
        "status": status,
        "reason": reason,
        "representative_news_item_id": representative_news_item_id,
        "basis": basis,
        "version": version,
    }


def _required_page_nested_text(payload: Mapping[str, Any], object_name: str, field_name: str) -> str:
    value = payload.get(field_name)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"news_page_row_payload_required:{object_name}.{field_name}")
    return value.strip()


def _required_page_nested_mapping(payload: Mapping[str, Any], object_name: str, field_name: str) -> dict[str, object]:
    value = payload.get(field_name)
    if not isinstance(value, Mapping):
        raise ValueError(f"news_page_row_payload_required:{object_name}.{field_name}")
    return dict(value)


def _require_page_agent_admission_match(
    payload: Mapping[str, Any],
    agent_admission: Mapping[str, object],
    *,
    payload_field: str,
    admission_field: str,
) -> None:
    if payload[payload_field] != agent_admission[admission_field]:
        raise ValueError(f"news_page_row_payload_invalid:{payload_field}_mismatch")


def _required_payload_list(payload: Mapping[str, object], field: str, *, label: str) -> list[object]:
    value = payload.get(field)
    if isinstance(value, str) or not isinstance(value, list | tuple):
        raise ValueError(f"unsupported {label} shape: {field} must be list")
    if not value:
        raise ValueError(f"unsupported {label} shape: {field} must be non-empty")
    return list(value)


def _required_payload_text(payload: Mapping[str, object], field: str, *, label: str) -> str:
    value = str(payload.get(field) or "").strip()
    if not value:
        raise ValueError(f"unsupported {label} shape: blank {field}")
    return value


def _required_payload_nonnegative_int(payload: Mapping[str, Any], field: str, *, label: str) -> int:
    if field not in payload:
        raise ValueError(f"unsupported {label} shape: missing {field}")
    value = payload[field]
    if isinstance(value, bool):
        raise ValueError(f"unsupported {label} shape: {field} must be non-negative integer")
    try:
        resolved = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"unsupported {label} shape: {field} must be non-negative integer") from exc
    if resolved < 0:
        raise ValueError(f"unsupported {label} shape: {field} must be non-negative integer")
    return resolved


def _required_payload_mapping(payload: Mapping[str, object], field: str, *, label: str) -> dict[str, object]:
    value = payload.get(field)
    if not isinstance(value, Mapping):
        raise ValueError(f"unsupported {label} shape: {field} must be mapping")
    return dict(value)


def _public_observation_edge_payload(row: Mapping[str, Any]) -> dict[str, Any]:
    allowed = (
        "news_item_id",
        "source_id",
        "source_domain",
        "source_name",
        "source_role",
        "trust_tier",
        "enabled",
        "match_type",
        "match_confidence",
        "policy_version",
        "first_seen_at_ms",
        "last_seen_at_ms",
        "provider_payload_status",
        "provider_published_at_ms",
        "provider_observed_at_ms",
    )
    return {key: row.get(key) for key in allowed if key in row}


def _public_news_item_payload(row: Mapping[str, Any]) -> dict[str, Any]:
    allowed = (
        "news_item_id",
        "source_id",
        "source_domain",
        "canonical_url",
        "title",
        "summary",
        "body_text",
        "language",
        "published_at_ms",
        "fetched_at_ms",
        "lifecycle_status",
        "content_class",
        "processed_at_ms",
        "processing_error",
        "created_at_ms",
        "updated_at_ms",
        "duplicate_observation_count",
    )
    payload = {key: row.get(key) for key in allowed if key in row}
    payload["canonical_url"] = _public_url(payload.get("canonical_url"))
    return payload


def _public_provider_observation_payload(row: Mapping[str, Any]) -> dict[str, Any]:
    allowed = (
        "source_id",
        "canonical_url",
        "fetched_at_ms",
        "provider_payload_status",
        "provider_published_at_ms",
        "provider_observed_at_ms",
        "source_domain",
        "source_name",
        "source_role",
        "trust_tier",
        "enabled",
    )
    payload = {key: row.get(key) for key in allowed if key in row}
    payload["canonical_url"] = _public_url(payload.get("canonical_url"))
    return payload


def _public_source_payload(row: Mapping[str, Any]) -> dict[str, Any]:
    allowed = (
        "source_id",
        "provider_type",
        "source_domain",
        "source_name",
        "source_role",
        "trust_tier",
        "coverage_tags_json",
        "asset_universe_json",
        "authority_scope_json",
        "source_quality_status",
        "enabled",
        "managed_by_config",
        "refresh_interval_seconds",
        "created_at_ms",
        "updated_at_ms",
    )
    payload = {key: row.get(key) for key in allowed if key in row}
    if "coverage_tags_json" in payload:
        payload["coverage_tags"] = _json_list(payload.pop("coverage_tags_json"))
    if "asset_universe_json" in payload:
        payload["asset_universe"] = _json_list(payload.pop("asset_universe_json"))
    if "authority_scope_json" in payload:
        payload["authority_scope"] = _json_dict(payload.pop("authority_scope_json"))
    return payload


def _public_fetch_run_payload(row: Mapping[str, Any]) -> dict[str, Any]:
    allowed = (
        "source_id",
        "status",
        "started_at_ms",
        "finished_at_ms",
        "fetched_count",
        "inserted_count",
        "updated_count",
        "duplicate_count",
        "http_status",
        "error",
        "created_at_ms",
    )
    payload = {key: row.get(key) for key in allowed if key in row}
    if "error" in payload:
        payload["error"] = _compact_error(payload.get("error"))
    return payload


def _public_agent_brief_payload(value: Any) -> dict[str, Any]:
    payload = _json_dict(value)
    public_fields = (
        "status",
        "direction",
        "decision_class",
        "event_type",
        "market_domains",
        "title_zh",
        "summary_zh",
        "market_read_zh",
        "bull_view",
        "bear_view",
        "affected_entities",
        "transmission_paths",
        "watch_triggers",
        "invalidation_conditions",
        "data_gaps",
        "evidence_refs",
        "computed_at_ms",
        "data_gap_count",
        "market_impacts",
        "bull_strength",
        "bear_strength",
    )
    public_payload = {key: payload.get(key) for key in public_fields if key in payload}
    public_payload["status"] = _required_public_agent_brief_text(payload, "status")
    if public_payload["status"] == "ready":
        public_payload["direction"] = _required_public_agent_brief_text(public_payload, "direction")
        public_payload["decision_class"] = _required_public_agent_brief_text(public_payload, "decision_class")
    for field_name in (
        "event_type",
        "title_zh",
        "summary_zh",
        "market_read_zh",
        "bull_strength",
        "bear_strength",
    ):
        if field_name in public_payload:
            text_value = _validate_public_agent_brief_text_field(public_payload, field_name)
            if text_value is None:
                public_payload.pop(field_name, None)
            else:
                public_payload[field_name] = text_value
    for field_name in ("bull_view", "bear_view"):
        if field_name in public_payload:
            public_payload[field_name] = _validate_public_agent_brief_mapping_field(public_payload, field_name)
    if "affected_entities" in public_payload:
        public_payload["affected_entities"] = [
            _validate_public_agent_brief_affected_entity(entity)
            for entity in _required_public_agent_brief_list(public_payload, "affected_entities")
        ]
    for list_key in ("transmission_paths", "market_domains", "market_impacts"):
        if list_key in public_payload:
            public_payload[list_key] = _required_public_agent_brief_list(public_payload, list_key)
    for list_key in ("data_gaps", "evidence_refs", "watch_triggers", "invalidation_conditions"):
        if list_key in public_payload:
            public_payload[list_key] = _required_public_agent_brief_list(public_payload, list_key)
    if "data_gap_count" not in public_payload and "data_gaps" in public_payload:
        public_payload["data_gap_count"] = len(_required_public_agent_brief_list(public_payload, "data_gaps"))
    for field_name in ("computed_at_ms", "data_gap_count"):
        if field_name in public_payload:
            public_payload[field_name] = _validate_public_agent_brief_nonnegative_int_field(
                public_payload,
                field_name,
            )
    return public_payload


def _validate_public_agent_brief_text_field(payload: Mapping[str, Any], field_name: str) -> str | None:
    value = payload.get(field_name)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"news_public_agent_brief_{field_name}_required")
    text = value.strip()
    if not text:
        return None
    return text


def _validate_public_agent_brief_mapping_field(payload: Mapping[str, Any], field_name: str) -> dict[str, Any]:
    value = payload.get(field_name)
    if not isinstance(value, Mapping):
        raise ValueError(f"news_public_agent_brief_{field_name}_required")
    return dict(value)


def _validate_public_agent_brief_nonnegative_int_field(payload: Mapping[str, Any], field_name: str) -> int:
    value = payload.get(field_name)
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError(f"news_public_agent_brief_{field_name}_required")
    return value


def _validate_public_agent_brief_affected_entity(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("news_public_agent_brief_affected_entities_required")
    entity = dict(value)
    payload: dict[str, Any] = {}
    for key in (
        "label",
        "symbol",
        "name",
        "entity_type",
        "market_domain",
        "resolution_status",
        "target_type",
        "target_id",
        "impact_direction",
        "reason_zh",
    ):
        text = _optional_public_agent_brief_affected_entity_text(entity, key)
        if text is not None:
            payload[key] = text
    evidence_refs = _optional_public_agent_brief_affected_entity_string_list(entity, "evidence_refs")
    if evidence_refs is not None:
        payload["evidence_refs"] = evidence_refs
    return payload


def _optional_public_agent_brief_affected_entity_text(entity: Mapping[str, Any], field_name: str) -> str | None:
    if field_name not in entity or entity.get(field_name) is None:
        return None
    value = entity.get(field_name)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"news_public_agent_brief_affected_entities_{field_name}_required")
    return value.strip()


def _optional_public_agent_brief_affected_entity_string_list(
    entity: Mapping[str, Any],
    field_name: str,
) -> list[str] | None:
    if field_name not in entity or entity.get(field_name) is None:
        return None
    values = entity.get(field_name)
    if not isinstance(values, list):
        raise ValueError(f"news_public_agent_brief_affected_entities_{field_name}_required")
    refs: list[str] = []
    for value in values:
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"news_public_agent_brief_affected_entities_{field_name}_required")
        refs.append(value.strip())
    return refs


def _required_public_agent_brief_list(payload: Mapping[str, Any], field_name: str) -> list[Any]:
    value = payload.get(field_name)
    if not isinstance(value, list):
        raise ValueError(f"news_public_agent_brief_{field_name}_required")
    return list(value)


def _required_public_agent_brief_text(payload: Mapping[str, Any], field_name: str) -> str:
    value = payload.get(field_name)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"news_public_agent_brief_{field_name}_required")
    return value.strip()


def _public_url(value: Any) -> str:
    url = str(value or "").strip()
    if url.startswith(("http://", "https://")):
        return url
    return ""


def _json_dict(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, Mapping):
        return dict(value)
    return {}


def _quoted_constraint_values(constraint_def: str) -> tuple[str, ...]:
    values: list[str] = []
    for match in _CHECK_QUOTED_VALUE_RE.finditer(str(constraint_def or "")):
        value = match.group(1).replace("''", "'")
        if value:
            values.append(value)
    return tuple(dict.fromkeys(values))


def _json_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return []


def _string_list(value: Any) -> list[str]:
    if isinstance(value, list | tuple):
        return [str(item) for item in value if str(item)]
    return []


def _compact_text(value: Any, *, max_length: int) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= max_length:
        return text
    return text[: max(0, max_length - 3)].rstrip() + "..."


def _required_fetch_run_count(field_name: str, *values: int | None) -> int:
    for value in values:
        if value is not None:
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise ValueError(f"news_fetch_run_{field_name}_required")
            return int(value)
    raise ValueError(f"news_fetch_run_{field_name}_required")


def _required_fetch_run_completion_status(status: Any) -> str:
    if not isinstance(status, str) or status.strip() not in {"success", "failed"}:
        raise ValueError("news_fetch_run_status_required")
    return status.strip()


def _required_fetch_run_finished_at_ms(value: Any) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError("news_fetch_run_finished_at_ms_required")
    return int(value)


def _optional_fetch_run_http_status(value: Any) -> int | None:
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError("news_fetch_run_http_status_required")
    return int(value)


def _optional_fetch_run_extra_json(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise ValueError("news_fetch_run_extra_json_required")
    return dict(value)


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    return int(value)


def _positive_optional_int(value: Any) -> int | None:
    item = _optional_int(value)
    if item is None or item <= 0:
        return None
    return item


def _max_optional_int(*values: int | None) -> int | None:
    normalized = [int(value) for value in values if value is not None]
    if not normalized:
        return None
    return max(normalized)


def _latest_fetch_run_payload(row: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {
        "status": _required_latest_fetch_run_text(row, "status"),
        "started_at_ms": _optional_int(row.get("started_at_ms")),
        "finished_at_ms": _positive_optional_int(row.get("finished_at_ms")),
        "http_status": _optional_int(row.get("http_status")),
        "fetched_count": _required_latest_fetch_run_nonnegative_int(row, "fetched_count"),
        "inserted_count": _required_latest_fetch_run_nonnegative_int(row, "inserted_count"),
        "updated_count": _required_latest_fetch_run_nonnegative_int(row, "updated_count"),
        "duplicate_count": _required_latest_fetch_run_nonnegative_int(row, "duplicate_count"),
        "error": _compact_error(row.get("error")),
    }


def _required_latest_fetch_run_text(row: Mapping[str, Any], field_name: str) -> str:
    value = row.get(field_name)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"news_source_status_latest_fetch_run_{field_name}_required")
    return value.strip()


def _required_latest_fetch_run_nonnegative_int(row: Mapping[str, Any], field_name: str) -> int:
    value = row.get(field_name)
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError(f"news_source_status_latest_fetch_run_{field_name}_required")
    return value


def _provider_health_payload(
    *,
    enabled: bool,
    consecutive_failures: int,
    source_quality_status: str,
    last_error: str | None,
    last_success_at_ms: int | None,
    last_seen_at_ms: int | None,
) -> dict[str, Any]:
    if not enabled:
        status = "disabled"
        reason = "source_disabled"
    elif consecutive_failures > 0:
        status = "failing"
        reason = "consecutive_failures"
    elif source_quality_status in {"healthy", "degraded", "poor"}:
        status = source_quality_status
        reason = "fetch_health"
    elif last_seen_at_ms is not None:
        status = "unknown"
        reason = "observed_without_quality"
    else:
        status = "unknown"
        reason = "no_observations"
    return {
        "status": status,
        "reason": reason,
        "last_error": last_error,
        "consecutive_failures": consecutive_failures,
        "last_success_at_ms": last_success_at_ms,
        "last_seen_at_ms": last_seen_at_ms,
    }


def _provider_capability_tags(*, provider_type: str, source_role: str, trust_tier: str) -> list[str]:
    normalized_provider_type = provider_type.strip().lower()
    normalized_source_role = source_role.strip().lower()
    normalized_trust_tier = trust_tier.strip().lower()
    tags: list[str] = []
    if normalized_provider_type in {"rss", "atom", "json_feed"}:
        tags.extend(["poll_primary_items", "http_cache"])
    elif normalized_provider_type in {"cryptopanic", "manual_api", "openbb", "github", "ossinsight"}:
        tags.extend(["poll_primary_items", "api_backed"])
    elif normalized_provider_type in {
        "twitter_profile",
        "twitter_thread_context",
        "reddit",
        "telegram_public",
        "hackernews",
    }:
        tags.extend(["poll_primary_items", "browser_backed"])
    else:
        tags.append("poll_primary_items")
    if normalized_source_role.startswith("official_") or normalized_trust_tier == "official":
        tags.append("official_source")
    if normalized_trust_tier in {"official", "high"}:
        tags.append("high_trust")
    return list(dict.fromkeys(tags))


def _json(value: Any) -> Jsonb:
    if isinstance(value, Jsonb):
        return value
    return Jsonb(value, dumps=lambda item: json.dumps(item, ensure_ascii=False, sort_keys=True))


def _current_read_model_payload_hash(payload: Mapping[str, Any], *, exclude: set[str]) -> str:
    return stable_current_payload_hash(
        {key: _current_hash_payload_value(value) for key, value in payload.items() if key not in exclude}
    )


def _current_hash_payload_value(value: Any) -> Any:
    if isinstance(value, Jsonb):
        return _current_hash_payload_value(value.obj)
    if isinstance(value, Mapping):
        return {key: _current_hash_payload_value(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_current_hash_payload_value(item) for item in value]
    return value


def _compact_error(error: str | None) -> str | None:
    if not error:
        return None
    return _redact_error_text(str(error))[:2_000]


def _redact_error_text(value: str) -> str:
    text = _URL_USERINFO_RE.sub(rf"\1{_REDACTED}@", value)
    text = _SECRET_HEADER_RE.sub(lambda match: f"{match.group(1)}: {_REDACTED}", text)
    text = _BEARER_RE.sub(f"Bearer {_REDACTED}", text)
    text = _SECRET_QUERY_RE.sub(rf"\1{_REDACTED}", text)
    text = _SECRET_QUOTED_KEY_VALUE_RE.sub(
        lambda match: f"{match.group(1)}{match.group(2)}{_REDACTED}{match.group(2)}",
        text,
    )
    return _SECRET_KEY_VALUE_RE.sub(rf"\1\2{_REDACTED}\3", text)
