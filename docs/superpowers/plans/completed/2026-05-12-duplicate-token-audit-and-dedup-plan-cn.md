# 同链同名 token 审计与物理去重 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 一次性脚本审计 PG 中 1,259 个 (chain, symbol) 重复组，按 holders/liq/mcap 排序 + OKX/CoinGecko 仲裁选出真品并物理 DROP ≈4,214 个假币 asset；同时规范化 `eth → ethereum` 链名。

**Architecture:** `scripts/audit_duplicate_tokens.py` 两阶段（Phase 1 链名规范化、Phase 2 同名去重），dry-run/apply 双模式，全程单事务，依赖 schema CASCADE/SET NULL。新增 `integrations/coingecko/` 作为 fallback 仲裁源；复用 `integrations/okx/dex_client.py:OkxDexClient.search_tokens` 作为主仲裁源。

**Tech Stack:** Python 3.11 / psycopg3 / httpx (sync) / pytest / testcontainers / 项目现有 `platform.db.postgres_client.connect_postgres` + `platform.config.settings.load_settings`

**Spec:** [docs/superpowers/specs/active/2026-05-12-duplicate-token-audit-and-dedup-design-cn.md](../specs/active/2026-05-12-duplicate-token-audit-and-dedup-design-cn.md)

---

## File Layout

| 路径 | 责任 |
|---|---|
| `src/parallax/integrations/coingecko/__init__.py` | 模块出口 |
| `src/parallax/integrations/coingecko/search_client.py` | CoinGecko `/api/v3/search` sync client，返回 `(symbol, chain, address)` 命中 |
| `scripts/audit_duplicate_tokens.py` | 主脚本入口 + argparse |
| `scripts/audit_dedup/__init__.py` | 子模块包 |
| `scripts/audit_dedup/candidates.py` | 候选读取（SQL）|
| `scripts/audit_dedup/winner.py` | 库内 winner 选择（纯函数）|
| `scripts/audit_dedup/external_arbiter.py` | OKX → CoinGecko fallback 链 |
| `scripts/audit_dedup/phase1_chain_normalize.py` | 链名规范化（读 + apply）|
| `scripts/audit_dedup/phase2_dedup.py` | 同名去重 orchestrator |
| `scripts/audit_dedup/report.py` | Markdown report writer |
| `tests/integrations/test_coingecko_search.py` | CoinGecko client 单测 |
| `tests/scripts/__init__.py` | 测试包 |
| `tests/scripts/test_audit_candidates.py` | 候选读取测试（PG 集成）|
| `tests/scripts/test_audit_winner.py` | 库内 winner 纯函数测试 |
| `tests/scripts/test_audit_external_arbiter.py` | 外部仲裁链测试（mock）|
| `tests/scripts/test_audit_phase1.py` | Phase 1 集成测试（PG）|
| `tests/scripts/test_audit_phase2.py` | Phase 2 集成测试（PG）|
| `tests/scripts/test_audit_report.py` | Report 生成测试 |
| `docs/generated/duplicate-token-audit.md` | dry-run 输出（运行产物）|
| `docs/generated/duplicate-token-audit-applied.md` | apply 后留痕（运行产物）|

---

## Task 1: CoinGecko search client

**Files:**
- Create: `src/parallax/integrations/coingecko/__init__.py`
- Create: `src/parallax/integrations/coingecko/search_client.py`
- Create: `tests/integrations/test_coingecko_search.py`

- [ ] **Step 1: Write failing test**

```python
# tests/integrations/test_coingecko_search.py
from __future__ import annotations

import httpx
import pytest

from parallax.integrations.coingecko.search_client import (
    CoingeckoSearchClient,
    CoingeckoSearchHit,
)


def _mock_transport(payload: dict) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v3/search"
        assert request.url.params.get("query") == "TROLL"
        return httpx.Response(200, json=payload)

    return httpx.MockTransport(handler)


def test_search_returns_platform_hit_for_known_chain() -> None:
    payload = {
        "coins": [
            {
                "id": "trollcoin",
                "symbol": "troll",
                "name": "Troll",
                "platforms": {
                    "ethereum": "0xf8ebf4849f1fa4faf0dff2106a173d3a6cb2eb3a",
                    "binance-smart-chain": "",
                },
            }
        ]
    }
    client = CoingeckoSearchClient(transport=_mock_transport(payload))

    hits = client.search(symbol="TROLL", chain="ethereum")

    assert hits == [
        CoingeckoSearchHit(
            coin_id="trollcoin",
            symbol="troll",
            chain="ethereum",
            address="0xf8ebf4849f1fa4faf0dff2106a173d3a6cb2eb3a",
        )
    ]


def test_search_returns_empty_when_chain_missing() -> None:
    payload = {
        "coins": [
            {"id": "trollcoin", "symbol": "troll", "name": "Troll", "platforms": {"polygon-pos": "0xabc"}}
        ]
    }
    client = CoingeckoSearchClient(transport=_mock_transport(payload))

    hits = client.search(symbol="TROLL", chain="ethereum")

    assert hits == []


def test_search_unknown_chain_returns_empty() -> None:
    payload = {"coins": [{"id": "x", "symbol": "x", "name": "x", "platforms": {}}]}
    client = CoingeckoSearchClient(transport=_mock_transport(payload))

    assert client.search(symbol="TROLL", chain="monad") == []


def test_search_handles_empty_response() -> None:
    client = CoingeckoSearchClient(transport=_mock_transport({"coins": []}))
    assert client.search(symbol="NOPE", chain="ethereum") == []
```

- [ ] **Step 2: Run test, verify FAIL**

```
uv run pytest tests/integrations/test_coingecko_search.py -v
```
Expected: import errors / module not found.

- [ ] **Step 3: Implement module**

```python
# src/parallax/integrations/coingecko/__init__.py
from parallax.integrations.coingecko.search_client import (
    CoingeckoSearchClient,
    CoingeckoSearchHit,
)

__all__ = ["CoingeckoSearchClient", "CoingeckoSearchHit"]
```

```python
# src/parallax/integrations/coingecko/search_client.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

CHAIN_TO_COINGECKO_PLATFORM: dict[str, str] = {
    "ethereum": "ethereum",
    "solana": "solana",
    "bsc": "binance-smart-chain",
    "base": "base",
    "tron": "tron",
}


@dataclass(frozen=True, slots=True)
class CoingeckoSearchHit:
    coin_id: str
    symbol: str
    chain: str
    address: str


class CoingeckoSearchClient:
    def __init__(
        self,
        *,
        base_url: str = "https://api.coingecko.com",
        timeout_seconds: float = 10.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._client = httpx.Client(base_url=base_url.rstrip("/"), timeout=timeout_seconds, transport=transport)

    def close(self) -> None:
        self._client.close()

    def search(self, *, symbol: str, chain: str) -> list[CoingeckoSearchHit]:
        platform = CHAIN_TO_COINGECKO_PLATFORM.get(chain)
        if platform is None:
            return []
        response = self._client.get("/api/v3/search", params={"query": symbol})
        response.raise_for_status()
        payload: dict[str, Any] = response.json() or {}
        hits: list[CoingeckoSearchHit] = []
        for coin in payload.get("coins") or []:
            address = ((coin.get("platforms") or {}).get(platform) or "").strip()
            if not address:
                continue
            hits.append(
                CoingeckoSearchHit(
                    coin_id=str(coin.get("id") or ""),
                    symbol=str(coin.get("symbol") or "").lower(),
                    chain=chain,
                    address=address.lower() if address.startswith("0x") else address,
                )
            )
        return hits
```

- [ ] **Step 4: Run tests, verify PASS**

```
uv run pytest tests/integrations/test_coingecko_search.py -v
```
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add src/parallax/integrations/coingecko/ tests/integrations/test_coingecko_search.py
git commit -m "feat: add CoinGecko search client for token audit arbitration"
```

---

## Task 2: Script scaffold + CLI args

**Files:**
- Create: `scripts/audit_duplicate_tokens.py`
- Create: `scripts/audit_dedup/__init__.py`
- Create: `tests/scripts/__init__.py`
- Create: `tests/scripts/test_audit_cli.py`

- [ ] **Step 1: Write failing test**

```python
# tests/scripts/test_audit_cli.py
from __future__ import annotations

import subprocess
import sys


def test_help_runs() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/audit_duplicate_tokens.py", "--help"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert "--dry-run" in result.stdout
    assert "--apply" in result.stdout
    assert "--report" in result.stdout
    assert "--chain" in result.stdout
    assert "--symbol" in result.stdout
    assert "--threshold-holders" in result.stdout
    assert "--threshold-liq-usd" in result.stdout
    assert "--no-external" in result.stdout
    assert "--only-phase1" in result.stdout
    assert "--only-phase2" in result.stdout


