"""Load pulse agent prompts from markdown files with route-specific sections.

Each prompt file lives at ``domains/pulse_lab/prompts/{role}.md`` and contains:

- a static base preamble (anti-injection prefix + role / schema)
- one or more ``## Route: <name>`` sections, exactly one of which is selected
  per call based on the runtime ``DecisionRoute``.

The base preamble is intentionally large (>= 4 KiB) so the LLM provider can
cache it across calls; only the route-specific tail rotates per candidate.
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

from parallax.domains.pulse_lab.types.agent_decision import DecisionRoute

_PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"
_ROUTE_HEADING_RE = re.compile(r"^##\s+Route:\s+(?P<route>\w+)\s*$", re.MULTILINE)
_KNOWN_ROLES = ("signal_analyst", "bear_case", "risk_portfolio_judge")


@lru_cache(maxsize=8)
def _read_file(path_str: str) -> str:
    return Path(path_str).read_text(encoding="utf-8")


def load_prompt(role: str, route: DecisionRoute) -> str:
    """Load markdown prompt for ``role`` and render only the ``route`` section.

    Returns the base preamble concatenated with the single matching
    ``## Route: <route>`` section. Other route sections are stripped.

    Raises:
        ValueError: when ``role`` is not a known prompt role.
        RuntimeError: when the prompt file is missing, or the requested
            ``route`` section does not exist inside the file.
    """
    role_clean = str(role).strip()
    if role_clean not in _KNOWN_ROLES:
        raise ValueError(f"unknown prompt role: {role_clean!r}")
    path = _PROMPTS_DIR / f"{role_clean}.md"
    if not path.exists():
        raise RuntimeError(f"prompt file not found: {path}")
    text = _read_file(str(path))

    matches = list(_ROUTE_HEADING_RE.finditer(text))
    if not matches:
        return text.strip()

    base = text[: matches[0].start()].rstrip()
    route_target = str(route).strip().lower()
    for i, match in enumerate(matches):
        if match.group("route").strip().lower() == route_target:
            section_start = match.start()
            section_end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            section = text[section_start:section_end].rstrip()
            return f"{base}\n\n{section}"

    raise RuntimeError(
        f"prompt {role_clean}.md does not contain ## Route: {route_target} section",
    )


def load_signal_analyst_prompt(route: DecisionRoute) -> str:
    return load_prompt("signal_analyst", route)


def load_bear_case_prompt(route: DecisionRoute) -> str:
    return load_prompt("bear_case", route)


def load_risk_portfolio_judge_prompt(route: DecisionRoute) -> str:
    return load_prompt("risk_portfolio_judge", route)


__all__ = [
    "load_bear_case_prompt",
    "load_prompt",
    "load_risk_portfolio_judge_prompt",
    "load_signal_analyst_prompt",
]
