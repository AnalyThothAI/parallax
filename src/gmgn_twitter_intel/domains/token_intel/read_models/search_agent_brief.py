from __future__ import annotations

from typing import Any

SCHEMA_VERSION = "search_agent_brief_v1"


def build_token_agent_brief(
    *,
    target: dict[str, Any],
    timeline: dict[str, Any],
    posts: dict[str, Any] | list[dict[str, Any]],
    radar_item: dict[str, Any] | None,
) -> dict[str, Any]:
    del radar_item
    post_items = _post_items(posts)
    summary = _dict(timeline.get("summary"))
    stages = [_dict(item) for item in _list(timeline.get("stages"))]
    authors = [_dict(item) for item in _list(timeline.get("authors"))]
    symbol = _target_symbol(target, post_items)
    evidence_ids = _evidence_ids(post_items)
    phase = str(summary.get("phase") or _last_phase(stages) or "unknown")
    posts_count = int(summary.get("posts") or len(post_items))
    authors_count = int(summary.get("authors") or len({item.get("author_handle") for item in post_items}))
    watched_posts = int(summary.get("watched_posts") or sum(1 for item in post_items if item.get("is_watched")))
    top_author_share = float(summary.get("top_author_share") or 0.0)
    duplicate_share = float(summary.get("duplicate_text_share") or 0.0)
    data_gaps = _token_data_gaps(timeline=timeline)
    stance = _stance(
        posts=posts_count,
        authors=authors_count,
        phase=phase,
        top_author_share=top_author_share,
        duplicate_share=duplicate_share,
    )
    phase_briefs = _phase_briefs(stages=stages, posts=post_items)
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_by": "deterministic",
        "project_summary": {
            "one_liner": f"${symbol} 24h social propagation brief",
            "summary_zh": (
                f"过去 24 小时，${symbol} 累计 {posts_count} 条相关推文、{authors_count} 个独立作者。"
                f"当前阶段是 {phase}，watched 账号贡献 {watched_posts} 条，top author share "
                f"{top_author_share:.0%}。这份总结只基于已入库推文、目标解析和市场锚点数据。"
            ),
            "current_state": _current_state(phase),
            "data_gaps": data_gaps,
            "evidence_event_ids": evidence_ids[:6],
        },
        "propagation": {
            "summary_zh": _propagation_summary(symbol=symbol, phases=phase_briefs),
            "phases": phase_briefs,
            "key_accounts": _key_accounts(authors=authors, posts=post_items),
        },
        "bull_bear": {
            "stance": stance,
            "bull": {
                "thesis_zh": (
                    f"多头观点：${symbol} 的有效信号来自作者扩散和 watched handle 确认，"
                    f"不是单一账号拖动。若后续出现新的独立高质量作者，并且流动性没有恶化，"
                    "有机会进入第二轮 social beta。"
                ),
                "evidence_event_ids": evidence_ids[:4],
                "triggers_zh": [
                    "2 个以上新的 watched 或高质量独立作者进入讨论",
                    "新推文提供项目、链上或流动性证据，而不是只复读价格图",
                    "市场锚点不显著弱于社交扩散节奏",
                ],
            },
            "bear": {
                "thesis_zh": (
                    f"空头观点：${symbol} 已经从发现阶段进入后段扩散，若后续内容继续转向 alert、"
                    "poll、scanner recap 和价格目标，当前热度更接近第一波尾部。"
                ),
                "evidence_event_ids": _late_evidence_ids(stages=stages, posts=post_items) or evidence_ids[-4:],
                "invalidations_zh": [
                    "连续 2 个桶没有新的独立作者或 watched handle",
                    "新增推文主要来自 scanner、复读账号或价格目标内容",
                    "流动性、价格锚点或项目资料出现新的负面缺口",
                ],
            },
        },
    }


