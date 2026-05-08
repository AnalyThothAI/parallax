from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from typing import Any
from urllib.parse import urlparse

from gmgn_twitter_intel.retrieval.token_target_stage_builder import build_token_target_stages

WINDOW_MS = {
    "5m": 5 * 60 * 1000,
    "1h": 60 * 60 * 1000,
    "4h": 4 * 60 * 60 * 1000,
    "24h": 24 * 60 * 60 * 1000,
}

_URL_RE = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)
_CASHTAG_RE = re.compile(r"(?<![A-Za-z0-9_])\$([A-Za-z][A-Za-z0-9_]{1,20})")
_CA_RE = re.compile(r"\b0x[a-fA-F0-9]{40}\b")
_NON_WORD_RE = re.compile(r"[^\w\s]+", re.UNICODE)


def build_pulse_timeline_context(
    *,
    target: dict[str, Any],
    rows: list[dict[str, Any]],
    window: str = "1h",
    scope: str = "all",
    now_ms: int | None = None,
    radar_score: dict[str, Any] | None = None,
    market_overlay: dict[str, Any] | None = None,
    max_selected_posts: int = 24,
    max_post_clusters: int = 16,
    max_raw_text_chars_per_post: int = 280,
) -> dict[str, Any]:
    ordered = sorted(_scope_rows(rows, scope), key=_row_sort_key)
    resolved_now_ms = _resolve_now_ms(ordered, now_ms)
    active_window_ms = WINDOW_MS.get(window, WINDOW_MS["1h"])
    active_rows = [
        row for row in ordered if int(row.get("received_at_ms") or 0) >= resolved_now_ms - active_window_ms
    ]
    all_row_infos = [_row_info(row, target=target) for row in ordered]
    row_infos = [
        info for info in all_row_infos if int(info["received_at_ms"]) >= resolved_now_ms - active_window_ms
    ]
    cluster_infos = _build_clusters(row_infos, target_id=_target_id(target))
    cluster_by_event_id = {
        event_id: cluster
        for cluster in cluster_infos
        for event_id in cluster["event_ids"]
    }
    stage_segments, stage_representative_ids = _stage_segments(active_rows)
    selected_posts = _selected_posts(
        row_infos,
        cluster_by_event_id=cluster_by_event_id,
        stage_representative_ids=stage_representative_ids,
        max_selected_posts=max_selected_posts,
        max_raw_text_chars_per_post=max_raw_text_chars_per_post,
    )
    post_clusters = [_public_cluster(cluster) for cluster in cluster_infos[: max(0, int(max_post_clusters))]]
    risk_flags = _risk_flags(active_rows, row_infos, cluster_infos)
    phase = _active_phase(stage_segments)
    windows = {
        label: _window_summary(
            ordered,
            all_row_infos,
            resolved_now_ms=resolved_now_ms,
            window_ms=duration_ms,
        )
        for label, duration_ms in WINDOW_MS.items()
    }

    return {
        "target": _jsonable(target),
        "windows": windows,
        "stage_segments": stage_segments,
        "post_clusters": post_clusters,
        "selected_posts": selected_posts,
        "market_overlay": (
            _jsonable(market_overlay) if market_overlay is not None else _market_overlay(active_rows, target)
        ),
        "radar_score": _jsonable(radar_score) if radar_score is not None else None,
        "timeline_signature": _timeline_signature(
            target_id=_target_id(target),
            window=window,
            phase=phase,
            selected_posts=selected_posts,
            post_clusters=post_clusters,
            stage_segments=stage_segments,
            author_count=len({_author(row) for row in active_rows if _author(row)}),
            duplicate_text_share=windows.get(window, windows["1h"])["duplicate_text_share"],
            price_change_since_social_pct=windows.get(window, windows["1h"])["price_change_since_social_pct"],
            risk_flags=risk_flags,
        ),
    }


def _scope_rows(rows: list[dict[str, Any]], scope: str) -> list[dict[str, Any]]:
    if scope == "matched":
        return [row for row in rows if row.get("is_watched")]
    return list(rows)