def test_requires_dry_run_or_apply() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/audit_duplicate_tokens.py"],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "--dry-run" in result.stderr or "--apply" in result.stderr
```

- [ ] **Step 2: Run test, verify FAIL**

```
uv run pytest tests/scripts/test_audit_cli.py -v
```
Expected: file-not-found error.

- [ ] **Step 3: Implement scaffold**

```python
# scripts/audit_dedup/__init__.py
"""Internal package for scripts/audit_duplicate_tokens.py."""
```

```python
# scripts/audit_duplicate_tokens.py
"""One-off audit + dedup of duplicate tokens across (chain, symbol).

See docs/superpowers/specs/active/2026-05-12-duplicate-token-audit-and-dedup-design-cn.md
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true", help="Compute audit but do not mutate DB.")
    mode.add_argument("--apply", action="store_true", help="Apply the audit; single transaction per phase.")

    parser.add_argument("--report", type=Path, default=Path("docs/generated/duplicate-token-audit.md"),
                        help="Markdown report output path.")
    parser.add_argument("--chain", type=str, default=None, help="Filter to one chain (debug).")
    parser.add_argument("--symbol", type=str, default=None, help="Filter to one symbol (debug).")
    parser.add_argument("--threshold-holders", type=int, default=200,
                        help="Minimum holders for in-db winner; below triggers external arbitration.")
    parser.add_argument("--threshold-liq-usd", type=float, default=5000.0,
                        help="Minimum liquidity_usd for in-db winner.")
    parser.add_argument("--no-external", action="store_true",
                        help="Skip OKX/CoinGecko fallback; under-threshold groups always group-drop.")
    parser.add_argument("--only-phase1", action="store_true", help="Only run chain-name normalization.")
    parser.add_argument("--only-phase2", action="store_true", help="Only run (chain, symbol) dedup.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.only_phase1 and args.only_phase2:
        parser.error("--only-phase1 and --only-phase2 are mutually exclusive")

    # Phases wired in later tasks. For now just print a banner.
    sys.stdout.write(
        f"audit_duplicate_tokens: mode={'apply' if args.apply else 'dry-run'} "
        f"chain={args.chain} symbol={args.symbol} "
        f"holders>={args.threshold_holders} liq>={args.threshold_liq_usd}\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

```python
# tests/scripts/__init__.py
```

- [ ] **Step 4: Run tests, verify PASS**

```
uv run pytest tests/scripts/test_audit_cli.py -v
```
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add scripts/audit_duplicate_tokens.py scripts/audit_dedup/__init__.py tests/scripts/__init__.py tests/scripts/test_audit_cli.py
git commit -m "feat: scaffold audit_duplicate_tokens script + CLI"
```

---

## Task 3: Candidate reader (PG)

**Files:**
- Create: `scripts/audit_dedup/candidates.py`
- Create: `tests/scripts/test_audit_candidates.py`

- [ ] **Step 1: Write failing test**

```python
# tests/scripts/test_audit_candidates.py
from __future__ import annotations

import pytest

from scripts.audit_dedup.candidates import (
    AssetCandidate,
    fetch_duplicate_groups,
)
from tests.postgres_test_utils import connect_postgres_test, prepare_postgres_database


@pytest.fixture(autouse=True)
def _fresh_db() -> None:
    prepare_postgres_database()


def _insert_asset(cur, asset_id: str, symbol: str, first_seen_ms: int) -> None:
    cur.execute(
        """
        INSERT INTO assets (asset_id, asset_type, canonical_symbol, identity_status, confidence,
                            primary_source, first_seen_at_ms, updated_at_ms)
        VALUES (%s, 'dex_token', %s, 'resolved', 0.95, 'test', %s, %s)
        """,
        (asset_id, symbol, first_seen_ms, first_seen_ms),
    )


def _insert_venue(cur, asset_id: str, venue_id: str, chain: str, address: str) -> None:
    cur.execute(
        """
        INSERT INTO asset_venues (venue_id, asset_id, venue_type, provider, chain, address,
                                  is_active, confidence, created_at_ms, updated_at_ms)
        VALUES (%s, %s, 'dex', 'okx_dex', %s, %s, true, 0.9, 0, 0)
        """,
        (venue_id, asset_id, chain, address),
    )


def _insert_snapshot(cur, asset_id: str, venue_id: str, observed_ms: int, *, holders: int | None,
                     liq: float | None, mcap: float | None) -> None:
    cur.execute(
        """
        INSERT INTO asset_market_snapshots (snapshot_id, asset_id, venue_id, provider, observed_at_ms,
                                            holders, liquidity_usd, market_cap_usd, created_at_ms)
        VALUES (%s, %s, %s, 'okx_dex', %s, %s, %s, %s, %s)
        """,
        (f"snap:{asset_id}:{observed_ms}", asset_id, venue_id, observed_ms, holders, liq, mcap, observed_ms),
    )


def test_fetch_duplicate_groups_returns_only_duplicates_per_chain() -> None:
    conn = connect_postgres_test()
    with conn.cursor() as cur:
        _insert_asset(cur, "asset:dex:solana:a", "TROLL", 100)
        _insert_asset(cur, "asset:dex:solana:b", "TROLL", 200)
        _insert_asset(cur, "asset:dex:solana:c", "UNIQUE", 300)
        _insert_venue(cur, "asset:dex:solana:a", "venue:dex:solana:a", "solana", "AAA")
        _insert_venue(cur, "asset:dex:solana:b", "venue:dex:solana:b", "solana", "BBB")
        _insert_venue(cur, "asset:dex:solana:c", "venue:dex:solana:c", "solana", "CCC")
        _insert_snapshot(cur, "asset:dex:solana:a", "venue:dex:solana:a", 1000, holders=500, liq=10000.0, mcap=1.0e6)
        _insert_snapshot(cur, "asset:dex:solana:b", "venue:dex:solana:b", 1100, holders=100, liq=2000.0, mcap=5.0e5)
        conn.commit()

    groups = fetch_duplicate_groups(conn)

    assert len(groups) == 1
    (group,) = groups
    assert group.chain == "solana"
    assert group.symbol == "TROLL"
    assert sorted(c.asset_id for c in group.candidates) == [
        "asset:dex:solana:a",
        "asset:dex:solana:b",
    ]
    by_id = {c.asset_id: c for c in group.candidates}
    assert by_id["asset:dex:solana:a"].holders == 500
    assert by_id["asset:dex:solana:b"].holders == 100


def test_fetch_duplicate_groups_picks_latest_snapshot_per_asset() -> None:
    conn = connect_postgres_test()
    with conn.cursor() as cur:
        _insert_asset(cur, "asset:dex:solana:a", "TROLL", 100)
        _insert_asset(cur, "asset:dex:solana:b", "TROLL", 200)
        _insert_venue(cur, "asset:dex:solana:a", "venue:dex:solana:a", "solana", "AAA")
        _insert_venue(cur, "asset:dex:solana:b", "venue:dex:solana:b", "solana", "BBB")
        _insert_snapshot(cur, "asset:dex:solana:a", "venue:dex:solana:a", 1000, holders=10, liq=1.0, mcap=1.0)
        _insert_snapshot(cur, "asset:dex:solana:a", "venue:dex:solana:a", 2000, holders=999, liq=999.0, mcap=999.0)
        _insert_snapshot(cur, "asset:dex:solana:b", "venue:dex:solana:b", 1500, holders=1, liq=1.0, mcap=1.0)
        conn.commit()

    groups = fetch_duplicate_groups(conn)

    by_id = {c.asset_id: c for c in groups[0].candidates}
    assert by_id["asset:dex:solana:a"].holders == 999  # latest snapshot wins
```

- [ ] **Step 2: Run test, verify FAIL**

```
uv run pytest tests/scripts/test_audit_candidates.py -v
```
Expected: import error.

- [ ] **Step 3: Implement**

```python
# scripts/audit_dedup/candidates.py
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class AssetCandidate:
    asset_id: str
    chain: str
    address: str
    first_seen_at_ms: int
    holders: int | None
    liquidity_usd: float | None
    market_cap_usd: float | None
    volume_24h_usd: float | None
    observed_at_ms: int | None


@dataclass(frozen=True, slots=True)
class DuplicateGroup:
    chain: str
    symbol: str
    candidates: tuple[AssetCandidate, ...] = field(default_factory=tuple)


def fetch_duplicate_groups(conn) -> list[DuplicateGroup]:
    """Return (chain, symbol) groups with >= 2 distinct assets.

    Joins assets ⨝ asset_venues, attaches latest asset_market_snapshots per asset.
    """
    sql = """
    WITH latest_snap AS (
        SELECT DISTINCT ON (asset_id) asset_id, observed_at_ms,
               holders, liquidity_usd, market_cap_usd, volume_24h_usd
        FROM asset_market_snapshots
        ORDER BY asset_id, observed_at_ms DESC
    ),
    base AS (
        SELECT
            av.chain,
            a.canonical_symbol AS symbol,
            a.asset_id,
            av.address,
            a.first_seen_at_ms,
            ls.holders, ls.liquidity_usd, ls.market_cap_usd, ls.volume_24h_usd,
            ls.observed_at_ms
        FROM assets a
        JOIN asset_venues av ON av.asset_id = a.asset_id
        LEFT JOIN latest_snap ls ON ls.asset_id = a.asset_id
        WHERE av.chain IS NOT NULL
          AND av.is_active = true
          AND a.canonical_symbol IS NOT NULL
    ),
    dup AS (
        SELECT chain, symbol
        FROM base
        GROUP BY chain, symbol
        HAVING COUNT(DISTINCT asset_id) > 1
    )
    SELECT b.chain, b.symbol, b.asset_id, b.address, b.first_seen_at_ms,
           b.holders, b.liquidity_usd, b.market_cap_usd, b.volume_24h_usd, b.observed_at_ms
    FROM base b
    JOIN dup ON dup.chain = b.chain AND dup.symbol = b.symbol
    ORDER BY b.chain, b.symbol, b.asset_id;
    """

    grouped: dict[tuple[str, str], list[AssetCandidate]] = {}
    with conn.cursor() as cur:
        cur.execute(sql)
        for row in cur.fetchall():
            chain, symbol, asset_id, address, first_seen, holders, liq, mcap, vol, observed = row
            key = (chain, symbol)
            grouped.setdefault(key, []).append(
                AssetCandidate(
                    asset_id=asset_id,
                    chain=chain,
                    address=address,
                    first_seen_at_ms=int(first_seen),
                    holders=int(holders) if holders is not None else None,
                    liquidity_usd=float(liq) if liq is not None else None,
                    market_cap_usd=float(mcap) if mcap is not None else None,
                    volume_24h_usd=float(vol) if vol is not None else None,
                    observed_at_ms=int(observed) if observed is not None else None,
                )
            )

    return [
        DuplicateGroup(chain=k[0], symbol=k[1], candidates=tuple(v))
        for k, v in sorted(grouped.items())
    ]
```

- [ ] **Step 4: Run tests, verify PASS**

```
uv run pytest tests/scripts/test_audit_candidates.py -v
```
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add scripts/audit_dedup/candidates.py tests/scripts/test_audit_candidates.py
git commit -m "feat: read (chain, symbol) duplicate groups with latest snapshots"
```

---

## Task 4: In-db winner selection (pure function)

**Files:**
- Create: `scripts/audit_dedup/winner.py`
- Create: `tests/scripts/test_audit_winner.py`

- [ ] **Step 1: Write failing test**

```python
# tests/scripts/test_audit_winner.py
from __future__ import annotations

from scripts.audit_dedup.candidates import AssetCandidate
from scripts.audit_dedup.winner import WinnerOutcome, pick_in_db_winner


def _c(asset_id: str, *, first_seen: int = 0, holders=None, liq=None, mcap=None) -> AssetCandidate:
    return AssetCandidate(
        asset_id=asset_id, chain="solana", address=asset_id.split(":")[-1],
        first_seen_at_ms=first_seen, holders=holders, liquidity_usd=liq, market_cap_usd=mcap,
        volume_24h_usd=None, observed_at_ms=None,
    )


def test_pick_in_db_winner_top_passes_threshold() -> None:
    candidates = (
        _c("a", holders=52267, liq=3_100_000.0, mcap=51_000_000.0, first_seen=1),
        _c("b", holders=134, liq=22_883.0, mcap=94_741_531.0, first_seen=2),
        _c("c", holders=151, liq=25_896.0, mcap=61_445_341.0, first_seen=3),
    )

    outcome = pick_in_db_winner(candidates, threshold_holders=200, threshold_liq_usd=5000.0)

    assert outcome == WinnerOutcome(
        winner_id="a",
        loser_ids=("b", "c"),
        reason="top1 holders=52267 liq=3100000.0 mcap=51000000.0 ≥ thresholds",
        needs_external=False,
    )


def test_pick_in_db_winner_top_fails_threshold_requests_external() -> None:
    candidates = (
        _c("a", holders=100, liq=10_000.0, mcap=1.0, first_seen=1),
        _c("b", holders=50, liq=50_000.0, mcap=1.0, first_seen=2),
    )

    outcome = pick_in_db_winner(candidates, threshold_holders=200, threshold_liq_usd=5000.0)

    assert outcome.winner_id is None
    assert outcome.needs_external is True
    assert set(outcome.loser_ids) == set()  # losers decided only after external step


def test_pick_in_db_winner_tiebreaks_on_first_seen_ascending() -> None:
    candidates = (
        _c("newer", holders=1000, liq=10_000.0, mcap=1.0, first_seen=200),
        _c("older", holders=1000, liq=10_000.0, mcap=1.0, first_seen=100),
    )

    outcome = pick_in_db_winner(candidates, threshold_holders=200, threshold_liq_usd=5000.0)

    assert outcome.winner_id == "older"
    assert outcome.loser_ids == ("newer",)


def test_pick_in_db_winner_handles_null_metrics_as_zero() -> None:
    candidates = (
        _c("a", holders=None, liq=None, mcap=None, first_seen=1),
        _c("b", holders=300, liq=10_000.0, mcap=1.0, first_seen=2),
    )

    outcome = pick_in_db_winner(candidates, threshold_holders=200, threshold_liq_usd=5000.0)

    assert outcome.winner_id == "b"
    assert outcome.loser_ids == ("a",)
```

- [ ] **Step 2: Run test, verify FAIL**

```
uv run pytest tests/scripts/test_audit_winner.py -v
```
Expected: import error.

- [ ] **Step 3: Implement**

```python
# scripts/audit_dedup/winner.py
from __future__ import annotations

from dataclasses import dataclass

from scripts.audit_dedup.candidates import AssetCandidate


@dataclass(frozen=True, slots=True)
class WinnerOutcome:
    winner_id: str | None
    loser_ids: tuple[str, ...]
    reason: str
    needs_external: bool


def _sort_key(c: AssetCandidate) -> tuple[int, float, float, int]:
    return (
        -(c.holders or 0),
        -(c.liquidity_usd or 0.0),
        -(c.market_cap_usd or 0.0),
        c.first_seen_at_ms,
    )


def pick_in_db_winner(
    candidates: tuple[AssetCandidate, ...],
    *,
    threshold_holders: int,
    threshold_liq_usd: float,
) -> WinnerOutcome:
    if not candidates:
        return WinnerOutcome(winner_id=None, loser_ids=(), reason="empty group", needs_external=False)

    ordered = sorted(candidates, key=_sort_key)
    top = ordered[0]
    passes = (top.holders or 0) >= threshold_holders and (top.liquidity_usd or 0.0) >= threshold_liq_usd

    if passes:
        losers = tuple(c.asset_id for c in ordered[1:])
        return WinnerOutcome(
            winner_id=top.asset_id,
            loser_ids=losers,
            reason=(
                f"top1 holders={top.holders} liq={top.liquidity_usd} mcap={top.market_cap_usd} "
                "≥ thresholds"
            ),
            needs_external=False,
        )

    return WinnerOutcome(
        winner_id=None,
        loser_ids=(),
        reason=(
            f"top1 holders={top.holders} liq={top.liquidity_usd} below threshold "
            f"(holders≥{threshold_holders}, liq≥{threshold_liq_usd}); needs external arbitration"
        ),
        needs_external=True,
    )
```

- [ ] **Step 4: Run tests, verify PASS**

```
uv run pytest tests/scripts/test_audit_winner.py -v
```
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add scripts/audit_dedup/winner.py tests/scripts/test_audit_winner.py
git commit -m "feat: in-db winner picker with holders/liq/mcap + first_seen tiebreak"
```

---

## Task 5: External arbiter (OKX → CoinGecko fallback chain)

**Files:**
- Create: `scripts/audit_dedup/external_arbiter.py`
- Create: `tests/scripts/test_audit_external_arbiter.py`

- [ ] **Step 1: Write failing test**

```python
# tests/scripts/test_audit_external_arbiter.py
from __future__ import annotations

from dataclasses import replace

from parallax.integrations.coingecko.search_client import CoingeckoSearchHit
from parallax.integrations.okx.models import OkxDexTokenCandidate
from scripts.audit_dedup.candidates import AssetCandidate
from scripts.audit_dedup.external_arbiter import (
    ExternalArbiter,
    ExternalArbiterResult,
)


class _StubOkx:
    def __init__(self, returns: list[OkxDexTokenCandidate]) -> None:
        self.returns = returns
        self.calls: list[tuple[str, tuple[str, ...]]] = []

    def search_tokens(self, *, query: str, chain_indexes):
        self.calls.append((query, tuple(chain_indexes)))
        return list(self.returns)


class _StubCg:
    def __init__(self, returns: list[CoingeckoSearchHit]) -> None:
        self.returns = returns
        self.calls: list[tuple[str, str]] = []

    def search(self, *, symbol: str, chain: str):
        self.calls.append((symbol, chain))
        return list(self.returns)


def _c(asset_id: str, address: str, *, holders=10, liq=1.0) -> AssetCandidate:
    return AssetCandidate(
        asset_id=asset_id, chain="solana", address=address,
        first_seen_at_ms=0, holders=holders, liquidity_usd=liq, market_cap_usd=None,
        volume_24h_usd=None, observed_at_ms=None,
    )


def _okx(address: str) -> OkxDexTokenCandidate:
    return OkxDexTokenCandidate(
        chain_index="501", chain="solana", address=address, symbol="TROLL", name=None,
        price_usd=None, market_cap_usd=None, liquidity_usd=None, holders=None,
        community_recognized=None, raw={},
    )


def test_okx_hit_short_circuits() -> None:
    okx = _StubOkx(returns=[_okx("AAA"), _okx("BBB")])
    cg = _StubCg(returns=[])
    arb = ExternalArbiter(okx_client=okx, coingecko_client=cg)

    candidates = (_c("asset:1", "AAA"), _c("asset:2", "ZZZ"))
    result = arb.arbitrate(chain="solana", symbol="TROLL", candidates=candidates)

    assert result == ExternalArbiterResult(
        winner_id="asset:1",
        source="okx_dex",
        external_address="AAA",
    )
    assert okx.calls == [("TROLL", ("501",))]
    assert cg.calls == []  # short-circuit


def test_okx_miss_falls_to_coingecko() -> None:
    okx = _StubOkx(returns=[_okx("NOPE")])  # not in candidates
    cg = _StubCg(returns=[CoingeckoSearchHit(coin_id="t", symbol="troll", chain="solana", address="bbb")])
    arb = ExternalArbiter(okx_client=okx, coingecko_client=cg)

    candidates = (_c("asset:1", "AAA"), _c("asset:2", "BBB"))
    result = arb.arbitrate(chain="solana", symbol="TROLL", candidates=candidates)

    assert result == ExternalArbiterResult(winner_id="asset:2", source="coingecko", external_address="BBB")
    assert cg.calls == [("TROLL", "solana")]


def test_no_hit_anywhere_returns_group_drop() -> None:
    okx = _StubOkx(returns=[])
    cg = _StubCg(returns=[])
    arb = ExternalArbiter(okx_client=okx, coingecko_client=cg)

    candidates = (_c("asset:1", "AAA"),)
    result = arb.arbitrate(chain="solana", symbol="TROLL", candidates=candidates)

    assert result == ExternalArbiterResult(winner_id=None, source="none", external_address=None)


def test_unknown_chain_skips_external_entirely() -> None:
    okx = _StubOkx(returns=[_okx("AAA")])
    cg = _StubCg(returns=[])
    arb = ExternalArbiter(okx_client=okx, coingecko_client=cg)

    candidates = (_c("asset:1", "AAA"),)
    result = arb.arbitrate(chain="monad", symbol="X", candidates=candidates)

    assert result == ExternalArbiterResult(winner_id=None, source="unsupported_chain", external_address=None)
    assert okx.calls == []
    assert cg.calls == []
```

- [ ] **Step 2: Run test, verify FAIL**

```
uv run pytest tests/scripts/test_audit_external_arbiter.py -v
```
Expected: import error.

- [ ] **Step 3: Implement**

```python
# scripts/audit_dedup/external_arbiter.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from parallax.integrations.coingecko.search_client import CoingeckoSearchHit
from parallax.integrations.okx.chains import OKX_CHAIN_TO_CHAIN_INDEX
from parallax.integrations.okx.models import OkxDexTokenCandidate
from scripts.audit_dedup.candidates import AssetCandidate


class OkxSearchProto(Protocol):
    def search_tokens(self, *, query: str, chain_indexes) -> list[OkxDexTokenCandidate]: ...


class CoingeckoSearchProto(Protocol):
    def search(self, *, symbol: str, chain: str) -> list[CoingeckoSearchHit]: ...


@dataclass(frozen=True, slots=True)
class ExternalArbiterResult:
    winner_id: str | None
    source: str  # "okx_dex" | "coingecko" | "none" | "unsupported_chain"
    external_address: str | None


def _normalize_addr(address: str | None) -> str:
    if address is None:
        return ""
    return address.lower() if address.startswith("0x") else address


class ExternalArbiter:
    def __init__(self, *, okx_client: OkxSearchProto, coingecko_client: CoingeckoSearchProto) -> None:
        self._okx = okx_client
        self._cg = coingecko_client

    def arbitrate(
        self,
        *,
        chain: str,
        symbol: str,
        candidates: tuple[AssetCandidate, ...],
    ) -> ExternalArbiterResult:
        chain_index = OKX_CHAIN_TO_CHAIN_INDEX.get(chain)
        if chain_index is None:
            return ExternalArbiterResult(winner_id=None, source="unsupported_chain", external_address=None)

        addr_to_id = {_normalize_addr(c.address): c.asset_id for c in candidates}

        for okx_hit in self._okx.search_tokens(query=symbol, chain_indexes=[chain_index]):
            normalized = _normalize_addr(okx_hit.address)
            if normalized in addr_to_id:
                return ExternalArbiterResult(
                    winner_id=addr_to_id[normalized], source="okx_dex", external_address=normalized,
                )

        for cg_hit in self._cg.search(symbol=symbol, chain=chain):
            normalized = _normalize_addr(cg_hit.address)
            if normalized in addr_to_id:
                return ExternalArbiterResult(
                    winner_id=addr_to_id[normalized], source="coingecko", external_address=normalized,
                )

        return ExternalArbiterResult(winner_id=None, source="none", external_address=None)
```

- [ ] **Step 4: Run tests, verify PASS**

```
uv run pytest tests/scripts/test_audit_external_arbiter.py -v
```
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add scripts/audit_dedup/external_arbiter.py tests/scripts/test_audit_external_arbiter.py
git commit -m "feat: external arbiter chains OKX DEX search then CoinGecko"
```

---

## Task 6: Report writer

**Files:**
- Create: `scripts/audit_dedup/report.py`
- Create: `tests/scripts/test_audit_report.py`

- [ ] **Step 1: Write failing test**

```python
# tests/scripts/test_audit_report.py
from __future__ import annotations

from scripts.audit_dedup.candidates import AssetCandidate, DuplicateGroup
from scripts.audit_dedup.report import (
    GroupDecision,
    Phase1Result,
    Phase2Summary,
    render_markdown_report,
)


def _c(asset_id: str, *, holders=None, liq=None, mcap=None) -> AssetCandidate:
    return AssetCandidate(
        asset_id=asset_id, chain="solana", address=asset_id.split(":")[-1],
        first_seen_at_ms=0, holders=holders, liquidity_usd=liq, market_cap_usd=mcap,
        volume_24h_usd=None, observed_at_ms=None,
    )


def test_report_renders_phase2_groups_with_keep_and_drop() -> None:
    group = DuplicateGroup(
        chain="solana", symbol="TROLL",
        candidates=(
            _c("asset:a", holders=52267, liq=3_100_000.0, mcap=51_000_000.0),
            _c("asset:b", holders=134, liq=22_883.0, mcap=94_741_531.0),
        ),
    )
    decision = GroupDecision(
        group=group, winner_id="asset:a", loser_ids=("asset:b",),
        source="in_db", external_address=None,
        reason="top1 holders=52267 liq=3100000.0 mcap=51000000.0 ≥ thresholds",
    )

    phase2 = Phase2Summary(
        groups_processed=1, in_db_winners=1, external_winners=0,
        external_okx_hits=0, external_cg_hits=0, no_real_token_groups=0,
        assets_kept=1, assets_dropped=1, decisions=(decision,),
    )

    markdown = render_markdown_report(
        mode="dry-run", phase1=Phase1Result.empty(), phase2=phase2,
    )

    assert "## solana / TROLL" in markdown
    assert "KEEP" in markdown and "asset:a" in markdown
    assert "DROP" in markdown and "asset:b" in markdown
    assert "Total assets DROPPED: 1" in markdown


def test_report_renders_group_drop_block() -> None:
    group = DuplicateGroup(
        chain="bsc", symbol="TROLL",
        candidates=(_c("asset:bsc:1", holders=972, liq=15_000.0),),
    )
    decision = GroupDecision(
        group=group, winner_id=None, loser_ids=("asset:bsc:1",),
        source="none", external_address=None,
        reason="top1 below threshold; OKX no hit; CoinGecko no hit",
    )
    phase2 = Phase2Summary(
        groups_processed=1, in_db_winners=0, external_winners=0,
        external_okx_hits=0, external_cg_hits=0, no_real_token_groups=1,
        assets_kept=0, assets_dropped=1, decisions=(decision,),
    )

    markdown = render_markdown_report(mode="dry-run", phase1=Phase1Result.empty(), phase2=phase2)

    assert "GROUP DROPPED" in markdown
    assert "No-real-token groups: 1" in markdown


def test_report_renders_phase1_merge_and_rename() -> None:
    phase1 = Phase1Result(
        venue_rows_normalized=149, assets_merged=2, assets_renamed=147,
        orphan_chains={"evm": 1, "evm_unknown": 2}, conflicts=(),
    )
    phase2 = Phase2Summary(
        groups_processed=0, in_db_winners=0, external_winners=0,
        external_okx_hits=0, external_cg_hits=0, no_real_token_groups=0,
        assets_kept=0, assets_dropped=0, decisions=(),
    )

    markdown = render_markdown_report(mode="apply", phase1=phase1, phase2=phase2)

    assert "Phase 1" in markdown
    assert "merged (same-address dup): 2" in markdown
    assert "renamed (no conflict): 147" in markdown
    assert "evm | 1" in markdown
    assert "evm_unknown | 2" in markdown
```

- [ ] **Step 2: Run test, verify FAIL**

```
uv run pytest tests/scripts/test_audit_report.py -v
```
Expected: import error.

- [ ] **Step 3: Implement**

```python
# scripts/audit_dedup/report.py
from __future__ import annotations

from dataclasses import dataclass, field
from io import StringIO

from scripts.audit_dedup.candidates import DuplicateGroup


@dataclass(frozen=True, slots=True)
class GroupDecision:
    group: DuplicateGroup
    winner_id: str | None
    loser_ids: tuple[str, ...]
    source: str
    external_address: str | None
    reason: str


@dataclass(frozen=True, slots=True)
class Phase1Result:
    venue_rows_normalized: int
    assets_merged: int
    assets_renamed: int
    orphan_chains: dict[str, int]
    conflicts: tuple[str, ...]

    @classmethod
    def empty(cls) -> "Phase1Result":
        return cls(0, 0, 0, {}, ())


@dataclass(frozen=True, slots=True)
class Phase2Summary:
    groups_processed: int
    in_db_winners: int
    external_winners: int
    external_okx_hits: int
    external_cg_hits: int
    no_real_token_groups: int
    assets_kept: int
    assets_dropped: int
    decisions: tuple[GroupDecision, ...]


def _fmt(value: float | int | None) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        return f"{value:,.0f}"
    return f"{value:,}"


def render_markdown_report(*, mode: str, phase1: Phase1Result, phase2: Phase2Summary) -> str:
    buf = StringIO()
    buf.write(f"# Duplicate Token Audit Report ({mode})\n\n")

    buf.write("## Phase 1 — Chain normalization\n\n")
    buf.write(f"- venue rows normalized: {phase1.venue_rows_normalized}\n")
    buf.write(f"  - merged (same-address dup): {phase1.assets_merged}\n")
    buf.write(f"  - renamed (no conflict): {phase1.assets_renamed}\n")
    if phase1.orphan_chains:
        buf.write("- orphan chains skipped (manual review needed):\n\n")
        buf.write("  | chain | venue_count |\n  |---|---:|\n")
        for chain, count in sorted(phase1.orphan_chains.items()):
            buf.write(f"  | {chain} | {count} |\n")
    if phase1.conflicts:
        buf.write("- merge conflicts:\n")
        for c in phase1.conflicts:
            buf.write(f"  - {c}\n")
    buf.write("\n")

    buf.write("## Phase 2 — (chain, symbol) dedup\n\n")
    for decision in phase2.decisions:
        group = decision.group
        if decision.winner_id is None:
            header = f"GROUP DROPPED via {decision.source}"
        else:
            header = f"winner via {decision.source}"
        buf.write(f"### {group.chain} / {group.symbol}  ({len(group.candidates)} candidates, {header})\n\n")
        if decision.source in {"okx_dex", "coingecko", "none"}:
            buf.write(f"External arbitration: source={decision.source} address={decision.external_address}\n\n")
        buf.write("| status | asset_id | address | holders | liq_usd | mcap_usd | reason |\n")
        buf.write("|---|---|---|---:|---:|---:|---|\n")
        for c in group.candidates:
            status = "KEEP" if c.asset_id == decision.winner_id else "DROP"
            reason_cell = decision.reason if status == "KEEP" else ""
            buf.write(
                f"| {status} | {c.asset_id} | {c.address} | {_fmt(c.holders)} | "
                f"{_fmt(c.liquidity_usd)} | {_fmt(c.market_cap_usd)} | {reason_cell} |\n"
            )
        buf.write("\n")

    buf.write("## Summary\n\n")
    buf.write(f"- Groups processed: {phase2.groups_processed}\n")
    buf.write(f"- In-db winners: {phase2.in_db_winners}\n")
    buf.write(
        f"- External-arbitration winners: {phase2.external_winners} "
        f"(OKX: {phase2.external_okx_hits}, CoinGecko: {phase2.external_cg_hits})\n"
    )
    buf.write(f"- No-real-token groups: {phase2.no_real_token_groups}\n")
    buf.write(f"- Total assets KEPT: {phase2.assets_kept}\n")
    buf.write(f"- Total assets DROPPED: {phase2.assets_dropped}\n")

    return buf.getvalue()
```

- [ ] **Step 4: Run tests, verify PASS**

```
uv run pytest tests/scripts/test_audit_report.py -v
```
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add scripts/audit_dedup/report.py tests/scripts/test_audit_report.py
git commit -m "feat: markdown audit report writer for phase 1 + phase 2"
```

---

## Task 7: Phase 2 orchestrator (dry-run + apply)

**Files:**
- Create: `scripts/audit_dedup/phase2_dedup.py`
- Create: `tests/scripts/test_audit_phase2.py`

- [ ] **Step 1: Write failing test**

```python
# tests/scripts/test_audit_phase2.py
from __future__ import annotations

from dataclasses import dataclass

import pytest

from scripts.audit_dedup.candidates import fetch_duplicate_groups
from scripts.audit_dedup.phase2_dedup import Phase2Config, run_phase2
from tests.postgres_test_utils import connect_postgres_test, prepare_postgres_database


@pytest.fixture(autouse=True)
def _fresh_db() -> None:
    prepare_postgres_database()


def _setup_troll(conn) -> None:
    rows = [
        ("asset:dex:solana:a", 100, "AAA", 52267, 3_100_000.0, 51_000_000.0),
        ("asset:dex:solana:b", 200, "BBB", 134, 22_883.0, 94_741_531.0),
        ("asset:dex:solana:c", 300, "CCC", 151, 25_896.0, 61_445_341.0),
    ]
    with conn.cursor() as cur:
        for asset_id, first_seen, addr, holders, liq, mcap in rows:
            cur.execute(
                """INSERT INTO assets (asset_id, asset_type, canonical_symbol, identity_status,
                   confidence, primary_source, first_seen_at_ms, updated_at_ms)
                   VALUES (%s, 'dex_token', 'TROLL', 'resolved', 0.95, 'test', %s, %s)""",
                (asset_id, first_seen, first_seen),
            )
            venue_id = f"venue:dex:solana:{addr.lower()}"
            cur.execute(
                """INSERT INTO asset_venues (venue_id, asset_id, venue_type, provider, chain, address,
                   is_active, confidence, created_at_ms, updated_at_ms)
                   VALUES (%s, %s, 'dex', 'okx_dex', 'solana', %s, true, 0.9, 0, 0)""",
                (venue_id, asset_id, addr),
            )
            cur.execute(
                """INSERT INTO asset_market_snapshots (snapshot_id, asset_id, venue_id, provider,
                   observed_at_ms, holders, liquidity_usd, market_cap_usd, created_at_ms)
                   VALUES (%s, %s, %s, 'okx_dex', %s, %s, %s, %s, %s)""",
                (f"snap:{asset_id}", asset_id, venue_id, 1000, holders, liq, mcap, 1000),
            )
    conn.commit()


class _StubArbiter:
    def arbitrate(self, *, chain, symbol, candidates):
        raise AssertionError("external arbiter should not be called in this fixture")


def test_phase2_dry_run_picks_in_db_winner_without_mutation() -> None:
    conn = connect_postgres_test()
    _setup_troll(conn)

    summary = run_phase2(
        conn,
        config=Phase2Config(threshold_holders=200, threshold_liq_usd=5000.0),
        external_arbiter=_StubArbiter(),
        apply=False,
    )

    assert summary.assets_kept == 1
    assert summary.assets_dropped == 2
    assert summary.in_db_winners == 1
    decision = summary.decisions[0]
    assert decision.winner_id == "asset:dex:solana:a"
    assert set(decision.loser_ids) == {"asset:dex:solana:b", "asset:dex:solana:c"}

    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM assets WHERE canonical_symbol='TROLL'")
        assert cur.fetchone()[0] == 3  # not mutated


def test_phase2_apply_drops_losers() -> None:
    conn = connect_postgres_test()
    _setup_troll(conn)

    run_phase2(
        conn,
        config=Phase2Config(threshold_holders=200, threshold_liq_usd=5000.0),
        external_arbiter=_StubArbiter(),
        apply=True,
    )

    with conn.cursor() as cur:
        cur.execute("SELECT asset_id FROM assets WHERE canonical_symbol='TROLL' ORDER BY asset_id")
        assert [r[0] for r in cur.fetchall()] == ["asset:dex:solana:a"]
        cur.execute("SELECT COUNT(*) FROM asset_venues WHERE asset_id IN ('asset:dex:solana:b','asset:dex:solana:c')")
        assert cur.fetchone()[0] == 0  # CASCADE
        cur.execute("SELECT COUNT(*) FROM asset_market_snapshots WHERE asset_id IN ('asset:dex:solana:b','asset:dex:solana:c')")
        assert cur.fetchone()[0] == 0  # CASCADE


@dataclass(frozen=True, slots=True)
class _ArbiterResultStub:
    winner_id: str | None
    source: str
    external_address: str | None


class _ArbiterHittingOkx:
    def arbitrate(self, *, chain, symbol, candidates):
        return _ArbiterResultStub(winner_id="asset:dex:solana:b", source="okx_dex", external_address="BBB")


def test_phase2_apply_uses_external_when_threshold_fails() -> None:
    conn = connect_postgres_test()
    rows = [
        ("asset:dex:solana:a", 100, "AAA", 50, 100.0, 1.0),
        ("asset:dex:solana:b", 200, "BBB", 30, 50.0, 1.0),
    ]
    with conn.cursor() as cur:
        for asset_id, first_seen, addr, holders, liq, mcap in rows:
            cur.execute(
                """INSERT INTO assets (asset_id, asset_type, canonical_symbol, identity_status,
                   confidence, primary_source, first_seen_at_ms, updated_at_ms)
                   VALUES (%s, 'dex_token', 'NOPE', 'resolved', 0.95, 'test', %s, %s)""",
                (asset_id, first_seen, first_seen),
            )
            venue_id = f"venue:dex:solana:{addr.lower()}"
            cur.execute(
                """INSERT INTO asset_venues (venue_id, asset_id, venue_type, provider, chain, address,
                   is_active, confidence, created_at_ms, updated_at_ms)
                   VALUES (%s, %s, 'dex', 'okx_dex', 'solana', %s, true, 0.9, 0, 0)""",
                (venue_id, asset_id, addr),
            )
            cur.execute(
                """INSERT INTO asset_market_snapshots (snapshot_id, asset_id, venue_id, provider,
                   observed_at_ms, holders, liquidity_usd, market_cap_usd, created_at_ms)
                   VALUES (%s, %s, %s, 'okx_dex', %s, %s, %s, %s, %s)""",
                (f"snap:{asset_id}", asset_id, venue_id, 1000, holders, liq, mcap, 1000),
            )
    conn.commit()

    summary = run_phase2(
        conn,
        config=Phase2Config(threshold_holders=200, threshold_liq_usd=5000.0),
        external_arbiter=_ArbiterHittingOkx(),
        apply=True,
    )

    assert summary.external_winners == 1
    assert summary.external_okx_hits == 1
    with conn.cursor() as cur:
        cur.execute("SELECT asset_id FROM assets WHERE canonical_symbol='NOPE'")
        assert [r[0] for r in cur.fetchall()] == ["asset:dex:solana:b"]


class _ArbiterNoHit:
    def arbitrate(self, *, chain, symbol, candidates):
        return _ArbiterResultStub(winner_id=None, source="none", external_address=None)


def test_phase2_apply_group_drops_when_external_no_hit() -> None:
    conn = connect_postgres_test()
    rows = [("asset:dex:bsc:a", 100, "AAA", 50, 100.0)]
    with conn.cursor() as cur:
        for asset_id, first_seen, addr, holders, liq in rows:
            cur.execute(
                """INSERT INTO assets (asset_id, asset_type, canonical_symbol, identity_status,
                   confidence, primary_source, first_seen_at_ms, updated_at_ms)
                   VALUES (%s, 'dex_token', 'TROLL', 'resolved', 0.95, 'test', %s, %s)""",
                (asset_id, first_seen, first_seen),
            )
            venue_id = f"venue:dex:bsc:{addr.lower()}"
            cur.execute(
                """INSERT INTO asset_venues (venue_id, asset_id, venue_type, provider, chain, address,
                   is_active, confidence, created_at_ms, updated_at_ms)
                   VALUES (%s, %s, 'dex', 'okx_dex', 'bsc', %s, true, 0.9, 0, 0)""",
                (venue_id, asset_id, addr),
            )
        # need a second asset to form a duplicate group
        cur.execute(
            """INSERT INTO assets (asset_id, asset_type, canonical_symbol, identity_status,
               confidence, primary_source, first_seen_at_ms, updated_at_ms)
               VALUES ('asset:dex:bsc:b', 'dex_token', 'TROLL', 'resolved', 0.95, 'test', 200, 200)"""
        )
        cur.execute(
            """INSERT INTO asset_venues (venue_id, asset_id, venue_type, provider, chain, address,
               is_active, confidence, created_at_ms, updated_at_ms)
               VALUES ('venue:dex:bsc:bbb', 'asset:dex:bsc:b', 'dex', 'okx_dex', 'bsc', 'BBB', true, 0.9, 0, 0)"""
        )
    conn.commit()

    summary = run_phase2(
        conn,
        config=Phase2Config(threshold_holders=200, threshold_liq_usd=5000.0),
        external_arbiter=_ArbiterNoHit(),
        apply=True,
    )

    assert summary.no_real_token_groups == 1
    assert summary.assets_kept == 0
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM assets WHERE canonical_symbol='TROLL'")
        assert cur.fetchone()[0] == 0
```

- [ ] **Step 2: Run test, verify FAIL**

```
uv run pytest tests/scripts/test_audit_phase2.py -v
```
Expected: import error.

- [ ] **Step 3: Implement**

```python
# scripts/audit_dedup/phase2_dedup.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from scripts.audit_dedup.candidates import AssetCandidate, fetch_duplicate_groups
from scripts.audit_dedup.report import GroupDecision, Phase2Summary
from scripts.audit_dedup.winner import pick_in_db_winner


@dataclass(frozen=True, slots=True)
class Phase2Config:
    threshold_holders: int
    threshold_liq_usd: float
    chain_filter: str | None = None
    symbol_filter: str | None = None
    use_external: bool = True


class ArbiterResultProto(Protocol):
    winner_id: str | None
    source: str
    external_address: str | None


class ArbiterProto(Protocol):
    def arbitrate(
        self, *, chain: str, symbol: str, candidates: tuple[AssetCandidate, ...]
    ) -> ArbiterResultProto: ...


class _NullArbiter:
    def arbitrate(self, *, chain, symbol, candidates):
        from scripts.audit_dedup.external_arbiter import ExternalArbiterResult
        return ExternalArbiterResult(winner_id=None, source="skipped_no_external", external_address=None)


def _delete_assets(conn, asset_ids: list[str]) -> None:
    if not asset_ids:
        return
    with conn.cursor() as cur:
        cur.execute("DELETE FROM assets WHERE asset_id = ANY(%s)", (asset_ids,))


def run_phase2(
    conn,
    *,
    config: Phase2Config,
    external_arbiter: ArbiterProto,
    apply: bool,
) -> Phase2Summary:
    arbiter = external_arbiter if config.use_external else _NullArbiter()

    groups = fetch_duplicate_groups(conn)
    if config.chain_filter:
        groups = [g for g in groups if g.chain == config.chain_filter]
    if config.symbol_filter:
        groups = [g for g in groups if g.symbol == config.symbol_filter]

    decisions: list[GroupDecision] = []
    in_db = 0
    ext_total = 0
    ext_okx = 0
    ext_cg = 0
    no_real = 0
    kept = 0
    dropped = 0

    drop_set: list[str] = []

    for group in groups:
        winner_outcome = pick_in_db_winner(
            group.candidates,
            threshold_holders=config.threshold_holders,
            threshold_liq_usd=config.threshold_liq_usd,
        )
        if not winner_outcome.needs_external and winner_outcome.winner_id is not None:
            in_db += 1
            decisions.append(
                GroupDecision(
                    group=group, winner_id=winner_outcome.winner_id,
                    loser_ids=winner_outcome.loser_ids, source="in_db",
                    external_address=None, reason=winner_outcome.reason,
                )
            )
            kept += 1
            dropped += len(winner_outcome.loser_ids)
            drop_set.extend(winner_outcome.loser_ids)
            continue

        result = arbiter.arbitrate(chain=group.chain, symbol=group.symbol, candidates=group.candidates)
        if result.winner_id is not None:
            ext_total += 1
            if result.source == "okx_dex":
                ext_okx += 1
            elif result.source == "coingecko":
                ext_cg += 1
            losers = tuple(c.asset_id for c in group.candidates if c.asset_id != result.winner_id)
            decisions.append(
                GroupDecision(
                    group=group, winner_id=result.winner_id, loser_ids=losers,
                    source=result.source, external_address=result.external_address,
                    reason=f"external arbitration via {result.source} matched {result.external_address}",
                )
            )
            kept += 1
            dropped += len(losers)
            drop_set.extend(losers)
        else:
            no_real += 1
            losers = tuple(c.asset_id for c in group.candidates)
            decisions.append(
                GroupDecision(
                    group=group, winner_id=None, loser_ids=losers,
                    source=result.source, external_address=None,
                    reason=f"top1 below threshold; external {result.source}",
                )
            )
            dropped += len(losers)
            drop_set.extend(losers)

    if apply:
        _delete_assets(conn, drop_set)
        conn.commit()

    return Phase2Summary(
        groups_processed=len(groups), in_db_winners=in_db,
        external_winners=ext_total, external_okx_hits=ext_okx, external_cg_hits=ext_cg,
        no_real_token_groups=no_real, assets_kept=kept, assets_dropped=dropped,
        decisions=tuple(decisions),
    )
```

- [ ] **Step 4: Run tests, verify PASS**

```
uv run pytest tests/scripts/test_audit_phase2.py -v
```
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add scripts/audit_dedup/phase2_dedup.py tests/scripts/test_audit_phase2.py
git commit -m "feat: phase 2 dedup orchestrator with apply/dry-run"
```

---

## Task 8: Phase 1 chain normalization

**Files:**
- Create: `scripts/audit_dedup/phase1_chain_normalize.py`
- Create: `tests/scripts/test_audit_phase1.py`

- [ ] **Step 1: Write failing test**

```python
# tests/scripts/test_audit_phase1.py
from __future__ import annotations

import pytest

from scripts.audit_dedup.phase1_chain_normalize import run_phase1
from tests.postgres_test_utils import connect_postgres_test, prepare_postgres_database


@pytest.fixture(autouse=True)
def _fresh_db() -> None:
    prepare_postgres_database()


def _insert_eth_asset(conn, asset_id: str, address: str, symbol: str, first_seen: int) -> None:
    venue_id = f"venue:dex:eth:{address.lower()}"
    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO assets (asset_id, asset_type, canonical_symbol, identity_status,
               confidence, primary_source, first_seen_at_ms, updated_at_ms)
               VALUES (%s, 'dex_token', %s, 'resolved', 0.95, 'test', %s, %s)""",
            (asset_id, symbol, first_seen, first_seen),
        )
        cur.execute(
            """INSERT INTO asset_venues (venue_id, asset_id, venue_type, provider, chain, address,
               is_active, confidence, created_at_ms, updated_at_ms)
               VALUES (%s, %s, 'dex', 'okx_dex', 'eth', %s, true, 0.9, 0, 0)""",
            (venue_id, asset_id, address),
        )
        cur.execute(
            """INSERT INTO asset_market_snapshots (snapshot_id, asset_id, venue_id, provider,
               observed_at_ms, holders, liquidity_usd, market_cap_usd, created_at_ms)
               VALUES (%s, %s, %s, 'okx_dex', 1000, 100, 100.0, 100.0, 1000)""",
            (f"snap:{asset_id}", asset_id, venue_id),
        )
    conn.commit()


