from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class AgentKnowledgeRef:
    ref_id: str
    title: str
    description: str
    path: Path


class AgentKnowledgeCatalog:
    def __init__(self, refs: tuple[AgentKnowledgeRef, ...]) -> None:
        self._refs = {ref.ref_id: ref for ref in refs}
        if len(self._refs) != len(refs):
            raise ValueError("duplicate agent knowledge ref")

    def index(self) -> dict[str, dict[str, Any]]:
        return {
            ref_id: {
                "ref_id": ref.ref_id,
                "title": ref.title,
                "description": ref.description,
            }
            for ref_id, ref in sorted(self._refs.items())
        }

    def load(self, ref_id: str) -> str:
        ref = self._ref(ref_id)
        return _read_text(str(ref.path))

    def render(self, ref_ids: tuple[str, ...]) -> str:
        sections = []
        for ref_id in ref_ids:
            ref = self._ref(ref_id)
            sections.append(f"## Loaded Knowledge: {ref.title}\n\n{_read_text(str(ref.path)).strip()}")
        return "\n\n".join(sections).strip()

    def _ref(self, ref_id: str) -> AgentKnowledgeRef:
        try:
            return self._refs[str(ref_id)]
        except KeyError as exc:
            raise ValueError(f"unknown agent knowledge ref: {ref_id}") from exc


def render_agent_instructions(
    base_instructions: str,
    *,
    knowledge_refs: tuple[str, ...] = (),
    catalog: AgentKnowledgeCatalog | None = None,
) -> str:
    base = str(base_instructions or "").strip()
    refs = tuple(str(ref).strip() for ref in knowledge_refs if str(ref).strip())
    if not refs:
        return base
    loaded = (catalog or agent_knowledge_catalog()).render(refs)
    if not loaded:
        return base
    return f"{base}\n\n{loaded}"


@lru_cache(maxsize=1)
def agent_knowledge_catalog() -> AgentKnowledgeCatalog:
    knowledge_dir = Path(__file__).resolve().parent.parent / "agent_knowledge"
    return AgentKnowledgeCatalog(
        (
            AgentKnowledgeRef(
                ref_id="market_research_harness",
                title="Market Research Harness",
                description="Parallax product-truth, read-only context, and no-action guardrails for LLM stages.",
                path=knowledge_dir / "market_research_harness.md",
            ),
        )
    )


@lru_cache(maxsize=16)
def _read_text(path: str) -> str:
    resolved = Path(path)
    if not resolved.exists():
        raise RuntimeError(f"agent knowledge file not found: {resolved}")
    return resolved.read_text(encoding="utf-8")


__all__ = [
    "AgentKnowledgeCatalog",
    "AgentKnowledgeRef",
    "agent_knowledge_catalog",
    "render_agent_instructions",
]