def _row_info(row: dict[str, Any], *, target: dict[str, Any]) -> dict[str, Any]:
    text = _text(row)
    normalized_text = _normalized_text(text)
    normalized_text_hash = _sha256(normalized_text)
    cashtags = _cashtags(row, text, target=target)
    primary_domain = _primary_url_domain(text)
    target_id = str(row.get("target_id") or _target_id(target))
    target_symbol = str(target.get("symbol") or "").lstrip("$").upper()
    semantic_key = "\x1f".join([normalized_text, primary_domain, ",".join(cashtags), target_id])
    return {
        "row": row,
        "event_id": str(row.get("event_id") or ""),
        "author": _author(row),
        "received_at_ms": int(row.get("received_at_ms") or 0),
        "text": text,
        "normalized_text": normalized_text,
        "normalized_text_hash": normalized_text_hash,
        "cashtags": cashtags,
        "primary_domain": primary_domain,
        "target_symbol": target_symbol,
        "semantic_cluster_key": semantic_key,
        "cluster_id": f"cluster:{_sha256(semantic_key)[:16]}",
    }


def _build_clusters(row_infos: list[dict[str, Any]], *, target_id: str) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for info in row_infos:
        grouped.setdefault(str(info["semantic_cluster_key"]), []).append(info)

    clusters = []
    for key in sorted(grouped):
        infos = sorted(grouped[key], key=lambda info: (int(info["received_at_ms"]), str(info["event_id"])))
        kept_infos = _first_latest_per_author(infos)
        authors = _ordered_unique(str(info["author"]) for info in infos if info["author"])
        cluster_id = str(infos[0]["cluster_id"])
        clusters.append(
            {
                "cluster_id": cluster_id,
                "cluster_type": _cluster_type(infos, target_id=target_id),
                "representative_event_id": str(kept_infos[0]["event_id"]) if kept_infos else None,
                "event_ids": [str(info["event_id"]) for info in kept_infos if info["event_id"]],
                "authors": authors,
                "watched_author_present": any(info["row"].get("is_watched") for info in infos),
                "text_excerpt": _truncate(str(kept_infos[0]["text"]) if kept_infos else "", 280),
                "first_seen_ms": int(infos[0]["received_at_ms"]),
                "latest_seen_ms": int(infos[-1]["received_at_ms"]),
                "duplicate_text_share": _duplicate_share(infos),
            }
        )
    return sorted(clusters, key=lambda item: (int(item["first_seen_ms"]), str(item["cluster_id"])))


def _first_latest_per_author(infos: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_author: dict[str, list[dict[str, Any]]] = {}
    for info in infos:
        by_author.setdefault(str(info["author"] or ""), []).append(info)
    kept: dict[str, dict[str, Any]] = {}
    for author_infos in by_author.values():
        ordered = sorted(author_infos, key=lambda info: (int(info["received_at_ms"]), str(info["event_id"])))
        for info in (ordered[0], ordered[-1]):
            if info["event_id"]:
                kept[str(info["event_id"])] = info
    return sorted(kept.values(), key=lambda info: (int(info["received_at_ms"]), str(info["event_id"])))


def _public_cluster(cluster: dict[str, Any]) -> dict[str, Any]:
    return {
        "cluster_id": cluster["cluster_id"],
        "cluster_type": cluster["cluster_type"],
        "representative_event_id": cluster["representative_event_id"],
        "event_ids": cluster["event_ids"],
        "authors": cluster["authors"],
        "watched_author_present": cluster["watched_author_present"],
        "text_excerpt": cluster["text_excerpt"],
        "first_seen_ms": cluster["first_seen_ms"],
        "latest_seen_ms": cluster["latest_seen_ms"],
        "duplicate_text_share": cluster["duplicate_text_share"],
    }


def _stage_segments(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], set[str]]:
    if not rows:
        return [], set()
    stage_build = build_token_target_stages(rows)
    segments = []
    representative_ids: set[str] = set()
    for stage in stage_build.stages:
        ids = [str(event_id) for event_id in stage.get("representative_event_ids", []) if event_id]
        representative_ids.update(ids)
        segments.append(
            {
                "phase": stage.get("phase") or "unknown",
                "start_ms": stage.get("start_ms"),
                "end_ms": stage.get("end_ms"),
                "representative_event_ids": ids,
                "summary_facts": {
                    "posts": stage.get("people", {}).get("posts", 0),
                    "authors": stage.get("people", {}).get("authors", 0),
                    "watched_posts": stage.get("people", {}).get("watched_posts", 0),
                    "top_author_share": stage.get("people", {}).get("top_author_share", 0.0),
                    "price_delta_pct": stage.get("price", {}).get("delta_pct"),
                    "risks": list(stage.get("risks", [])),
                },
            }
        )
    return segments, representative_ids