def _insert_ethereum_asset(conn, asset_id: str, address: str, symbol: str, first_seen: int) -> None:
    venue_id = f"venue:dex:ethereum:{address.lower()}"
    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO assets (asset_id, asset_type, canonical_symbol, identity_status,
               confidence, primary_source, first_seen_at_ms, updated_at_ms)
               VALUES (%s, 'dex_token', %s, 'resolved', 0.95, 'test', %s, %s)""",
            (asset_id, symbol, first_seen, first_seen),
        )
        cur.execute(
            """INSERT INTO asset_venues (venue_id, asset_id, venue_type, provider, chain, address,
               is_active, confidence, created_at_ms, updated_at_ms)
               VALUES (%s, %s, 'dex', 'okx_dex', 'ethereum', %s, true, 0.9, 0, 0)""",
            (venue_id, asset_id, address),
        )
    conn.commit()


def test_phase1_renames_eth_when_no_conflict() -> None:
    conn = connect_postgres_test()
    addr = "0xdef0000000000000000000000000000000000000"
    _insert_eth_asset(conn, f"asset:dex:eth:{addr}", addr, "FOO", 100)

    result = run_phase1(conn, apply=True)

    assert result.venue_rows_normalized == 1
    assert result.assets_renamed == 1
    assert result.assets_merged == 0

    with conn.cursor() as cur:
        cur.execute("SELECT asset_id FROM assets WHERE canonical_symbol='FOO'")
        assert [r[0] for r in cur.fetchall()] == [f"asset:dex:ethereum:{addr}"]
        cur.execute("SELECT chain FROM asset_venues WHERE asset_id=%s", (f"asset:dex:ethereum:{addr}",))
        assert cur.fetchone()[0] == "ethereum"
        cur.execute("SELECT COUNT(*) FROM asset_market_snapshots WHERE asset_id=%s", (f"asset:dex:ethereum:{addr}",))
        assert cur.fetchone()[0] == 1


def test_phase1_merges_eth_into_existing_ethereum() -> None:
    conn = connect_postgres_test()
    addr = "0xabc0000000000000000000000000000000000000"
    _insert_eth_asset(conn, f"asset:dex:eth:{addr}", addr, "FOO", 100)
    _insert_ethereum_asset(conn, f"asset:dex:ethereum:{addr}", addr, "FOO", 200)

    result = run_phase1(conn, apply=True)

    assert result.assets_merged == 1
    assert result.assets_renamed == 0

    with conn.cursor() as cur:
        cur.execute("SELECT asset_id FROM assets WHERE canonical_symbol='FOO' ORDER BY asset_id")
        assert [r[0] for r in cur.fetchall()] == [f"asset:dex:ethereum:{addr}"]
        # snapshot reassigned
        cur.execute("SELECT COUNT(*) FROM asset_market_snapshots WHERE asset_id=%s", (f"asset:dex:ethereum:{addr}",))
        assert cur.fetchone()[0] == 1
        # eth asset removed
        cur.execute("SELECT COUNT(*) FROM assets WHERE asset_id=%s", (f"asset:dex:eth:{addr}",))
        assert cur.fetchone()[0] == 0


def test_phase1_lists_orphan_chains() -> None:
    conn = connect_postgres_test()
    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO assets (asset_id, asset_type, canonical_symbol, identity_status,
               confidence, primary_source, first_seen_at_ms, updated_at_ms)
               VALUES ('asset:evm:xyz', 'dex_token', 'WEIRD', 'resolved', 0.5, 'test', 0, 0)"""
        )
        cur.execute(
            """INSERT INTO asset_venues (venue_id, asset_id, venue_type, provider, chain, address,
               is_active, confidence, created_at_ms, updated_at_ms)
               VALUES ('venue:evm:xyz', 'asset:evm:xyz', 'dex', 'okx_dex', 'evm_unknown', '0xff', true, 0.5, 0, 0)"""
        )
    conn.commit()

    result = run_phase1(conn, apply=True)

    assert result.orphan_chains == {"evm_unknown": 1}
    # untouched
    with conn.cursor() as cur:
        cur.execute("SELECT chain FROM asset_venues WHERE asset_id='asset:evm:xyz'")
        assert cur.fetchone()[0] == "evm_unknown"


