# Narrative Intel Architecture

Narrative Intel is a CQRS read-model lane downstream of Token Radar. Its
business truth starts with material facts (`events`, token resolutions, market
facts, and current `token_radar_rows`) and then flows through three rebuildable
read models:

```text
token_radar_rows
  -> narrative_admissions
  -> token_mention_semantics
  -> token_discussion_digests
  -> API / WebSocket / CLI reads
```

## Source-Set Truth

`narrative_admissions.source_event_ids_json` is the only current source-set
truth for a target/window/scope/schema. Downstream coverage must expand admitted
source sets and then left-check semantics rows. A source event may be counted
once for each current admission it belongs to, including across windows and
scopes. Multiple semantic fingerprints for the same admission-source row count
as one covered source row.

Prompt samples are not completeness. Digest prompts may cap the number of
mentions sent to the LLM, but completeness uses full-source aggregate counts:
source rows, semantic rows, missing rows, pending/retryable rows, labeled rows,
and terminal unavailable rows.

## Writer Ownership

`NarrativeAdmissionWorker` is the runtime writer for `narrative_admissions`.
`MentionSemanticsWorker` is the runtime writer for `token_mention_semantics`.
`TokenDiscussionDigestWorker` is the runtime writer for
`token_discussion_digests`. Repository methods may contain SQL for these tables,
but normal runtime writes are reached only through the owning worker.

`ops rebuild-narrative-intel` is the maintenance exception. While it holds all
narrative worker advisory locks, it may run hard-cut cleanup to delete obsolete
queued/retryable/stale semantics and mark suppressed or fingerprint-mismatched
current digests stale. That path is not callable from HTTP routes and is not a
second runtime writer.

## Public Digest Contract

A public current digest must match an admitted current source set and the same
`source_fingerprint`. If no usable digest exists, public reads return a
non-persisted missing-state reason:

- `digest_not_ready`: admitted source set exists, but no current digest is ready.
- `digest_stale`: a current digest exists but no longer matches the admitted
  source fingerprint.
- `not_in_current_frontier`: the target/window/scope is no longer admitted.

Digest and semantics budget pressure is explicit. `llm_cycle_budget_exhausted`
means the digest worker deferred an otherwise due LLM call for cycle capacity.
`llm_failure_budget_exhausted` means provider failures consumed the cycle's
failure budget and remaining LLM work backed off.

## Hard Cut

This domain does not keep runtime compatibility aliases for removed behavior.
Source-age prune compatibility, old fallback digest hydration, and old collapsed
`digest_not_ready` reasons are removed rather than shadowed by runtime aliases.