def _selected_posts(
    row_infos: list[dict[str, Any]],
    *,
    cluster_by_event_id: dict[str, dict[str, Any]],
    stage_representative_ids: set[str],
    max_selected_posts: int,
    max_raw_text_chars_per_post: int,
) -> list[dict[str, Any]]:
    priority_role_rows: list[tuple[str, dict[str, Any]]] = []
    if row_infos:
        priority_role_rows.append(("first_seed", row_infos[0]))
        priority_role_rows.append(("latest", row_infos[-1]))
    priority_role_rows.extend(
        ("stage_representative", info) for info in row_infos if info["event_id"] in stage_representative_ids
    )
    inflection = _price_inflection_info(row_infos)
    if inflection is not None:
        priority_role_rows.append(("price_inflection", inflection))
    concentration = _duplicate_or_concentration_risk_info(row_infos)
    if concentration is not None:
        priority_role_rows.append(("duplicate_or_concentration_risk", concentration))

    bulk_role_rows: list[tuple[str, dict[str, Any]]] = []
    bulk_role_rows.extend(("watched_author", info) for info in row_infos if info["row"].get("is_watched"))
    bulk_role_rows.extend(
        ("direct_ca_or_ticker_evidence", info) for info in row_infos if _has_direct_target_evidence(info)
    )
    bulk_role_rows.extend(("new_independent_author", info) for info in _new_independent_authors(row_infos))

    selected: dict[str, dict[str, Any]] = {}
    max_posts = max(0, int(max_selected_posts))
    for role, info in [*priority_role_rows, *bulk_role_rows]:
        event_id = str(info["event_id"])
        if not event_id or event_id not in cluster_by_event_id:
            continue
        if event_id in selected:
            if role not in selected[event_id]["roles"]:
                selected[event_id]["roles"].append(role)
            continue
        if len(selected) >= max_posts:
            continue
        selected[event_id] = {"info": info, "roles": [role]}

    items = []
    for role, info in sorted(
        ((item["roles"][0], item["info"]) for item in selected.values()),
        key=lambda item: (int(item[1]["received_at_ms"]), str(item[1]["event_id"])),
    ):
        cluster = cluster_by_event_id.get(str(info["event_id"]))
        roles = selected[str(info["event_id"])]["roles"]
        items.append(
            {
                "event_id": str(info["event_id"]),
                "author_handle": str(info["author"]),
                "text": _truncate(str(info["text"]), max_raw_text_chars_per_post),
                "role": role,
                "roles": roles,
                "received_at_ms": int(info["received_at_ms"]),
                "cluster_id": cluster["cluster_id"] if cluster else str(info["cluster_id"]),
            }
        )
    return items


def _window_summary(
    ordered_rows: list[dict[str, Any]],
    row_infos: list[dict[str, Any]],
    *,
    resolved_now_ms: int,
    window_ms: int,
) -> dict[str, Any]:
    since_ms = resolved_now_ms - window_ms
    rows = [row for row in ordered_rows if int(row.get("received_at_ms") or 0) >= since_ms]
    authors = [_author(row) for row in rows if _author(row)]
    infos = [info for info in row_infos if int(info["received_at_ms"]) >= since_ms]
    return {
        "mentions": len(rows),
        "authors": len(set(authors)),
        "watched_mentions": sum(1 for row in rows if row.get("is_watched")),
        "phase": _summary_phase(rows),
        "top_author_share": _top_author_share(rows),
        "duplicate_text_share": _duplicate_text_share(infos),
        "price_change_since_social_pct": _latest_price_change(rows),
    }


def _timeline_signature(
    *,
    target_id: str,
    window: str,
    phase: str,
    selected_posts: list[dict[str, Any]],
    post_clusters: list[dict[str, Any]],
    stage_segments: list[dict[str, Any]],
    author_count: int,
    duplicate_text_share: float,
    price_change_since_social_pct: float | None,
    risk_flags: list[str],
) -> str:
    payload = {
        "target_id": target_id,
        "window": window,
        "phase": phase,
        "selected_event_ids": [post["event_id"] for post in selected_posts],
        "selected_event_roles": [
            {
                "event_id": post["event_id"],
                "role": post["role"],
                "roles": post.get("roles", [post["role"]]),
            }
            for post in selected_posts
        ],
        "cluster_ids": [cluster["cluster_id"] for cluster in post_clusters],
        "cluster_fingerprints": [
            {
                "cluster_id": cluster["cluster_id"],
                "event_ids": cluster.get("event_ids", []),
                "latest_seen_ms": cluster.get("latest_seen_ms"),
                "duplicate_text_share": cluster.get("duplicate_text_share"),
            }
            for cluster in post_clusters
        ],
        "stage_fingerprints": [
            {
                "phase": segment.get("phase"),
                "start_ms": segment.get("start_ms"),
                "end_ms": segment.get("end_ms"),
                "representative_event_ids": segment.get("representative_event_ids", []),
            }
            for segment in stage_segments
        ],
        "author_count_bucket": _author_count_bucket(author_count),
        "duplicate_share_bucket": _share_bucket(duplicate_text_share),
        "price_change_bucket": _price_change_bucket(price_change_since_social_pct),
        "risk_flags": sorted(risk_flags),
    }
    return _sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")))


