"""Macro intel persistence repositories."""

from parallax.domains.macro_intel.repositories.macro_research_repository import (
    MacroResearchRepository,
    PostgresMacroResearchReadPort,
)

__all__ = ["MacroResearchRepository", "PostgresMacroResearchReadPort"]
