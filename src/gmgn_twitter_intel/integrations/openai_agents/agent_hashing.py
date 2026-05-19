from __future__ import annotations

import hashlib
import json
from typing import Any


def json_sha256(value: Any) -> str:
    data = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    return "sha256:" + hashlib.sha256(data).hexdigest()


def text_sha256(value: str) -> str:
    return "sha256:" + hashlib.sha256(str(value or "").encode("utf-8")).hexdigest()


def trace_id_for(value: Any, *, length: int = 32) -> str:
    digest = hashlib.sha256(str(value or "").encode("utf-8")).hexdigest()
    return "trace_" + digest[: max(8, int(length))]


def artifact_hash_for(
    *,
    model: str,
    prompt_version: str,
    schema_version: str,
    runtime_version: str,
    output_schema_hash: str,
) -> str:
    return json_sha256(
        {
            "model": model,
            "prompt_version": prompt_version,
            "schema_version": schema_version,
            "runtime_version": runtime_version,
            "output_schema_hash": output_schema_hash,
        }
    )


__all__ = ["artifact_hash_for", "json_sha256", "text_sha256", "trace_id_for"]