def _normalized_text(text: str) -> str:
    without_urls = _URL_RE.sub(" ", text.lower())
    without_punctuation = _NON_WORD_RE.sub(" ", without_urls)
    return re.sub(r"\s+", " ", without_punctuation).strip()


def _text(row: dict[str, Any]) -> str:
    for key in ("text", "search_text", "text_clean", "content"):
        value = row.get(key)
        if value:
            return str(value)
    return ""


def _cashtags(row: dict[str, Any], text: str, *, target: dict[str, Any]) -> list[str]:
    values: list[str] = []
    for item in row.get("cashtags") or []:
        values.append(str(item).lstrip("$").upper())
    entities = row.get("entities") if isinstance(row.get("entities"), dict) else {}
    for item in entities.get("cashtags") or []:
        values.append(str(item).lstrip("$").upper())
    values.extend(match.group(1).upper() for match in _CASHTAG_RE.finditer(text))
    symbol = str(row.get("symbol") or target.get("symbol") or "").lstrip("$").upper()
    if symbol and re.search(rf"(?<![A-Za-z0-9_]){re.escape(symbol)}(?![A-Za-z0-9_])", text, re.IGNORECASE):
        values.append(symbol)
    return sorted({value for value in values if value})


def _primary_url_domain(text: str) -> str:
    urls = _URL_RE.findall(text)
    if not urls:
        return ""
    url = urls[0]
    if url.startswith("www."):
        url = f"https://{url}"
    domain = urlparse(url).netloc.lower()
    return domain[4:] if domain.startswith("www.") else domain


def _has_direct_target_evidence(info: dict[str, Any]) -> bool:
    row = info["row"]
    symbol = str(row.get("symbol") or info.get("target_symbol") or "").lstrip("$").upper()
    text = str(info["text"])
    text_upper = text.upper()
    entities = row.get("entities") if isinstance(row.get("entities"), dict) else {}
    has_ca = bool(_CA_RE.search(text) or entities.get("contract_addresses"))
    return has_ca or bool(symbol and (f"${symbol}" in text_upper or symbol in info["cashtags"]))


def _price_inflection_info(row_infos: list[dict[str, Any]]) -> dict[str, Any] | None:
    with_price = [
        info
        for info in row_infos
        if _number(info["row"].get("price_change_since_social_pct")) is not None
    ]
    if not with_price:
        return None
    return max(
        with_price,
        key=lambda info: (
            abs(float(info["row"].get("price_change_since_social_pct") or 0)),
            int(info["received_at_ms"]),
            str(info["event_id"]),
        ),
    )