def test_phase1_dry_run_does_not_mutate() -> None:
    conn = connect_postgres_test()
    addr = "0xfff0000000000000000000000000000000000000"
    _insert_eth_asset(conn, f"asset:dex:eth:{addr}", addr, "BAR", 100)

    result = run_phase1(conn, apply=False)

    assert result.venue_rows_normalized == 1
    assert result.assets_renamed == 1
    with conn.cursor() as cur:
        cur.execute("SELECT chain FROM asset_venues WHERE asset_id=%s", (f"asset:dex:eth:{addr}",))
        assert cur.fetchone()[0] == "eth"  # not mutated
```

- [ ] **Step 2: Run test, verify FAIL**

```
uv run pytest tests/scripts/test_audit_phase1.py -v
```
Expected: import error.

- [ ] **Step 3: Implement**

```python
# scripts/audit_dedup/phase1_chain_normalize.py
from __future__ import annotations

from scripts.audit_dedup.report import Phase1Result

ORPHAN_CHAINS = {"evm", "evm_unknown", "tron", "monad"}


def _eth_rows(conn) -> list[tuple[str, str, str]]:
    """Return [(asset_id, venue_id, address)] for chain='eth'."""
    with conn.cursor() as cur:
        cur.execute(
            """SELECT av.asset_id, av.venue_id, av.address
               FROM asset_venues av
               WHERE av.chain = 'eth'
               ORDER BY av.asset_id"""
        )
        return [(r[0], r[1], r[2]) for r in cur.fetchall()]


