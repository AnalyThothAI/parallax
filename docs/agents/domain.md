# Domain Docs

How engineering skills should consume this repository's domain documentation before exploring the codebase.

## Before exploring, read these

- `CONTEXT.md` at the repository root, or
- `CONTEXT-MAP.md` at the repository root if it exists, then each relevant context document, and
- ADRs under `docs/adr/` that touch the area being changed.

If any of these files do not exist, proceed silently. Do not create them pre-emptively; domain-modeling work creates them when terminology or decisions are actually resolved.

The repository is currently treated as a single context unless `CONTEXT-MAP.md` is introduced.

## Use the glossary's vocabulary

When an output names a domain concept in an issue title, proposal, hypothesis, or test, use the term defined by the project glossary. Do not drift to synonyms the glossary explicitly avoids.

If a needed concept is absent, reconsider whether it is established project language. Record a genuine gap for domain-modeling work rather than silently inventing a competing term.

## Flag ADR conflicts

If an output contradicts an existing ADR, surface the conflict explicitly instead of silently overriding it.
