from __future__ import annotations

from typing import Any, Protocol


class NarrativeDigestReader(Protocol):
    def current_digests_for_targets(
        self,
        targets: list[dict[str, str]],
        *,
        window: str,
        scope: str,
        schema_version: str,
    ) -> dict[tuple[str, str], dict[str, Any]]: ...

