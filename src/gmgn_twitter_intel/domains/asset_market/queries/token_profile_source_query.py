from __future__ import annotations

from typing import Any

from gmgn_twitter_intel.domains.asset_market.identity_evidence_policy import (
    EVIDENCE_GMGN_PAYLOAD_EXACT,
    EVIDENCE_OKX_DEX_EXACT_ADDRESS,
)
from gmgn_twitter_intel.domains.asset_market.profile_source_selection import (
    select_gmgn_stream_source,
    select_okx_dex_source,
)


class TokenProfileSourceQuery:
    def __init__(self, conn: Any) -> None:
        self.conn = conn

    def gmgn_openapi_profiles(self, asset_ids: list[str]) -> dict[str, dict[str, Any]]:
        requested = _dedupe(asset_ids)
        if not requested:
            return {}
        rows = self.conn.execute(
            """
            SELECT *
            FROM asset_profiles
            WHERE provider = 'gmgn_dex_profile'
              AND status = 'ready'
              AND asset_id = ANY(%s)
            """,
            (requested,),
        ).fetchall()
        return {str(row["asset_id"]): dict(row) for row in rows}

    def binance_web3_profiles(self, asset_ids: list[str]) -> dict[str, dict[str, Any]]:
        requested = _dedupe(asset_ids)
        if not requested:
            return {}
        rows = self.conn.execute(
            """
            SELECT *
            FROM asset_profiles
            WHERE provider = 'binance_web3_profile'
              AND status = 'ready'
              AND asset_id = ANY(%s)
            """,
            (requested,),
        ).fetchall()
        return {str(row["asset_id"]): dict(row) for row in rows}

    def gmgn_stream_profiles(self, asset_ids: list[str]) -> dict[str, dict[str, Any]]:
        rows_by_asset = self._identity_evidence_rows(
            asset_ids=asset_ids,
            provider="gmgn",
            evidence_kind=EVIDENCE_GMGN_PAYLOAD_EXACT,
        )
        return {
            asset_id: selected
            for asset_id, rows in rows_by_asset.items()
            if (selected := select_gmgn_stream_source(rows)) is not None
        }

    def okx_dex_profiles(self, asset_ids: list[str]) -> dict[str, dict[str, Any]]:
        rows_by_asset = self._identity_evidence_rows(
            asset_ids=asset_ids,
            provider="okx",
            evidence_kind=EVIDENCE_OKX_DEX_EXACT_ADDRESS,
        )
        return {
            asset_id: selected
            for asset_id, rows in rows_by_asset.items()
            if (selected := select_okx_dex_source(rows)) is not None
        }

    def cex_token_profiles(self, cex_token_ids: list[str]) -> dict[str, dict[str, Any]]:
        requested = _dedupe(cex_token_ids)
        if not requested:
            return {}
        rows = self.conn.execute(
            """
            SELECT
              cex_token_profiles.*,
              cex_tokens.base_symbol
            FROM cex_token_profiles
            JOIN cex_tokens
              ON cex_tokens.cex_token_id = cex_token_profiles.cex_token_id
            WHERE cex_token_profiles.provider = 'binance_cex_profile'
              AND cex_token_profiles.status = 'ready'
              AND cex_tokens.cex_token_id = ANY(%s)
              AND cex_tokens.status IN ('candidate', 'canonical')
            """,
            (requested,),
        ).fetchall()
        return {str(row["cex_token_id"]): dict(row) for row in rows}

    def _identity_evidence_rows(
        self,
        *,
        asset_ids: list[str],
        provider: str,
        evidence_kind: str,
    ) -> dict[str, list[dict[str, Any]]]:
        requested = _dedupe(asset_ids)
        if not requested:
            return {}
        rows = self.conn.execute(
            """
            SELECT *
            FROM asset_identity_evidence
            WHERE provider = %s
              AND evidence_kind = %s
              AND asset_id = ANY(%s)
            ORDER BY asset_id ASC, observed_at_ms DESC, evidence_id DESC
            """,
            (provider, evidence_kind, requested),
        ).fetchall()
        grouped: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            item = dict(row)
            grouped.setdefault(str(item.get("asset_id")), []).append(item)
        return grouped


def _dedupe(values: list[str]) -> list[str]:
    return [value for value in dict.fromkeys(str(item).strip() for item in values) if value]