def _ethereum_asset_for(conn, address_lower: str) -> str | None:
    """Return the existing ethereum-side asset_id for this address, if any."""
    with conn.cursor() as cur:
        cur.execute(
            """SELECT asset_id FROM asset_venues
               WHERE chain = 'ethereum' AND lower(address) = lower(%s)
               LIMIT 1""",
            (address_lower,),
        )
        row = cur.fetchone()
        return row[0] if row else None


def _orphan_chains(conn) -> dict[str, int]:
    with conn.cursor() as cur:
        cur.execute(
            """SELECT chain, COUNT(*) FROM asset_venues
               WHERE chain = ANY(%s)
               GROUP BY chain""",
            (list(ORPHAN_CHAINS),),
        )
        return {r[0]: int(r[1]) for r in cur.fetchall()}


_FK_TABLES_ASSET = (
    "asset_aliases",
    "asset_market_snapshots",
    "token_intent_resolutions",
    "token_intent_resolution_candidates",
    "token_radar_rows",
    "asset_signal_snapshots",
)

_FK_TABLES_VENUE = (
    ("asset_market_snapshots", "venue_id"),
    ("token_intent_resolutions", "primary_venue_id"),
    ("token_intent_resolution_candidates", "venue_id"),
    ("token_radar_rows", "primary_venue_id"),
    ("asset_signal_snapshots", "primary_venue_id"),
)


