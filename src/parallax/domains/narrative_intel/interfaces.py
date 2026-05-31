from __future__ import annotations

from typing import Any, Protocol

from parallax.domains.narrative_intel._constants import NARRATIVE_SCHEMA_VERSION

__all__ = ("NARRATIVE_SCHEMA_VERSION", "NarrativeDigestReader")


class NarrativeDigestReader(Protocol):
    def current_narrative_snapshots_for_targets(
        self,
        targets: list[dict[str, str]],
        *,
        window: str,
        scope: str,
        schema_version: str,
        now_ms: int,
    ) -> dict[tuple[str, str], dict[str, Any]]: ...

    def current_digests_for_targets(
        self,
        targets: list[dict[str, str]],
        *,
        window: str,
        scope: str,
        schema_version: str,
    ) -> dict[tuple[str, str], dict[str, Any]]: ...
