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
| `regen_ws_protocol.py` produces a sparse table because `app/surfaces/api/ws.py` uses JSON dicts not typed message classes | 2026-05-09 (harness-restructure) | api | low | The auto-generated `ws-protocol.md` doesn't fully document the wire protocol until message classes exist | unowned |
| `RULE_PHRASES` strings in `tests/test_harness_structure.py` are tightly coupled to verbatim governance prose; rewording governance files breaks the test | 2026-05-09 (harness-restructure) | harness | low | Test brittleness; mitigate by re-anchoring on stable phrases or by relaxing to fuzzy match | unowned |
| `TOKEN_RADAR_RESOLVER_POLICY_VERSION` is duplicated in `domains/token_intel/_constants.py` (canonical) and inlined with sync comments in `domains/asset_market/repositories/registry_repository.py` + `domains/asset_market/queries/pending_market_observation_query.py` to break a circular import | 2026-05-10 (src-domain-package-restructure, Task 5) | architecture | medium | Drift risk if the canonical value changes; better long-term fix is to move runtime function re-exports out of `domains/token_intel/interfaces.py` so the cycle disappears, or to put the constant in a cross-domain leaf module | unowned |
| `domains/token_intel/interfaces.py` imports from `runtime/token_resolution_refresh` to re-export `deferred_token_radar_projection`, `refresh_recent_token_state`, `reprocess_recent_token_intents`, `WINDOW_MS`. This couples the public interface to runtime and is what creates the asset_market↔token_intel cycle that drove the constant duplication above | 2026-05-10 (src-domain-package-restructure, Task 5) | architecture | medium | Removing these re-exports would let the duplicated constants be eliminated; callers in app/runtime can use deeper paths since composition root is exempt from cross-domain rules | unowned |
| `MarketRepository` was added to `domains/asset_market/interfaces.py` even though only `app/runtime/repository_session.py` consumes it, and composition root is exempt from cross-domain rules | 2026-05-10 (src-domain-package-restructure, Task 4) | architecture | low | Over-exposure of the public interface surface; shrink the interface during a future cleanup pass | unowned |
| `domains/evidence/types/entity.py` is a thin re-export shim (`EVM_QUERY_CHAINS`, `ExtractedEntity`, `normalize_ca` from `services/entity_extractor.py`) added so evidence repositories can import these constants without importing from `services/`. Future work could split `entity_extractor.py` so the constants live in `types/` directly and the shim disappears | 2026-05-10 (src-domain-package-restructure, Task 3) | architecture | low | Mild indirection; not a correctness issue | unowned |

## Closed

| Description | Introduced | Resolved | Resolution |
|-------------|------------|----------|------------|