def _new_independent_authors(row_infos: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    new_authors = []
    for info in row_infos:
        author = str(info["author"])
        if not author or author in seen:
            continue
        seen.add(author)
        if len(seen) > 1:
            new_authors.append(info)
    return new_authors


def _duplicate_or_concentration_risk_info(row_infos: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not row_infos:
        return None
    text_counts = Counter(str(info["normalized_text_hash"]) for info in row_infos if info["normalized_text"])
    duplicate_hashes = {key for key, count in text_counts.items() if count > 1}
    for info in row_infos:
        if str(info["normalized_text_hash"]) in duplicate_hashes:
            return info
    author_counts = Counter(str(info["author"]) for info in row_infos if info["author"])
    if author_counts and max(author_counts.values()) / len(row_infos) >= 0.5 and len(row_infos) >= 3:
        top_author = author_counts.most_common(1)[0][0]
        return next(info for info in row_infos if info["author"] == top_author)
    return None


def _risk_flags(
    rows: list[dict[str, Any]],
    row_infos: list[dict[str, Any]],
    clusters: list[dict[str, Any]],
) -> list[str]:
    flags = []
    if _duplicate_text_share(row_infos) >= 0.25:
        flags.append("duplicate_text")
    if _top_author_share(rows) >= 0.5 and len(rows) >= 3:
        flags.append("author_concentration")
    if any(cluster["watched_author_present"] and len(cluster["authors"]) > 1 for cluster in clusters):
        flags.append("watched_amplified_duplicate")
    return flags


def _cluster_type(infos: list[dict[str, Any]], *, target_id: str) -> str:
    authors = {str(info["author"]) for info in infos if info["author"]}
    if len(authors) > 1:
        return "multi_author_duplicate"
    if len(infos) > 1:
        return "same_author_repeat"
    if target_id:
        return "target_evidence"
    return "single_post"


def _duplicate_text_share(infos: list[dict[str, Any]]) -> float:
    if len(infos) <= 1:
        return 0.0
    counts = Counter(str(info["normalized_text_hash"]) for info in infos if info["normalized_text"])
    duplicate_posts = sum(count for count in counts.values() if count > 1)
    return round(duplicate_posts / len(infos), 6)


def _duplicate_share(infos: list[dict[str, Any]]) -> float:
    if len(infos) <= 1:
        return 0.0
    return round((len(infos) - 1) / len(infos), 6)


def _latest_price_change(rows: list[dict[str, Any]]) -> float | None:
    for row in reversed(rows):
        value = _number(row.get("price_change_since_social_pct"))
        if value is not None:
            return value
    return None


def _summary_phase(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "unknown"
    authors = len({_author(row) for row in rows if _author(row)})
    top_share = _top_author_share(rows)
    price_change = _latest_price_change(rows)
    if len(rows) <= 1:
        return "seed"
    if price_change is not None and abs(price_change) >= 0.5:
        return "chase"
    if len(rows) >= 3 and top_share >= 0.75:
        return "concentration"
    if len(rows) >= 4 and authors >= 3:
        return "expansion"
    return "ignition"


def _market_overlay(rows: list[dict[str, Any]], target: dict[str, Any]) -> dict[str, Any] | None:
    source = rows[0] if rows else target
    if not source and not target:
        return None
    keys = (
        "target_type",
        "target_id",
        "chain_id",
        "address",
        "symbol",
        "provider",
        "native_market_id",
        "quote_symbol",
        "feed_type",
        "pricefeed_id",
    )
    overlay = {key: source.get(key, target.get(key)) for key in keys if source.get(key, target.get(key)) is not None}
    return overlay or None


def _active_phase(stage_segments: list[dict[str, Any]]) -> str:
    if not stage_segments:
        return "unknown"
    return str(stage_segments[-1].get("phase") or "unknown")


def _author(row: dict[str, Any]) -> str:
    return str(row.get("author_handle") or "").strip()


def _target_id(target: dict[str, Any]) -> str:
    return str(target.get("target_id") or target.get("id") or "")


def _row_sort_key(row: dict[str, Any]) -> tuple[int, str]:
    return (int(row.get("received_at_ms") or 0), str(row.get("event_id") or ""))


def _resolve_now_ms(rows: list[dict[str, Any]], now_ms: int | None) -> int:
    if now_ms is not None:
        return int(now_ms)
    if rows:
        return max(int(row.get("received_at_ms") or 0) for row in rows)
    return 0


def _top_author_share(rows: list[dict[str, Any]]) -> float:
    if not rows:
        return 0.0
    counts = Counter(_author(row) for row in rows if _author(row))
    return round((max(counts.values()) / len(rows)) if counts else 0.0, 6)


def _author_count_bucket(count: int) -> str:
    if count <= 1:
        return "0-1"
    if count <= 3:
        return "2-3"
    if count <= 8:
        return "4-8"
    return "9+"


def _share_bucket(value: float) -> str:
    if value <= 0:
        return "none"
    if value < 0.25:
        return "low"
    if value < 0.5:
        return "medium"
    return "high"


def _price_change_bucket(value: float | None) -> str:
    if value is None:
        return "unknown"
    absolute = abs(float(value))
    if absolute < 0.05:
        return "flat"
    if absolute < 0.25:
        return "moving"
    if absolute < 0.5:
        return "hot"
    return "extreme"


def _ordered_unique(values: Any) -> list[str]:
    seen: set[str] = set()
    result = []
    for value in values:
        item = str(value)
        if item and item not in seen:
            seen.add(item)
            result.append(item)
    return result


def _truncate(text: str, max_chars: int) -> str:
    limit = max(0, int(max_chars))
    if len(text) <= limit:
        return text
    return text[:limit]


def _number(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _jsonable(value: Any) -> Any:
    return json.loads(json.dumps(value, default=str, sort_keys=True))


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
