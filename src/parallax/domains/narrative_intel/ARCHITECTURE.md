# Narrative Intel Architecture

Narrative Intel is a deterministic admission read-model lane downstream of
Token Radar. Its active chain is intentionally small:

```text
material facts + token_radar_current_rows
  -> narrative_admission_dirty_targets
  -> NarrativeAdmissionWorker
  -> narrative_admissions
  -> API narrative_admission
```

## Truth and identity

`events`, current token resolutions, market facts, and
`token_radar_current_rows` are material inputs. `narrative_admissions` is the
only Narrative serving read model. Its stable identity is
`(target_type, target_id, window, scope)`; schema, run, attempt, generation,
timestamp, and UUID values are not row identity.

`source_event_ids_json`, `source_max_received_at_ms`, source counts, and author
counts describe the admission source frontier. Provider frames and removed
semantic/digest rows are not current facts or fallback inputs.

## Writer ownership

`NarrativeAdmissionWorker` is the sole runtime writer for
`narrative_admissions`. It claims `narrative_admission_dirty_targets`, validates
the claimed window and scope against worker settings, exact-loads the Radar
target, recomputes the source set from material facts, and upserts only when the
stable payload changes. An empty queue never causes a Radar or event scan.

The worker is wake-in only. `token_radar_updated` and `resolution_updated` may
wake it, but it emits no downstream wake. The queue lease, retry delay, limits,
rank thresholds, and statement timeout come from
`settings.workers.narrative_admission`; runtime aliases and service-local
defaults are not supported.

Queue mutations and admission serving-row writes use an explicit connection
transaction. Claimed completion keys require the positive `attempt_count`,
non-empty `lease_owner`, and `payload_hash` returned by the claim. Changed-row
counts come from PostgreSQL `cursor.rowcount`; missing or invalid rowcount is a
driver contract failure, not zero work.

The admission source watermark comes only from positive Token Radar
`source_max_received_at_ms`. Publication time and runtime time are not source
watermark substitutes. Payload hashes exclude lifecycle timestamps so an
unchanged recomputation writes zero serving rows.

## Public read contract

Token Radar and Token Case expose `narrative_admission`, never a generated
narrative digest. The object contains only:

- `status`: `admitted`, `suppressed`, or `missing`;
- `reason` and `is_current`;
- `computed_at_ms`;
- `currentness.display_status` and `currentness.reason`;
- `coverage.source_mentions` and `coverage.independent_authors`;
- explicit `data_gaps` for missing, suppressed, or unsupported states.

The payload is derived only from `narrative_admissions`. Unsupported windows
use `status=missing` with `currentness.display_status=unsupported_window`.
Target identity comes from formal `target_type` / `target_id` fields; legacy
`type` / `id` aliases are not repaired. API routes do not call providers or
write Narrative tables. Target-post responses remain raw evidence pages and do
not attach per-post semantic placeholders.

## Hard cut

The following runtime and storage surfaces are removed, not disabled:

- per-post mention semantics and discussion-digest workers;
- `token_mention_semantics`, `token_discussion_digests`, narrative model-run,
  and digest dirty-target tables;
- Narrative model-provider/client and prompt wiring;
- digest/currentness compatibility readers and per-post semantic hydration;
- downstream evidence-packet Narrative digest dependencies;
- `ops rebuild-narrative-intel` and other repair shims for removed lanes.

Do not reintroduce aliases, shadow queues, ghost payload fields, or tests that
imply these removed lanes will resume processing.
