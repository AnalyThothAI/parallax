# Narrative Intel Architecture

Narrative Intel is now an admission read-model lane downstream of Token Radar.
Its active runtime truth starts with material facts (`events`, token
resolutions, market facts, and current `token_radar_current_rows`) and writes
one current read model:

```text
token_radar_current_rows
  -> narrative_admission_dirty_targets
  -> narrative_admissions
  -> API / WebSocket / CLI reads
```

## Source-Set Truth

`narrative_admissions.source_event_ids_json` is the only current source-set
truth for a target/window/scope/schema. Public readers may compare this frontier
with historical semantic or digest rows, but those rows do not define current
source volume and are not refreshed by active runtime workers.

## Writer Ownership

`NarrativeAdmissionWorker` is the runtime writer for `narrative_admissions`.
It claims `narrative_admission_dirty_targets`, exact-loads the target Radar
context, recomputes the source set from material facts, and upserts only changed
admission rows. Empty queues return without scanning Token Radar or event
history.
The worker is wake-in only: `token_radar_updated` and `resolution_updated`
may wake it, but it emits no downstream wake. Its admission limit, source-set
limit, dirty-target lease, retry delay, rank thresholds, and worker-session
statement timeout are formal `settings.workers.narrative_admission` fields;
there are no runtime `lease_seconds` / `error_retry_seconds` fallbacks, no
service-local rank-threshold defaults, no carry-forward TTL compatibility, and
no `wake_bus` / `wake_emitter` constructor aliases.
Claimed dirty-target `window` and `scope` are validated against the same formal
worker settings before admission-target or source-set reads, and dirty-target
claim `UPDATE ... RETURNING` rowcount must match returned claimed rows before
source-set evidence is loaded. Malformed claim dimensions fail through
dirty-target error/retry; the worker must not treat an unknown scope as
all-public or restore an unknown window to a 24h source-set width.
Worker claim/done/error writes are caller-owned inside
`RepositorySession.transaction`. Repository-owned dirty-target enqueue, claim,
done, error, and reschedule mutations require a callable connection
transaction before queue SQL; missing transaction support is a contract failure,
not permission to call `self.conn.commit()`.
Dirty-target enqueue requires a positive producer-supplied
`source_watermark_ms`; missing, zero, negative, boolean, or string watermarks
fail before queue SQL, and enqueue SQL does not carry a zero-watermark
compatibility branch.
Dirty-target done/error/reschedule completion keys require the positive
`attempt_count`, non-empty `lease_owner`, and `payload_hash` returned by
`claim_due`; malformed keys fail before SQL instead of being restored to zero
attempts, empty owners, or empty payload hashes.
Dirty-target done/error/reschedule changed-row counts require PostgreSQL
`cursor.rowcount`; missing or invalid rowcount is malformed repository/driver
state, not zero changed narrative dirty-target work.
Repository-owned `narrative_admissions` upsert and stale-target deletion also
require a callable connection transaction before serving-row SQL; the worker
path remains caller-owned with `commit=False` inside `RepositorySession.transaction`.
Their returned write counts require PostgreSQL `cursor.rowcount` evidence;
missing or invalid rowcount is malformed repository/driver state, not zero
changed admission work.
Source, label, and text fingerprint primitives live in
`narrative_intel.types.fingerprints`; repositories depend on that leaf type
module and must not import deterministic service modules for payload identity.

The former runtime LLM agents are removed:

- `MentionSemanticsWorker`
- `TokenDiscussionDigestWorker`
- narrative LiteLLM provider/client wiring
- narrative prompt files
- `ops rebuild-narrative-intel`

Do not reintroduce disabled compatibility workers, aliases, shadow queues, or
HTTP maintenance paths for those agents.

## Public Read Contract

Public Token Radar and Token Case reads may still expose
`discussion_digest.currentness` for legacy rows. That field is read-only
composition: the last historical ready digest, when present, is compared with
the current `narrative_admissions` frontier. Missing, stale, or out-of-frontier
state must be explicit. Token Radar hydration reads formal target identity from
the public row `target.target_type` / `target.target_id` object, or from direct
formal `target_type` / `target_id` fields when a non-API caller already owns that
shape. API routes must not synthesize top-level target fields for hydration;
legacy `type` / `id` aliases are treated as missing narrative target identity
rather than restored. API routes never run providers and never write narrative
tables.
Product reads do not expose retired semantic backlog or imply a semantic worker
will continue processing. Selected post detail may show a historical labeled
semantic row when one already exists; missing legacy semantics are explicit
missing context, not runtime queue state. Post-detail semantic hydration reads
the selected post keyset through one SQL statement with
`unnest(%s::text[], %s::text[], %s::text[]) WITH ORDINALITY`, `distinct_posts`,
and a lateral latest-row probe; it must not loop over posts and query
`token_mention_semantics` once per post.

## Hard Cut

This domain does not keep runtime compatibility aliases for removed behavior.
Source-age prune compatibility, old fallback digest hydration, old collapsed
`digest_not_ready` reasons, Token Radar `type` / `id` target identity aliases,
narrative LLM lanes, and narrative rebuild CLI surfaces are removed rather than
shadowed by runtime aliases.