def _merge_one(conn, *, eth_asset_id: str, eth_venue_id: str, address: str) -> str:
    """Return 'merged' or 'renamed' depending on whether ethereum target existed."""
    target_asset_id = f"asset:dex:ethereum:{address.lower()}"
    target_venue_id = f"venue:dex:ethereum:{address.lower()}"
    existing = _ethereum_asset_for(conn, address)

    with conn.cursor() as cur:
        if existing is None:
            # No conflict: insert target asset + venue, then reassign + delete eth
            cur.execute(
                """INSERT INTO assets (asset_id, asset_type, canonical_symbol, display_name,
                       identity_status, confidence, primary_source, first_seen_at_ms, updated_at_ms)
                   SELECT %s, asset_type, canonical_symbol, display_name, identity_status,
                          confidence, primary_source, first_seen_at_ms, updated_at_ms
                   FROM assets WHERE asset_id = %s""",
                (target_asset_id, eth_asset_id),
            )
            cur.execute(
                """INSERT INTO asset_venues (venue_id, asset_id, venue_type, provider, exchange,
                       chain, address, inst_id, base_symbol, quote_symbol, inst_type, is_active,
                       confidence, source_payload_hash, created_at_ms, updated_at_ms)
                   SELECT %s, %s, venue_type, provider, exchange, 'ethereum', address, inst_id,
                          base_symbol, quote_symbol, inst_type, is_active, confidence,
                          source_payload_hash, created_at_ms, updated_at_ms
                   FROM asset_venues WHERE venue_id = %s""",
                (target_venue_id, target_asset_id, eth_venue_id),
            )
            outcome = "renamed"
        else:
            # Conflict: keep existing ethereum asset; pick older first_seen_at_ms / higher confidence
            cur.execute(
                """UPDATE assets
                   SET first_seen_at_ms = LEAST(first_seen_at_ms,
                       (SELECT first_seen_at_ms FROM assets WHERE asset_id = %s)),
                       confidence = GREATEST(confidence,
                       (SELECT confidence FROM assets WHERE asset_id = %s))
                   WHERE asset_id = %s""",
                (eth_asset_id, eth_asset_id, target_asset_id),
            )
            target_asset_id = existing
            outcome = "merged"

        # Reassign asset_id-keyed FKs
        for table in _FK_TABLES_ASSET:
            cur.execute(f"UPDATE {table} SET asset_id = %s WHERE asset_id = %s",
                        (target_asset_id, eth_asset_id))
        # Reassign venue_id-keyed FKs
        for table, col in _FK_TABLES_VENUE:
            cur.execute(f"UPDATE {table} SET {col} = %s WHERE {col} = %s",
                        (target_venue_id, eth_venue_id))

        # Drop eth venue + asset
        cur.execute("DELETE FROM asset_venues WHERE venue_id = %s", (eth_venue_id,))
        cur.execute("DELETE FROM assets WHERE asset_id = %s", (eth_asset_id,))

    return outcome


