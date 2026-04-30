from __future__ import annotations

import json
import time
from typing import Any

from .lancedb_client import LanceDbClient


class TokenRegistryRepository:
    def __init__(self, client: LanceDbClient):
        self.client = client

    def upsert_token(self, entry) -> None:
        now_ms = int(time.time() * 1000)
        self.client.upsert(
            "token_registry",
            key_fields=("token_key",),
            row={
                "token_key": f"{entry.chain}:{entry.ca}",
                "chain": entry.chain,
                "ca": entry.ca,
                "symbol": entry.symbol.upper() if entry.symbol else None,
                "name": entry.name,
                "aliases_json": json.dumps(entry.aliases, ensure_ascii=False, sort_keys=True),
                "source": entry.source,
                "created_at_ms": now_ms,
                "updated_at_ms": now_ms,
            },
        )

    def find_by_symbol(self, symbol: str) -> list[dict[str, Any]]:
        normalized = symbol.strip().lstrip("$").upper()
        return self.client.query_where("token_registry", where=f"symbol = '{_sql_literal(normalized)}'")

    def close(self) -> None:
        self.client.close()


def _sql_literal(value: str) -> str:
    return value.replace("'", "''")
