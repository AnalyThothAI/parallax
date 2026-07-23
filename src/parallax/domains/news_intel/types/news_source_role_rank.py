from __future__ import annotations

from parallax.domains.news_intel.types.source_classification import SOURCE_ROLES

SOURCE_ROLE_RANK: dict[str, int] = {
    "official_exchange": 80,
    "official_regulator": 80,
    "official_protocol": 80,
    "official_issuer": 80,
    "developer_signal": 70,
    "specialist_media": 60,
    "observed_source": 50,
    "community": 40,
    "social": 30,
    "aggregator": 20,
}

_UNKNOWN_SOURCE_ROLE_RANK = 10

if set(SOURCE_ROLE_RANK) != set(SOURCE_ROLES):
    raise RuntimeError("SOURCE_ROLE_RANK must cover SOURCE_ROLES exactly")


def source_role_rank(source_role: object) -> int:
    normalized = str(source_role or "").strip().lower()
    if not normalized:
        return 0
    return SOURCE_ROLE_RANK.get(normalized, _UNKNOWN_SOURCE_ROLE_RANK)


def source_role_rank_case_sql(column_sql: str) -> str:
    clauses = "\n".join(
        f"                           WHEN '{role}' THEN {rank}" for role, rank in SOURCE_ROLE_RANK.items()
    )
    return (
        f"CASE COALESCE({column_sql}, '')\n"
        f"{clauses}\n"
        "                           WHEN '' THEN 0\n"
        f"                           ELSE {_UNKNOWN_SOURCE_ROLE_RANK}\n"
        "                         END"
    )


__all__ = ["SOURCE_ROLE_RANK", "source_role_rank", "source_role_rank_case_sql"]
