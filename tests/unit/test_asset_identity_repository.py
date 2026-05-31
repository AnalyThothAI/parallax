from __future__ import annotations

from parallax.domains.asset_market.identity_evidence_policy import (
    EVIDENCE_OKX_DEX_EXACT_ADDRESS,
    EVIDENCE_TWEET_CONTRACT_MENTION,
)
from parallax.domains.asset_market.repositories.identity_evidence_repository import (
    IdentityEvidenceRepository,
)


def test_recompute_current_identity_writes_policy_result_without_source_precedence():
    conn = FakeIdentityConnection(
        evidence_rows=[
            {
                "evidence_id": "tweet-sato",
                "asset_id": "asset:eip155:1:erc20:0x999b49c0d1612e619a4a4f6280733184da025108",
                "evidence_kind": EVIDENCE_TWEET_CONTRACT_MENTION,
                "provider": "twitter",
                "lookup_mode": "tweet_mention",
                "symbol": "SATO",
                "name": None,
                "decimals": None,
                "observed_at_ms": 100,
            },
            {
                "evidence_id": "okx-exact-slop",
                "asset_id": "asset:eip155:1:erc20:0x999b49c0d1612e619a4a4f6280733184da025108",
                "evidence_kind": EVIDENCE_OKX_DEX_EXACT_ADDRESS,
                "provider": "okx",
                "lookup_mode": "exact_address",
                "symbol": "SLOP",
                "name": "SLOP",
                "decimals": None,
                "observed_at_ms": 200,
            },
        ]
    )
    repo = IdentityEvidenceRepository(conn)

    current = repo.recompute_current_identity(
        "asset:eip155:1:erc20:0x999b49c0d1612e619a4a4f6280733184da025108",
        now_ms=1_000,
        commit=False,
    )

    assert current["canonical_symbol"] == "SLOP"
    assert current["identity_confidence"] == "provider_exact"
    assert conn.current_rows == [
        {
            "asset_id": "asset:eip155:1:erc20:0x999b49c0d1612e619a4a4f6280733184da025108",
            "canonical_symbol": "SLOP",
            "canonical_name": "SLOP",
            "identity_confidence": "provider_exact",
            "selected_evidence_id": "okx-exact-slop",
            "reason_codes": ["SELECTED_PROVIDER_EXACT", "CONFLICTING_IDENTITY_EVIDENCE", "MENTION_NOT_CANONICAL"],
            "conflict_count": 1,
        }
    ]
    assert conn.commits == 0


class FakeCursor:
    def __init__(self, rows):
        self.rows = rows

    def fetchall(self):
        return self.rows

    def fetchone(self):
        return self.rows[0] if self.rows else None


class FakeIdentityConnection:
    def __init__(self, *, evidence_rows):
        self.evidence_rows = evidence_rows
        self.current_rows = []
        self.commits = 0

    def execute(self, sql, params=None):
        text = " ".join(str(sql).split())
        if "FROM asset_identity_evidence" in text:
            return FakeCursor(self.evidence_rows)
        if "INSERT INTO asset_identity_current" in text:
            self.current_rows.append(
                {
                    "asset_id": params[0],
                    "canonical_symbol": params[1],
                    "canonical_name": params[2],
                    "identity_confidence": params[4],
                    "selected_evidence_id": params[5],
                    "reason_codes": list(params[6].obj),
                    "conflict_count": params[7],
                }
            )
            return FakeCursor([])
        raise AssertionError(f"unexpected SQL: {text}")

    def commit(self):
        self.commits += 1
