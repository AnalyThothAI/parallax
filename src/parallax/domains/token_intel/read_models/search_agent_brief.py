from __future__ import annotations

from typing import Any

SCHEMA_VERSION = "search_agent_brief_v1"


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


def _author_posts(events: list[dict[str, Any]], handle: str) -> int:
    return sum(1 for event in events if str(event.get("author_handle") or "") == handle)


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}
