from __future__ import annotations

from typing import Any

from .lancedb_client import LanceDbClient


class LlmRepository:
    def __init__(self, client: LanceDbClient):
        self.client = client

    def upsert_run(self, row: dict[str, Any]) -> None:
        self.client.upsert("llm_runs", key_fields=("llm_run_id",), row=row)

    def insert_claim(self, row: dict[str, Any]) -> bool:
        return self.client.insert_if_missing("llm_claims", row=row, key_fields=("claim_id",))

    def insert_entity(self, row: dict[str, Any]) -> bool:
        return self.client.insert_if_missing("llm_entities", row=row, key_fields=("entity_id",))

    def insert_relation(self, row: dict[str, Any]) -> bool:
        return self.client.insert_if_missing("llm_relations", row=row, key_fields=("relation_id",))

    def count_claims(self, llm_run_id: str) -> int:
        return self.client.count_where("llm_claims", where=f"llm_run_id = '{_sql_literal(llm_run_id)}'")


def _sql_literal(value: str) -> str:
    return value.replace("'", "''")
