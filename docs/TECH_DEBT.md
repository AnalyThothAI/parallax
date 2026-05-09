# Tech Debt

> **Scope.** Append-only log of tracked technical debt. Verification artefacts that surface follow-up items append rows here rather than burying them in per-feature `verification.md` files.

## Schema

| Field | Meaning |
|-------|---------|
| Description | One-line summary of the debt. |
| Introduced | Commit SHA or spec slug that introduced it. |
| Area | One of `collector`, `pipeline`, `storage`, `retrieval`, `api`, `web`, `harness`, `infra`. |
| Severity | `low`, `medium`, `high`. |
| Impact | One sentence on what it costs us to leave this. |
| Owner | Name or `unowned`. |

Order rows by severity (high first) then by date introduced (oldest first).

## Open

| Description | Introduced | Area | Severity | Impact | Owner |
|-------------|------------|------|----------|--------|-------|
| `test_rule_uniqueness` should be split into `test_rule_ownership` + `test_routers_have_no_governance_phrases`; add comment explaining the `path.exists()` guard | 2026-05-09 (harness-restructure) | harness | low | Future failure messages would be more actionable | unowned |
| `regen_ws_protocol.py` produces a sparse table because `api/ws.py` uses JSON dicts not typed message classes | 2026-05-09 (harness-restructure) | api | low | The auto-generated `ws-protocol.md` doesn't fully document the wire protocol until message classes exist | unowned |
| `RULE_PHRASES` strings in `tests/test_harness_structure.py` are tightly coupled to verbatim governance prose; rewording governance files breaks the test | 2026-05-09 (harness-restructure) | harness | low | Test brittleness; mitigate by re-anchoring on stable phrases or by relaxing to fuzzy match | unowned |

## Closed

| Description | Introduced | Resolved | Resolution |
|-------------|------------|----------|------------|
