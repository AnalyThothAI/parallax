from __future__ import annotations

from .lancedb_client import LanceDbClient
from .lancedb_schema import ensure_required_tables


def bootstrap_lancedb(client: LanceDbClient) -> None:
    ensure_required_tables(client, embedding_dim=client.embedding_dim)