def run_phase1(conn, *, apply: bool) -> Phase1Result:
    eth_rows = _eth_rows(conn)
    if not apply:
        # Compute counts only; nothing mutated
        existing_count = sum(
            1 for _, _, addr in eth_rows
            if _ethereum_asset_for(conn, addr.lower()) is not None
        )
        return Phase1Result(
            venue_rows_normalized=len(eth_rows),
            assets_merged=existing_count,
            assets_renamed=len(eth_rows) - existing_count,
            orphan_chains=_orphan_chains(conn),
            conflicts=(),
        )

    merged = 0
    renamed = 0
    for asset_id, venue_id, address in eth_rows:
        outcome = _merge_one(conn, eth_asset_id=asset_id, eth_venue_id=venue_id, address=address)
        if outcome == "merged":
            merged += 1
        else:
            renamed += 1
    conn.commit()

    return Phase1Result(
        venue_rows_normalized=len(eth_rows),
        assets_merged=merged,
        assets_renamed=renamed,
        orphan_chains=_orphan_chains(conn),
        conflicts=(),
    )
```

- [ ] **Step 4: Run tests, verify PASS**

```
uv run pytest tests/scripts/test_audit_phase1.py -v
```
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add scripts/audit_dedup/phase1_chain_normalize.py tests/scripts/test_audit_phase1.py
git commit -m "feat: phase 1 chain normalization (eth → ethereum) via insert→reassign→delete"
```

---

## Task 9: Wire main script + end-to-end test

**Files:**
- Modify: `scripts/audit_duplicate_tokens.py` (replace placeholder body with full orchestration)
- Create: `tests/scripts/test_audit_main.py`

- [ ] **Step 1: Write failing end-to-end test**

```python
# tests/scripts/test_audit_main.py
from __future__ import annotations

from pathlib import Path

import pytest

import scripts.audit_duplicate_tokens as cli
from tests.postgres_test_utils import connect_postgres_test, prepare_postgres_database


@pytest.fixture(autouse=True)
def _fresh_db() -> None:
    prepare_postgres_database()


def _seed_troll(conn) -> None:
    rows = [
        ("asset:dex:solana:keep", "KKK", 52267, 3_100_000.0),
        ("asset:dex:solana:drop", "DDD", 134, 22_883.0),
    ]
    with conn.cursor() as cur:
        for asset_id, addr, holders, liq in rows:
            cur.execute(
                """INSERT INTO assets (asset_id, asset_type, canonical_symbol, identity_status,
                   confidence, primary_source, first_seen_at_ms, updated_at_ms)
                   VALUES (%s, 'dex_token', 'TROLL', 'resolved', 0.95, 'test', 0, 0)""",
                (asset_id,),
            )
            venue_id = f"venue:dex:solana:{addr.lower()}"
            cur.execute(
                """INSERT INTO asset_venues (venue_id, asset_id, venue_type, provider, chain, address,
                   is_active, confidence, created_at_ms, updated_at_ms)
                   VALUES (%s, %s, 'dex', 'okx_dex', 'solana', %s, true, 0.9, 0, 0)""",
                (venue_id, asset_id, addr),
            )
            cur.execute(
                """INSERT INTO asset_market_snapshots (snapshot_id, asset_id, venue_id, provider,
                   observed_at_ms, holders, liquidity_usd, market_cap_usd, created_at_ms)
                   VALUES (%s, %s, %s, 'okx_dex', 1000, %s, %s, 1.0, 1000)""",
                (f"snap:{asset_id}", asset_id, venue_id, holders, liq),
            )
    conn.commit()


def test_main_dry_run_writes_report_without_mutation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    conn = connect_postgres_test()
    _seed_troll(conn)

    monkeypatch.setattr(cli, "_open_connection", lambda: conn)
    monkeypatch.setattr(cli, "_build_external_arbiter", lambda *args, **kwargs: _FailingArbiter())

    report_path = tmp_path / "report.md"
    rc = cli.main([
        "--dry-run", "--report", str(report_path),
        "--threshold-holders", "200", "--threshold-liq-usd", "5000",
        "--no-external",
    ])

    assert rc == 0
    text = report_path.read_text(encoding="utf-8")
    assert "solana / TROLL" in text
    assert "KEEP" in text and "asset:dex:solana:keep" in text

    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM assets WHERE canonical_symbol='TROLL'")
        assert cur.fetchone()[0] == 2  # untouched


def test_main_apply_drops_losers(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    conn = connect_postgres_test()
    _seed_troll(conn)

    monkeypatch.setattr(cli, "_open_connection", lambda: conn)

    rc = cli.main([
        "--apply", "--report", str(tmp_path / "report.md"),
        "--no-external",
    ])

    assert rc == 0
    with conn.cursor() as cur:
        cur.execute("SELECT asset_id FROM assets WHERE canonical_symbol='TROLL'")
        assert [r[0] for r in cur.fetchall()] == ["asset:dex:solana:keep"]


class _FailingArbiter:
    def arbitrate(self, *, chain, symbol, candidates):
        raise AssertionError("should not be reached with --no-external")
```

- [ ] **Step 2: Run test, verify FAIL**

```
uv run pytest tests/scripts/test_audit_main.py -v
```
Expected: AttributeError (`_open_connection` / `_build_external_arbiter` not in cli).

- [ ] **Step 3: Replace main() body**

```python
# scripts/audit_duplicate_tokens.py
"""One-off audit + dedup of duplicate tokens across (chain, symbol).

See docs/superpowers/specs/active/2026-05-12-duplicate-token-audit-and-dedup-design-cn.md
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from parallax.integrations.coingecko.search_client import CoingeckoSearchClient
from parallax.integrations.okx.dex_client import OkxDexClient
from parallax.platform.config.settings import load_settings
from parallax.platform.db.postgres_client import (
    connect_postgres,
    local_docker_host_dsn,
    with_password_from_file,
)
from scripts.audit_dedup.external_arbiter import ExternalArbiter
from scripts.audit_dedup.phase1_chain_normalize import run_phase1
from scripts.audit_dedup.phase2_dedup import Phase2Config, run_phase2
from scripts.audit_dedup.report import Phase1Result, Phase2Summary, render_markdown_report


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--apply", action="store_true")

    parser.add_argument("--report", type=Path, default=Path("docs/generated/duplicate-token-audit.md"))
    parser.add_argument("--chain", type=str, default=None)
    parser.add_argument("--symbol", type=str, default=None)
    parser.add_argument("--threshold-holders", type=int, default=200)
    parser.add_argument("--threshold-liq-usd", type=float, default=5000.0)
    parser.add_argument("--no-external", action="store_true")
    parser.add_argument("--only-phase1", action="store_true")
    parser.add_argument("--only-phase2", action="store_true")
    return parser


def _open_connection():
    settings = load_settings(require_ws_token=False)
    dsn = local_docker_host_dsn(with_password_from_file(settings.postgres_dsn, settings.postgres_password_file))
    return connect_postgres(dsn)


def _build_external_arbiter(*, settings=None) -> ExternalArbiter:
    settings = settings or load_settings(require_ws_token=False)
    okx = OkxDexClient(
        base_url=settings.okx_dex_base_url if hasattr(settings, "okx_dex_base_url") else "https://web3.okx.com",
    )
    cg = CoingeckoSearchClient()
    return ExternalArbiter(okx_client=okx, coingecko_client=cg)


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.only_phase1 and args.only_phase2:
        parser.error("--only-phase1 and --only-phase2 are mutually exclusive")

    apply = bool(args.apply)
    conn = _open_connection()

    phase1: Phase1Result = Phase1Result.empty()
    if not args.only_phase2:
        phase1 = run_phase1(conn, apply=apply)

    if args.no_external:
        from scripts.audit_dedup.phase2_dedup import _NullArbiter  # type: ignore[attr-defined]
        arbiter = _NullArbiter()
    else:
        arbiter = _build_external_arbiter()

    phase2: Phase2Summary = Phase2Summary(0, 0, 0, 0, 0, 0, 0, 0, ())
    if not args.only_phase1:
        phase2 = run_phase2(
            conn,
            config=Phase2Config(
                threshold_holders=args.threshold_holders,
                threshold_liq_usd=args.threshold_liq_usd,
                chain_filter=args.chain,
                symbol_filter=args.symbol,
                use_external=not args.no_external,
            ),
            external_arbiter=arbiter,
            apply=apply,
        )

    markdown = render_markdown_report(
        mode="apply" if apply else "dry-run", phase1=phase1, phase2=phase2,
    )
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(markdown, encoding="utf-8")
    sys.stdout.write(f"Audit report → {args.report}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run tests, verify PASS**

```
uv run pytest tests/scripts/test_audit_main.py -v
uv run pytest tests/scripts/ -v
```
Expected: all green.

- [ ] **Step 5: Commit**

```bash
git add scripts/audit_duplicate_tokens.py tests/scripts/test_audit_main.py
git commit -m "feat: wire audit_duplicate_tokens main entrypoint end-to-end"
```

---

## Task 10: Real-DB dry-run smoke + spot-check report

**Files:** none new; produces `docs/generated/duplicate-token-audit.md`

- [ ] **Step 1: Run full unit + integration suite**

```bash
uv run pytest tests/scripts/ tests/integrations/test_coingecko_search.py -v
```
Expected: all green.

- [ ] **Step 2: Dry-run against real PG (production schema only, in dev compose)**

```bash
uv run python scripts/audit_duplicate_tokens.py \
    --dry-run \
    --report docs/generated/duplicate-token-audit.md
```
Expected stdout: `Audit report → docs/generated/duplicate-token-audit.md`. No mutation.

- [ ] **Step 3: Spot-check three groups in the report**

Open `docs/generated/duplicate-token-audit.md`. Verify:
- `## solana / TROLL` — KEEP must be `asset:dex:solana:5uuh9rtdispq6hks6bp4ndu9pnjpxrxuiw6shbtbhgh2` (holders 52,267)
- `## ethereum / TROLL` — KEEP must be `asset:dex:ethereum:0xf8ebf4849f1fa4faf0dff2106a173d3a6cb2eb3a` (holders 15,824)
- `## bsc / TROLL` — should be `GROUP DROPPED via none` (top1 only 972 holders, OKX/CG no hit)
- Summary line `Total assets DROPPED: D` should be ≈ 4,214 ± a small delta (data drift since spec date)

- [ ] **Step 4: Confirm DB unchanged**

```bash
docker exec parallax-postgres-1 psql -U parallax_app -d parallax -c "SELECT COUNT(*) FROM assets;"
```
Expected: still ≈15,004 (no drift from baseline).

- [ ] **Step 5: Commit the dry-run report**

```bash
git add docs/generated/duplicate-token-audit.md
git commit -m "chore: dry-run duplicate-token audit report (pre-apply)"
```

---

## Task 11: Apply against real DB (after human review of dry-run report)

**Files:** none new; produces `docs/generated/duplicate-token-audit-applied.md`

- [ ] **Step 1: Confirm dry-run report was reviewed**

This step is a human gate, not automation. Do not proceed unless the user has reviewed `docs/generated/duplicate-token-audit.md` and explicitly approved.

- [ ] **Step 2: Apply**

```bash
uv run python scripts/audit_duplicate_tokens.py \
    --apply \
    --report docs/generated/duplicate-token-audit-applied.md
```
Expected stdout: `Audit report → docs/generated/duplicate-token-audit-applied.md`.

- [ ] **Step 3: Post-apply invariants**

```bash
docker exec parallax-postgres-1 psql -U parallax_app -d parallax -c "
  SELECT COUNT(*) AS assets_after FROM assets;
  SELECT chain, COUNT(*) FROM asset_venues GROUP BY chain ORDER BY chain;
  WITH dup AS (
    SELECT av.chain, a.canonical_symbol
    FROM assets a JOIN asset_venues av ON av.asset_id = a.asset_id
    WHERE av.chain IS NOT NULL AND a.canonical_symbol IS NOT NULL
    GROUP BY av.chain, a.canonical_symbol
    HAVING COUNT(DISTINCT a.asset_id) > 1
  )
  SELECT COUNT(*) AS remaining_dups FROM dup;
"
```

Expected:
- `assets_after` ≈ 10,790
- `chain` values: no `eth` row anymore (only `ethereum`, `solana`, `bsc`, `base`, plus orphans `evm`/`evm_unknown`/`tron`/`monad` unchanged)
- `remaining_dups` = 0

- [ ] **Step 4: Commit applied report**

```bash
git add docs/generated/duplicate-token-audit-applied.md
git commit -m "chore: apply duplicate-token audit (drop ~4214 assets, normalize eth→ethereum)"
```

---

## Self-Review Notes (post-write)

- **Spec coverage**: Phase 1 (Task 8), Phase 2 (Task 7), external arbiter (Task 5), report format (Task 6), CLI surface (Tasks 2 + 9), real-DB smoke + apply (Tasks 10 + 11). External-arbiter testing is mocked in Task 5 since real HTTP is non-deterministic; that's spec-aligned.
- **Tiebreaker** (`first_seen_at_ms ASC`) covered in Task 4 test `test_pick_in_db_winner_tiebreaks_on_first_seen_ascending`.
- **Schema CASCADE assumption** verified during spec writing (`ON DELETE CASCADE` for venues/aliases/snapshots, `ON DELETE SET NULL` for resolutions/radar/signal). No re-verification step needed at execution time.
- **No backup**: per user instruction; only single-transaction atomicity and dry-run review gate. Codified in Task 11 Step 1.
- **No placeholders**: every code block has concrete content; reasons/SQL/imports all spelled out.
