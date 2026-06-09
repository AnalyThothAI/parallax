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
state must be explicit. API routes never run providers and never write narrative
tables.

## Hard Cut

This domain does not keep runtime compatibility aliases for removed behavior.
Source-age prune compatibility, old fallback digest hydration, old collapsed
`digest_not_ready` reasons, narrative LLM lanes, and narrative rebuild CLI
surfaces are removed rather than shadowed by runtime aliases.