def build_topic_agent_brief(*, query: str, items: list[dict[str, Any]]) -> dict[str, Any]:
    events = [_dict(item.get("event")) for item in items if isinstance(item, dict)]
    evidence_ids = [str(event.get("event_id")) for event in events if event.get("event_id")]
    authors = sorted({str(event.get("author_handle") or "") for event in events if event.get("author_handle")})
    count = len(events)
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_by": "deterministic",
        "project_summary": {
            "one_liner": f"关键词「{query}」24h Twitter topic brief",
            "summary_zh": (
                f"过去 24 小时，关键词「{query}」命中 {count} 条推文、{len(authors)} 个作者。"
                "该结果是 topic 语料总结，不自动推断为单一 token。"
            ),
            "current_state": "topic_result",
            "data_gaps": ["未解析为唯一 token", "缺 token 级市场和基本面上下文"],
            "evidence_event_ids": evidence_ids[:8],
        },
        "propagation": {
            "summary_zh": (
                f"关键词「{query}」当前按推文时间和作者覆盖度聚合，适合先看主题簇和代表推文，再下钻相关 token。"
            ),
            "phases": [
                {
                    "phase": "topic",
                    "window_label": "24h",
                    "tweets": count,
                    "authors": len(authors),
                    "lead_accounts": authors[:5],
                    "read_zh": "topic 结果不做 token 阶段判断，只展示过去 24h 的讨论密度和代表账号。",
                    "evidence_event_ids": evidence_ids[:8],
                }
            ],
            "key_accounts": [
                {"handle": handle, "role": "topic_author", "posts": _author_posts(events, handle)}
                for handle in authors[:8]
            ],
        },
        "bull_bear": {
            "stance": "research" if count else "unknown",
            "bull": {
                "thesis_zh": "多头观点：主题热度足够时，可以从高频共现 token 和高质量作者里寻找可下钻标的。",
                "evidence_event_ids": evidence_ids[:6],
                "triggers_zh": [
                    "出现可唯一解析的 token 候选",
                    "主题提及继续由独立作者扩散",
                    "代表推文提供产品或链上证据",
                ],
            },
            "bear": {
                "thesis_zh": "空头观点：关键词热度可能只是泛讨论，若没有可解析 token 或证据链，不能直接转成交易判断。",
                "evidence_event_ids": evidence_ids[-6:],
                "invalidations_zh": [
                    "提及集中在少数账号",
                    "内容主要是复读或无 token 指向",
                    "缺少市场数据和基本面上下文",
                ],
            },
        },
    }


def _post_items(posts: dict[str, Any] | list[dict[str, Any]]) -> list[dict[str, Any]]:
    if isinstance(posts, dict):
        return [_dict(item) for item in _list(posts.get("items"))]
    return [_dict(item) for item in posts]


