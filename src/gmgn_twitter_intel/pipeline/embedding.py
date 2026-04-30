from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass
from typing import Protocol

import httpx

TOKEN_RE = re.compile(r"[A-Za-z0-9_$#@]+")


class EmbeddingBackend(Protocol):
    dimension: int

    def embed(self, text: str) -> list[float]: ...


@dataclass(frozen=True, slots=True)
class HashEmbeddingBackend:
    dimension: int = 1024

    def embed(self, text: str) -> list[float]:
        vector = [0.0] * self.dimension
        for token in TOKEN_RE.findall(text.lower()):
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimension
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[index] += sign
        norm = math.sqrt(sum(value * value for value in vector))
        if norm <= 0:
            return vector
        return [value / norm for value in vector]


@dataclass(frozen=True, slots=True)
class HttpEmbeddingBackend:
    endpoint: str
    model: str
    dimension: int
    api_key: str | None = None
    timeout: float = 15.0

    def embed(self, text: str) -> list[float]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        response = httpx.post(
            self.endpoint,
            json={"model": self.model, "input": text},
            headers=headers,
            timeout=self.timeout,
        )
        response.raise_for_status()
        payload = response.json()
        vector = _extract_embedding(payload)
        if len(vector) != self.dimension:
            raise ValueError(f"embedding dimension mismatch: got {len(vector)} expected {self.dimension}")
        return vector


def embed_pending_tweets(repo, backend: EmbeddingBackend, *, limit: int = 100) -> int:
    if int(backend.dimension) != int(repo.client.embedding_dim):
        raise ValueError(
            "embedding backend dimension "
            f"{backend.dimension} does not match store dimension {repo.client.embedding_dim}"
        )
    processed = 0
    for row in repo.pending_embedding_rows(limit=limit):
        text = row.get("embedding_text") or row.get("text_clean") or row.get("text")
        if not isinstance(text, str) or not text.strip():
            repo.update_event_embedding(event_id=str(row["event_id"]), embedding=row["embedding"], status="skipped")
            continue
        repo.update_event_embedding(
            event_id=str(row["event_id"]),
            embedding=backend.embed(text),
            status="embedded",
        )
        processed += 1
    return processed


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    return sum(a * b for a, b in zip(left, right, strict=False))


def _extract_embedding(payload: dict) -> list[float]:
    data = payload.get("data")
    if isinstance(data, list) and data:
        embedding = data[0].get("embedding") if isinstance(data[0], dict) else None
        if isinstance(embedding, list):
            return [float(value) for value in embedding]
    embedding = payload.get("embedding")
    if isinstance(embedding, list):
        return [float(value) for value in embedding]
    raise ValueError("embedding response does not contain an embedding vector")