def _phase_briefs(*, stages: list[dict[str, Any]], posts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    briefs: list[dict[str, Any]] = []
    for stage in stages:
        people = _dict(stage.get("people"))
        representative_ids = [str(item) for item in _list(stage.get("representative_event_ids"))]
        stage_posts = [item for item in posts if str(item.get("event_id")) in representative_ids]
        phase = str(stage.get("phase") or "unknown")
        briefs.append(
            {
                "phase": phase,
                "window_label": _window_label(stage),
                "tweets": int(people.get("posts") or len(stage_posts)),
                "authors": int(people.get("authors") or len({item.get("author_handle") for item in stage_posts})),
                "lead_accounts": _lead_accounts(stage_posts, posts=posts, event_ids=representative_ids),
                "read_zh": _phase_read(phase),
                "evidence_event_ids": representative_ids,
            }
        )
    if briefs:
        return briefs
    return [
        {
            "phase": "topic",
            "window_label": "24h",
            "tweets": len(posts),
            "authors": len({item.get("author_handle") for item in posts if item.get("author_handle")}),
            "lead_accounts": _lead_accounts(posts[:5], posts=posts, event_ids=[]),
            "read_zh": "暂无阶段切分，先按全部推文语料阅读。",
            "evidence_event_ids": _evidence_ids(posts)[:8],
        }
    ]


def _lead_accounts(
    stage_posts: list[dict[str, Any]],
    *,
    posts: list[dict[str, Any]],
    event_ids: list[str],
) -> list[str]:
    source = stage_posts
    if not source and event_ids:
        event_set = set(event_ids)
        source = [item for item in posts if str(item.get("event_id")) in event_set]
    handles = []
    for item in source:
        handle = str(item.get("handle") or item.get("author_handle") or "").strip()
        if handle and handle not in handles:
            handles.append(handle)
    return handles[:5]


def _key_accounts(*, authors: list[dict[str, Any]], posts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if authors:
        return [
            {
                "handle": str(item.get("handle") or ""),
                "role": str(item.get("role") or "author"),
                "posts": int(item.get("posts") or 0),
                "first_seen_ms": item.get("first_seen_ms"),
            }
            for item in authors[:8]
            if item.get("handle")
        ]
    counts: dict[str, int] = {}
    first_seen: dict[str, int] = {}
    for item in posts:
        handle = str(item.get("handle") or item.get("author_handle") or "").strip()
        if not handle:
            continue
        counts[handle] = counts.get(handle, 0) + 1
        received_at_ms = int(item.get("received_at_ms") or 0)
        first_seen[handle] = min(first_seen.get(handle, received_at_ms), received_at_ms)
    return [
        {"handle": handle, "role": "author", "posts": posts_count, "first_seen_ms": first_seen.get(handle)}
        for handle, posts_count in sorted(counts.items(), key=lambda pair: (-pair[1], first_seen.get(pair[0], 0)))[:8]
    ]


def _stance(*, posts: int, authors: int, phase: str, top_author_share: float, duplicate_share: float) -> str:
    if posts <= 0:
        return "unknown"
    if duplicate_share >= 0.6 or top_author_share >= 0.7:
        return "avoid"
    if authors >= 3 and posts >= 5 and phase != "seed":
        return "watch"
    return "research"


def _current_state(phase: str) -> str:
    if phase == "seed":
        return "early_discovery"
    if phase in {"ignition", "expansion"}:
        return "active_propagation"
    if phase == "chase":
        return "late_chase_risk"
    return phase


def _propagation_summary(*, symbol: str, phases: list[dict[str, Any]]) -> str:
    if not phases:
        return f"${symbol} 暂无足够传播阶段数据。"
    labels = " → ".join(str(item["phase"]) for item in phases)
    return f"${symbol} 过去 24 小时传播路径为 {labels}，应优先核对每个阶段的代表推文和 lead accounts。"


def _token_data_gaps(*, timeline: dict[str, Any]) -> list[str]:
    gaps = ["缺真实 OHLC/K 线，只能展示 message anchor price"]
    if not timeline.get("market_overlay"):
        gaps.append("缺市场 overlay")
    gaps.extend(["缺 holders", "缺合约风险和项目方资料"])
    return gaps


def _target_symbol(target: dict[str, Any], posts: list[dict[str, Any]]) -> str:
    symbol = str(target.get("symbol") or "").strip().lstrip("$")
    if symbol:
        return symbol.upper()
    for item in posts:
        post_symbol = str(item.get("symbol") or "").strip().lstrip("$")
        if post_symbol:
            return post_symbol.upper()
    return str(target.get("target_id") or "UNKNOWN").split(":")[-1].upper()


def _late_evidence_ids(*, stages: list[dict[str, Any]], posts: list[dict[str, Any]]) -> list[str]:
    ids: list[str] = []
    for stage in stages:
        if str(stage.get("phase") or "") in {"chase", "fade", "concentration"}:
            ids.extend(str(item) for item in _list(stage.get("representative_event_ids")) if item)
    return _bounded_ids(ids) or _evidence_ids(posts[-4:])


def _evidence_ids(posts: list[dict[str, Any]]) -> list[str]:
    return _bounded_ids(str(item.get("event_id")) for item in posts if item.get("event_id"))


def _bounded_ids(values: Any) -> list[str]:
    ids: list[str] = []
    for value in values:
        item = str(value or "").strip()
        if item and item not in ids:
            ids.append(item)
    return ids[:12]


def _phase_read(phase: str) -> str:
    return {
        "seed": "传播起点较薄，主要看首批作者和 CA/ticker 证据。",
        "ignition": "开始出现放大账号或叙事改写，需要观察是否带来独立作者。",
        "expansion": "作者宽度变大，重点看 watched handle 和新增证据质量。",
        "chase": "价格或复读内容增多，注意第一波尾部风险。",
        "concentration": "传播集中在少数账号，注意单点 pump 风险。",
    }.get(phase, "阶段证据不足，按代表推文阅读。")


def _window_label(stage: dict[str, Any]) -> str:
    start_ms = stage.get("start_ms")
    end_ms = stage.get("end_ms")
    if start_ms is None or end_ms is None:
        return "24h"
    return f"{int(start_ms)}-{int(end_ms)}"


def _last_phase(stages: list[dict[str, Any]]) -> str | None:
    if not stages:
        return None
    return str(stages[-1].get("phase") or "") or None


def _author_posts(events: list[dict[str, Any]], handle: str) -> int:
    return sum(1 for event in events if str(event.get("author_handle") or "") == handle)


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []
