# News Duplicate Hard-Cut Optimization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eliminate user-visible duplicate News rows by making canonical URL identity, generic URL hygiene, and OpenNews material duplicate handling deterministic at the fact layer.

**Architecture:** Keep the KISS News flow: provider observation -> canonical item -> observation edge -> deterministic processing -> optional item brief -> page row. Do not add a story layer, LLM fuzzy dedup, UI hiding, compatibility flags, or legacy fallback modes. Article-only public URL identity and bounded OpenNews material identity are resolved before `news_items` and `news_item_observation_edges` are published; material duplicate handling must be order-independent and guarded by deterministic advisory locks.

**Tech Stack:** Python 3.13, PostgreSQL/Alembic, Parallax News Intel repositories/workers, pytest, ruff, Docker Compose.

---

**Status:** Audit-upgraded for subagent-driven implementation
**Date:** 2026-06-04
**Owning spec:** Current News root-cause audit plus `docs/superpowers/specs/active/2026-05-28-news-intel-dedup-root-fix-cn.md`, `docs/superpowers/specs/active/2026-05-31-news-brief-opennews-dedup-cost-hard-cut-cn.md`, `docs/superpowers/specs/active/2026-06-01-news-intel-kiss-simplification-cn.md`, `docs/superpowers/specs/completed/2026-06-03-news-intel-hard-cut-residual-root-fix-cn.md`, and `src/parallax/domains/news_intel/ARCHITECTURE.md`
**Worktree:** `.worktrees/news-duplicate-hard-cut-optimization`
**Branch:** `codex/news-duplicate-hard-cut-optimization`
**Implementation progress:** Tasks 1-9 are implemented and focused tests pass; Task 10 remains for full rollout verification.

## Non-Negotiable Constraints

- No compatibility mode, feature flag, legacy identity branch, or "old behaviour if present" code.
- No frontend-only hide, API-only filter, or page projection masking as the root fix.
- No LLM/vector/embedding/fuzzy dedup in this cut.
- No new News story worker or cross-domain write.
- No generic homepage, aggregator, feed, preview, or announcement index URL may be treated as article canonical URL.
- No `live_page` URL may be treated as hard canonical URL in this cut; live-like URLs are raw/provider evidence unless a future spec explicitly changes that policy.
- No duplicate public row for the same hard public URL, same OpenNews provider article, or same bounded material duplicate key.
- Derived read models and agent briefs may be deleted/rebuilt; provider observations and raw payload evidence must remain auditable.
- Runtime canonicalization must be order-independent: public-first/fallback-later and fallback-first/public-later arrival orders produce the same surviving canonical item and edge set.
- Runtime material duplicate lookup must be concurrency-safe: take a deterministic material advisory lock before candidate lookup, then lock canonical item keys in stable order.
- Ops repair must guard against active News workers/leases, preserve or remap agent run audit semantics before deleting zero-edge items, clean stale page/brief dirty targets for old ids, and enqueue only representative targets.
- Diagnostics must prove fact-layer, queue-layer, brief-layer, and serving-layer duplicate gates; visible `/api/news` rows alone are not a completion signal.

## Target Runtime Shape

```text
OpenNews/RSS provider payload
  -> normalize one observation URL
     - allowed public article or single-slug article URL stays public
     - live/homepage/aggregator/feed/preview URL becomes provider fallback when OpenNews provides a global article id
  -> compute canonical identity
     - admitted article public URL wins as the serving canonical identity
     - eligible OpenNews fallback uses deterministic material identity before provider article id
     - public URL arrival remaps existing material/provider fallback edges into the public item
     - provider article id is fallback only when no admitted public URL or eligible material identity exists
  -> upsert news_items + observation edge
  -> delete/rebuild stale derived rows and stale dirty targets when an edge moves
  -> process / brief / page projection
  -> /api/news contains one row per current canonical item
```

## Audit Upgrade Overrides

The four read-only audit agents found that the earlier draft was directionally correct but not root-fix complete. The following overrides are binding for all tasks below:

1. Material identity is bidirectional. If a fallback material item exists and a public URL item arrives later, remap fallback edges to the public item. If the public item exists and a fallback arrives later, attach the fallback edge to the public item. Both orders must pass the same integration test assertions.
2. Material identity is explicit. Eligible OpenNews fallback observations use a deterministic `material_title` canonical key instead of a provider-article key. The edge evidence stores `material_title_fingerprint`, `material_window_bucket_ms`, and `material_symbol_key`.
3. Material lookup is locked. Repository code must take deterministic advisory locks over every material window bucket that intersects the `published_at_ms ± material_match_window_ms` candidate range for `(source_id, material_title_fingerprint)`. The lock is deliberately not partitioned by `material_symbol_key`; symbols remain evidence and a compatibility filter, but empty-symbol vs non-empty-symbol observations must not bypass concurrency protection. Candidate lookup must not use an arbitrary `LIMIT 100`; it must scan the bounded indexed source/window range.
4. `live_page` is blocked from hard public URL identity. The Coindesk live duplicate class is handled by material identity, not by treating all live URLs as hard article URLs.
5. OpenNews fallback URL construction must derive `opennews://item/{id}` from `provider_article_id`, `provider_article_key`, or OpenNews `id`; it must not require the raw link to already be `opennews://item/{id}`.
6. `same_qualified_content` and `same_content_hash` must be unified. The implementation must either emit `same_content_hash` for qualified content or expand the DB check and tests consistently; this plan chooses `same_content_hash` to match the current schema/spec wording.
7. Alembic `CREATE INDEX CONCURRENTLY` must run in `op.get_context().autocommit_block()`.
8. Repair execution must reuse or extract repository helpers for edge remap, observation summary refresh, representative reselect, derived cleanup, stale dirty-target cleanup, and representative re-enqueue. It must not hand-roll a separate SQL order that can drift from runtime upsert.
9. Before real-data repair or diagnostics, run `uv run parallax config` and report only redacted config/workers paths and boolean status. Runtime config must point at `~/.parallax/`.
10. Detail-page redesign and AI source-chain/input-quality improvements are follow-up work. This hard-cut only removes duplicate facts/brief targets/page rows and preserves the evidence needed for that later UI/AI task.

## File-Level Edits

### `src/parallax/domains/news_intel/services/news_url_identity.py`

- Replace storage policy ambiguity with one explicit policy function.
- Keep `url_identity_kind()` as diagnostic only.
- Remove `is_article_identity()` and update tests to assert `url_identity_kind()` plus `public_url_identity_policy()` directly.
- Add this shape:

```python
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PublicUrlIdentityPolicy:
    normalized_url: str
    identity_key: str
    identity_kind: str
    blocked_reason: str

    @property
    def allowed(self) -> bool:
        return bool(self.identity_key)


def public_url_identity_policy(canonical_url: object) -> PublicUrlIdentityPolicy:
    normalized_url = canonicalize_url(canonical_url)
    if not normalized_url:
        return PublicUrlIdentityPolicy("", "", "unknown", "not_public_url")

    split = urlsplit(normalized_url)
    if split.scheme.lower() not in {"http", "https"} or not split.netloc:
        return PublicUrlIdentityPolicy(normalized_url, "", "unknown", "not_public_url")

    social_status_key = _social_status_identity_key(split.hostname or "", split.path or "")
    if social_status_key:
        return PublicUrlIdentityPolicy(normalized_url, social_status_key, "article", "")

    lower_segments = _path_segments(split.path or "")
    if _is_preview_path(lower_segments):
        return PublicUrlIdentityPolicy(normalized_url, "", url_identity_kind(normalized_url), "preview")
    if _is_generic_announcement_path(lower_segments):
        return PublicUrlIdentityPolicy(normalized_url, "", url_identity_kind(normalized_url), "generic_announcement")
    if _is_feed_index_path(lower_segments):
        return PublicUrlIdentityPolicy(normalized_url, "", url_identity_kind(normalized_url), "feed_index")

    identity_kind = url_identity_kind(normalized_url)
    if identity_kind in {"homepage", "aggregator", "live_page"}:
        return PublicUrlIdentityPolicy(normalized_url, "", identity_kind, identity_kind)

    return PublicUrlIdentityPolicy(normalized_url, f"canonical-url:{normalized_url}", identity_kind, "")


def hard_public_url_identity_key(canonical_url: object) -> str:
    return public_url_identity_policy(canonical_url).identity_key
```

### `src/parallax/domains/news_intel/services/feed_item_normalizer.py`

- Sanitize canonical URL before `NormalizedNewsItem` is created.
- If the raw link is a blocked public URL for OpenNews, convert it to `opennews://item/{provider_article_id}` instead of storing the homepage/aggregator URL as canonical URL.
- Do not preserve old generic URL as a canonical URL for serving. Raw payload still carries the upstream link.
- Add this helper shape:

```python
from parallax.domains.news_intel.services.news_url_identity import public_url_identity_policy


def _canonical_news_url_or_fallback(link: object, entry: Mapping[str, Any]) -> str:
    public_policy = public_url_identity_policy(link)
    if public_policy.allowed:
        return public_policy.normalized_url

    fallback_url = _opennews_fallback_url(link, entry) or _opennews_provider_fallback_url(entry)
    if fallback_url:
        return fallback_url

    if public_policy.normalized_url and not public_policy.blocked_reason:
        return public_policy.normalized_url
    return ""


def _opennews_provider_fallback_url(entry: Mapping[str, Any]) -> str:
    provider_article_key = _first_text(entry, "provider_article_key")
    item_id = (
        _first_text(entry, "provider_article_id")
        or _opennews_provider_article_key_id(provider_article_key)
        or _first_text(entry, "id")
    )
    has_opennews_marker = (
        bool(item_id)
        and (
            bool(_first_text(entry, "provider_article_id"))
            or provider_article_key.lower().startswith("opennews:")
            or bool(_first_text(entry, "opennews_method"))
        )
    )
    if not has_opennews_marker or _OPENNEWS_FALLBACK_INVALID_RE.search(item_id):
        return ""
    return f"opennews://item/{item_id.strip()}"
```

- Replace:

```python
canonical_url = canonicalize_url(link)
```

with:

```python
canonical_url = _canonical_news_url_or_fallback(link, entry)
```

### `src/parallax/domains/news_intel/services/news_material_identity.py`

- Create this file. It owns deterministic material duplicate keys for provider fallback items only.
- It must not import repositories or call LLMs.
- Required content:

```python
from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping, Sequence

from parallax.domains.news_intel.services.text_normalization import title_fingerprint

_SOURCE_PREFIX_RE = re.compile(
    r"^([A-Z][A-Z0-9&.+/-]*(?:[ -][A-Z][A-Z0-9&.+/-]*){0,2})[:：]\\s+",
    re.IGNORECASE,
)
_SOURCE_PREFIX_ALIASES = frozenset(
    {
        "AFP",
        "BLOOMBERG",
        "BUSINESS INSIDER",
        "CNBC",
        "COINDESK",
        "COIN DESK",
        "FINANCEFEEDS",
        "FINANCE FEEDS",
        "FORBES",
        "JP-BLOOMBERG",
        "TASS",
        "TASS RU",
        "ZEROHEDGE",
    }
)
_MIN_MATERIAL_TOKENS = 6


def material_title_fingerprint(title: object) -> str:
    text = str(title or "").strip()
    match = _SOURCE_PREFIX_RE.match(text)
    if match and match.group(1).strip().upper() in _SOURCE_PREFIX_ALIASES:
        text = text[match.end() :]
    return title_fingerprint(text)


def material_title_is_eligible(fingerprint: str) -> bool:
    return len(str(fingerprint or "").split()) >= _MIN_MATERIAL_TOKENS


def provider_symbol_set(provider_token_impacts: object) -> set[str]:
    symbols: set[str] = set()
    if isinstance(provider_token_impacts, str):
        provider_token_impacts = json.loads(provider_token_impacts or "[]")
    if not isinstance(provider_token_impacts, Sequence):
        return symbols
    for item in provider_token_impacts:
        if not isinstance(item, Mapping):
            continue
        symbol = str(item.get("symbol") or "").strip().upper()
        if symbol:
            symbols.add(symbol)
    return symbols


def symbol_sets_compatible(incoming: Iterable[str], existing: Iterable[str]) -> bool:
    incoming_set = {str(symbol).upper() for symbol in incoming if str(symbol).strip()}
    existing_set = {str(symbol).upper() for symbol in existing if str(symbol).strip()}
    return not incoming_set or not existing_set or bool(incoming_set & existing_set)
```

### `src/parallax/domains/news_intel/services/news_canonical_identity.py`

- Add `material_title_fingerprint` into `CanonicalIdentity.evidence` for every identity.
- Do not make material dedup a pure function here because it needs DB candidate lookup. The repository owns the "attach to existing item" decision.
- Keep priority:

```text
hard public URL
  -> repository material duplicate candidate
  -> deterministic OpenNews material identity
  -> provider-global article id
  -> qualified content
  -> weak source/title/hour
```

### `src/parallax/domains/news_intel/repositories/news_repository.py`

- Add repository-owned material duplicate resolution before `INSERT INTO news_items`.
- The helper must not simply return early for `identity.dedup_key_kind == "canonical_url"`. Public URL identity wins, but public URL arrival must also remap existing material fallback edges into the public item.
- Before material candidate lookup, take deterministic advisory transaction locks over every material window bucket intersecting the lookup range. `material_symbol_key` is recorded in evidence and used for symbol compatibility, but it must not split the lock.

```python
def _lock_material_duplicate_candidate_window(
    self,
    *,
    source_id: str,
    material_fingerprint: str,
    published_at_ms: int,
) -> None:
    for material_window_bucket_ms in _material_window_bucket_ms_values_for_match_window(published_at_ms):
        lock_key = json.dumps(
            [
                "news-material-duplicate-v2",
                str(source_id),
                str(material_fingerprint),
                int(material_window_bucket_ms),
            ],
            separators=(",", ":"),
        )
        self.conn.execute(
            """
            SELECT pg_advisory_xact_lock(
              ('x' || substr(md5(%s), 1, 16))::bit(64)::bigint
            )
            """,
            (lock_key,),
        )
```

- Add helper:

```python
def _material_duplicate_identity_for_observation(
    self,
    *,
    identity: CanonicalIdentity,
    provider_type: str,
    source_id: str,
    provider_item_id: str,
    title: str,
    published_at_ms: int,
    provider_token_impacts: Sequence[Mapping[str, Any]],
) -> CanonicalIdentity:
    if str(provider_type or "").strip().lower() != "opennews":
        return identity
    material_fingerprint = material_title_fingerprint(title)
    if not material_title_is_eligible(material_fingerprint):
        return identity
    material_window_bucket_ms = material_window_bucket_ms_for_published_at(published_at_ms)
    material_symbol_key = material_symbol_key_for_impacts(provider_token_impacts)
    self._lock_material_duplicate_candidate_window(
        source_id=source_id,
        material_fingerprint=material_fingerprint,
        published_at_ms=published_at_ms,
    )

    candidates = self.conn.execute(
        """
        SELECT items.news_item_id,
               items.canonical_item_key,
               items.dedup_key_kind,
               items.dedup_key_confidence,
               items.url_identity_kind,
               items.title,
               items.provider_token_impacts_json,
               items.published_at_ms,
               provider_items.provider_payload_status,
               edges.evidence_json
          FROM news_items AS items
          JOIN news_item_observation_edges AS edges
            ON edges.news_item_id = items.news_item_id
          JOIN news_provider_items AS provider_items
            ON provider_items.provider_item_id = items.provider_item_id
         WHERE items.source_id = %s
           AND items.published_at_ms BETWEEN %s AND %s
           AND items.canonical_item_key <> %s
         ORDER BY
           CASE WHEN items.dedup_key_kind = 'canonical_url' THEN 0 ELSE 1 END,
           CASE WHEN provider_items.provider_payload_status = 'ready' THEN 0 ELSE 1 END,
           items.published_at_ms DESC,
           items.news_item_id ASC
        """,
        (source_id, published_at_ms - 600_000, published_at_ms + 600_000, identity.canonical_item_key),
    ).fetchall()
    incoming_symbols = provider_symbol_set(provider_token_impacts)
    for candidate in candidates:
        if material_title_fingerprint(candidate["title"]) != material_fingerprint:
            continue
        existing_symbols = provider_symbol_set(candidate["provider_token_impacts_json"])
        if not symbol_sets_compatible(incoming_symbols, existing_symbols):
            continue
        return CanonicalIdentity(
            canonical_item_key=str(candidate["canonical_item_key"]),
            news_item_id=str(candidate["news_item_id"]),
            dedup_key_kind=str(candidate["dedup_key_kind"]),
            dedup_key_confidence=str(candidate["dedup_key_confidence"]),
            url_identity_kind=str(candidate["url_identity_kind"]),
            match_type="same_material_title",
            match_confidence="strong",
            evidence={
                **dict(identity.evidence),
                "material_title_fingerprint": material_fingerprint,
                "material_window_bucket_ms": material_window_bucket_ms,
                "material_symbol_key": material_symbol_key,
                "material_existing_news_item_id": str(candidate["news_item_id"]),
                "material_match_window_ms": 600_000,
            },
        )
    return identity
```

- Call the helper immediately after the existing identity selection and before provider article reuse. Then lock the final `identity.canonical_item_key`.

```python
identity = canonical_identity if canonical_identity is not None else computed_identity
identity = self._material_duplicate_identity_for_observation(
    identity=identity,
    provider_type=str(observation["provider_type"] or ""),
    source_id=observation_source_id,
    provider_item_id=str(provider_item_id),
    title=str(title),
    published_at_ms=item_published_at_ms,
    provider_token_impacts=provider_token_impacts_payload,
)
```
- When an edge moves to a new item, keep existing cleanup behaviour:
  - `_refresh_news_item_observation_summary()`
  - `_delete_zero_edge_news_item()`
  - `_reselect_news_item_representative_from_edges()`
  - `_clear_item_scoped_derived_facts()`
- Add or reuse repository helpers for:
  - remapping all edges from an old material/provider fallback item into a later public URL item;
  - deleting/terminalizing stale `news_projection_dirty_targets` for old duplicate ids;
  - preserving agent run audit rows before any zero-edge item delete that would cascade audit rows.
- Remove code that gives OpenNews provider id permanent priority over a stronger material duplicate. Provider id is still evidence, not a public row boundary when the item is a missing-link duplicate.

### Storage / Migrations

- Add one Alembic migration under `src/parallax/platform/db/alembic/versions/`.
- Migration name: `20260604_0148_news_material_duplicate_hard_cut.py`.
- Extend observation edge match type check and align runtime/schema match types. `news_canonical_identity.py` must emit `same_content_hash` for qualified content instead of `same_qualified_content`.

```sql
ALTER TABLE news_item_observation_edges
  DROP CONSTRAINT IF EXISTS news_item_observation_edges_match_type_check;

ALTER TABLE news_item_observation_edges
  ADD CONSTRAINT news_item_observation_edges_match_type_check
  CHECK (
    match_type = ANY (
      ARRAY[
        'same_provider_article_id',
        'same_article_url',
        'same_canonical_url',
        'same_content_hash',
        'same_material_title',
        'weak_title_time_source'
      ]::text[]
    )
  );
```

- Add candidate lookup index:

```sql
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_news_items_source_published_material_lookup
  ON news_items(source_id, published_at_ms DESC, news_item_id);
```

The Alembic implementation must wrap the concurrent index in autocommit:

```python
with op.get_context().autocommit_block():
    op.execute(
        """
        CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_news_items_source_published_material_lookup
          ON news_items(source_id, published_at_ms DESC, news_item_id)
        """
    )
```

- No legacy table, no compatibility column, no feature flag.

### `src/parallax/app/surfaces/cli/parser.py`

- Add one hard-cut repair command:

```python
repair_news_duplicates = ops_subcommands.add_parser(
    "repair-news-duplicates-hard-cut",
    help="repair News canonical URL, generic URL, and OpenNews material duplicates",
)
repair_news_duplicates.add_argument("--limit", type=int, default=20000)
repair_news_duplicates_mode = repair_news_duplicates.add_mutually_exclusive_group(required=True)
repair_news_duplicates_mode.add_argument("--dry-run", action="store_true")
repair_news_duplicates_mode.add_argument("--execute", action="store_true")
```

### `src/parallax/domains/news_intel/services/news_duplicate_hard_cut_repair.py`

- Create this file. It is an ops repair service, not runtime compatibility code.
- It must be idempotent and run against current policy only.
- `execute=True` must fail fast when News workers/leases are active. Reuse the worker/advisory guard pattern from `news_intel_hard_cut_cleanup.py`.
- It performs three passes in one transaction:
  1. Promote/merge every row whose `public_url_identity_policy(canonical_url).allowed` is true to `canonical-url:{normalized_url}`.
  2. Rewrite blocked generic public URLs to provider fallback canonical URLs, preserving raw payload evidence.
  3. Remap OpenNews material duplicates into one canonical item using `material_title_fingerprint`.
- It must remap/migrate or explicitly preserve agent audit rows before deleting zero-edge duplicate items.
- It must delete or terminalize stale `page` and `brief_input` dirty targets for old duplicate ids and enqueue only surviving representative ids.
- It must delete/rebuild derived rows for affected representatives by using the same repository helper order as runtime upsert.
- Return counters:

```python
{
    "mode": "dry_run" | "execute",
    "hard_url_groups_repaired": int,
    "generic_urls_rewritten": int,
    "material_duplicate_groups_repaired": int,
    "edges_remapped": int,
    "zero_edge_items_deleted": int,
    "page_rows_deleted": int,
    "stale_dirty_targets_deleted": int,
    "agent_audit_rows_remapped": int,
    "dirty_targets_enqueued": int,
}
```

### `src/parallax/app/surfaces/cli/commands/ops.py`

- Wire `repair-news-duplicates-hard-cut`.
- Do not accept flags that preserve old behaviour.
- Use existing `repositories(settings)` and commit only through the repair service.

```python
if args.ops_command == "repair-news-duplicates-hard-cut":
    data = repair_news_duplicates_hard_cut(
        repos,
        limit=max(1, int(args.limit)),
        execute=bool(args.execute),
        now_ms=_now_ms(),
    )
    return 0, {"ok": True, "data": data}
```

### `src/parallax/domains/news_intel/repositories/news_repository.py` Diagnostics

- Extend `news_dedup_diagnostics()` with current-policy duplicate counters:

```python
"hard_public_url_visible_duplicate_excess": 0,
"generic_public_url_visible_rows": 0,
"material_title_visible_duplicate_excess": 0,
"fact_layer_material_duplicate_excess": 0,
"stale_duplicate_brief_rows": 0,
"stale_duplicate_dirty_targets": 0,
"top_material_title_duplicate_groups": [],
```

- Existing `top_visible_canonical_duplicate_groups` remains, but the acceptance gate uses the new explicit fact/queue/brief/serving counters.

### Docs

- Update `src/parallax/domains/news_intel/ARCHITECTURE.md`:
  - Public URL hard identity is "public URL allowed by `public_url_identity_policy`", not "all http/https".
  - `url_identity_kind` is diagnostic.
  - Generic URLs are raw/provider evidence, not article canonical URLs.
  - OpenNews missing-link duplicates can be folded by bounded material title identity.
- Update `docs/WORKERS.md` News row to mention `repair-news-duplicates-hard-cut` only as ops repair, not a runtime path.

## Task Breakdown

### Task 1: Public URL Policy Single Source

**Status:** Completed in current workspace; unit tests passed.

**Files:**
- Modify: `src/parallax/domains/news_intel/services/news_url_identity.py`
- Modify: `tests/unit/domains/news_intel/test_news_url_identity.py`
- Modify: `tests/unit/domains/news_intel/test_news_canonical_identity.py`

- [ ] **Step 1: Write failing public URL policy tests**

Add tests:

```python
def test_public_url_policy_allows_single_segment_news_slug() -> None:
    service = _service()
    url = "https://financefeeds.com/bessent-urges-lawmakers-to-pass-crypto-clarity-act-this-summer"

    policy = service.public_url_identity_policy(url)

    assert policy.allowed is True
    assert policy.identity_key == f"canonical-url:{url}"
    assert policy.identity_kind == "unknown"
    assert policy.blocked_reason == ""


def test_public_url_policy_blocks_generic_source_urls() -> None:
    service = _service()

    assert service.public_url_identity_policy("https://www.afp.com").blocked_reason == "homepage"
    assert service.public_url_identity_policy("https://tass.ru/").blocked_reason == "homepage"
    assert service.public_url_identity_policy("https://tass.com/world").blocked_reason == "aggregator"
    assert service.public_url_identity_policy("https://www.afp.com/en/news").blocked_reason == "aggregator"
    assert service.public_url_identity_policy("https://www.coindesk.com/markets").blocked_reason == "aggregator"
    assert service.public_url_identity_policy("https://www.coindesk.com/live").blocked_reason == "live_page"
    assert service.public_url_identity_policy("https://news.6551.io/preview/abc").blocked_reason == "preview"
    assert service.public_url_identity_policy("https://example.com/rss.xml").blocked_reason == "feed_index"
```

- [ ] **Step 2: Run tests and confirm failure**

Run:

```bash
uv run pytest tests/unit/domains/news_intel/test_news_url_identity.py -q
```

Expected: fails because `public_url_identity_policy` does not exist.

- [ ] **Step 3: Implement policy object and update `hard_public_url_identity_key()`**

Implement the code shape from File-Level Edits.

- [ ] **Step 4: Run unit tests**

Run:

```bash
uv run pytest tests/unit/domains/news_intel/test_news_url_identity.py tests/unit/domains/news_intel/test_news_canonical_identity.py -q
```

Expected: all tests pass.

### Task 2: Generic URL Ingest Hygiene

**Status:** Completed in current workspace; unit tests passed.

**Files:**
- Modify: `src/parallax/domains/news_intel/services/feed_item_normalizer.py`
- Modify: `tests/unit/domains/news_intel/test_feed_item_normalizer.py`

- [ ] **Step 1: Write failing tests**

Add tests:

```python
def test_opennews_homepage_link_uses_provider_fallback_url() -> None:
    item = normalize_feed_entry(
        "6551.io",
        {
            "provider_article_id": "2514613",
            "provider_article_key": "opennews:2514613",
            "opennews_method": "news.rest",
            "link": "https://tass.ru/",
            "title": "TASS: FOUR TU-214 AIRCRAFT ARE PLANNED TO BE DELIVERED IN 2026",
            "published_at_ms": 1_780_542_000_000,
        },
        fetched_at_ms=1_780_542_000_000,
    )

    assert item is not None
    assert item.canonical_url == "opennews://item/2514613"
    assert item.raw_payload["link"] == "https://tass.ru/"


def test_opennews_article_link_keeps_public_url() -> None:
    url = "https://financefeeds.com/bessent-urges-lawmakers-to-pass-crypto-clarity-act-this-summer"
    item = normalize_feed_entry(
        "6551.io",
        {
            "provider_article_id": "2511056",
            "provider_article_key": "opennews:2511056",
            "opennews_method": "news.rest",
            "link": url,
            "title": "Bessent Urges Lawmakers to Pass Crypto Clarity Act This Summer",
        },
        fetched_at_ms=1_780_542_000_000,
    )

    assert item is not None
    assert item.canonical_url == url
```

- [ ] **Step 2: Run tests and confirm failure**

Run:

```bash
uv run pytest tests/unit/domains/news_intel/test_feed_item_normalizer.py -q
```

Expected: homepage test fails because current normalizer stores `https://tass.ru/`.

- [ ] **Step 3: Implement `_canonical_news_url_or_fallback()`**

Use the helper from File-Level Edits.

- [ ] **Step 4: Run normalizer tests**

Run:

```bash
uv run pytest tests/unit/domains/news_intel/test_feed_item_normalizer.py -q
```

Expected: all normalizer tests pass.

### Task 3: Material Identity Service

**Status:** Completed in current workspace; unit tests passed.

**Files:**
- Create: `src/parallax/domains/news_intel/services/news_material_identity.py`
- Create or modify: `tests/unit/domains/news_intel/test_news_material_identity.py`

- [ ] **Step 1: Write failing tests**

Add tests:

```python
from parallax.domains.news_intel.services.news_material_identity import (
    material_title_fingerprint,
    material_title_is_eligible,
    provider_symbol_set,
    symbol_sets_compatible,
)


def test_material_title_fingerprint_strips_known_source_prefix() -> None:
    assert material_title_fingerprint(
        "COINDESK: Live Markets: Bitcoin crashes to $62,000 as billions of longs get liquidated"
    ) == material_title_fingerprint(
        "Live Markets: Bitcoin crashes to $62,000 as billions of longs get liquidated"
    )


def test_material_title_fingerprint_strips_mixed_case_and_compact_source_prefixes() -> None:
    assert material_title_fingerprint("CoinDesk: Live Markets: Bitcoin crashes sharply again") == (
        material_title_fingerprint("Live Markets: Bitcoin crashes sharply again")
    )
    assert material_title_fingerprint("FINANCEFEEDS: Bessent urges lawmakers to pass crypto clarity act") == (
        material_title_fingerprint("Bessent urges lawmakers to pass crypto clarity act")
    )
    assert material_title_fingerprint("AFP: Fed leaves interest rates unchanged after meeting") == (
        material_title_fingerprint("Fed leaves interest rates unchanged after meeting")
    )


def test_material_title_fingerprint_keeps_non_source_prefix() -> None:
    assert material_title_fingerprint("SEC: New crypto policy expected") == "sec new crypto policy expected"


def test_material_title_requires_enough_tokens() -> None:
    assert material_title_is_eligible("bitcoin crashes to lows") is False
    assert material_title_is_eligible(
        "live markets bitcoin crashes to 62 000 as billions of longs get liquidated"
    ) is True


def test_symbol_sets_are_compatible_when_overlapping_or_missing() -> None:
    assert provider_symbol_set([{"symbol": "btc"}, {"symbol": "BILL"}]) == {"BTC", "BILL"}
    assert symbol_sets_compatible({"BTC"}, {"BTC", "ETH"}) is True
    assert symbol_sets_compatible({"SOL"}, {"BTC", "ETH"}) is False
    assert symbol_sets_compatible(set(), {"BTC"}) is True
```

- [ ] **Step 2: Run tests and confirm failure**

Run:

```bash
uv run pytest tests/unit/domains/news_intel/test_news_material_identity.py -q
```

Expected: import fails because file does not exist.

- [ ] **Step 3: Create service**

Implement the code shape from File-Level Edits.

- [ ] **Step 4: Run tests**

Run:

```bash
uv run pytest tests/unit/domains/news_intel/test_news_material_identity.py -q
```

Expected: all tests pass.

### Task 4: Storage Contract For Material Edges

**Status:** Completed in current workspace; schema tests passed.

**Files:**
- Create: `src/parallax/platform/db/alembic/versions/20260604_0148_news_material_duplicate_hard_cut.py`
- Modify: `tests/unit/test_postgres_schema.py`

- [ ] **Step 1: Write failing schema test**

Add assertion that `news_item_observation_edges_match_type_check` includes `same_material_title`.

```python
def test_news_observation_edges_allow_same_material_title_match_type(postgres_conn) -> None:
    definition = _constraint_definition(
        postgres_conn,
        "news_item_observation_edges",
        "news_item_observation_edges_match_type_check",
    )
    assert "same_material_title" in definition
```

- [ ] **Step 2: Run schema test and confirm failure**

Run:

```bash
uv run pytest tests/unit/test_postgres_schema.py -k same_material_title -q
```

Expected: fails because migration does not exist.

- [ ] **Step 3: Add Alembic migration**

Use the SQL from Storage / Migrations.

- [ ] **Step 4: Run schema test**

Run:

```bash
uv run pytest tests/unit/test_postgres_schema.py -k same_material_title -q
```

Expected: pass.

### Task 5: Repository Material Duplicate Merge

**Status:** Completed in current workspace; focused integration tests and code review passed.

**Files:**
- Modify: `src/parallax/domains/news_intel/repositories/news_repository.py`
- Modify: `tests/integration/domains/news_intel/test_news_repository.py`

- [ ] **Step 1: Write failing integration tests for both material arrival orders**

Add test:

```python
def test_opennews_missing_link_material_duplicate_attaches_to_existing_public_url_item(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repo = NewsRepository(conn)
        repo.upsert_source(
            source_id="opennews-news",
            provider_type="opennews",
            feed_url="opennews://news",
            source_domain="6551.io",
            source_name="OpenNews News",
            refresh_interval_seconds=60,
            now_ms=NOW_MS,
        )
        canonical_url = (
            "https://www.coindesk.com/tech/2026/06/03/"
            "live-markets-bitcoin-crashes-to-usd62-000-as-billions-of-longs-get-liquidated"
        )
        public_provider = repo.upsert_provider_item(
            source_id="opennews-news",
            fetch_run_id=repo.start_fetch_run(source_id="opennews-news", started_at_ms=NOW_MS),
            source_item_key="2514740",
            canonical_url=canonical_url,
            payload_hash="payload-public",
            raw_payload_json={"id": "2514740", "link": canonical_url},
            fetched_at_ms=NOW_MS,
            provider_article_id="2514740",
        )
        public_news = repo.upsert_canonical_news_item(
            provider_item_id=public_provider["provider_item_id"],
            canonical_url=canonical_url,
            title="Live Markets: Bitcoin crashes to $62,000 as billions of longs get liquidated",
            summary="",
            body_text="Live Markets: Bitcoin crashes to $62,000 as billions of longs get liquidated",
            language="en",
            published_at_ms=NOW_MS,
            fetched_at_ms=NOW_MS,
            content_hash="hash-public",
            title_fingerprint="live markets bitcoin crashes to 62 000 as billions of longs get liquidated",
            now_ms=NOW_MS,
            provider_token_impacts=[{"symbol": "BTC", "signal": "short", "score": 85}],
        )
        fallback_provider = repo.upsert_provider_item(
            source_id="opennews-news",
            fetch_run_id=repo.start_fetch_run(source_id="opennews-news", started_at_ms=NOW_MS + 1),
            source_item_key="2514742",
            canonical_url="opennews://item/2514742",
            payload_hash="payload-fallback",
            raw_payload_json={"id": "2514742", "link": ""},
            fetched_at_ms=NOW_MS + 1,
            provider_article_id="2514742",
        )
        fallback_news = repo.upsert_canonical_news_item(
            provider_item_id=fallback_provider["provider_item_id"],
            canonical_url="opennews://item/2514742",
            title="COINDESK: Live Markets: Bitcoin crashes to $62,000 as billions of longs get liquidated",
            summary="",
            body_text="COINDESK: Live Markets: Bitcoin crashes to $62,000 as billions of longs get liquidated",
            language="en",
            published_at_ms=NOW_MS + 1,
            fetched_at_ms=NOW_MS + 1,
            content_hash="hash-fallback",
            title_fingerprint="coindesk live markets bitcoin crashes to 62 000 as billions of longs get liquidated",
            now_ms=NOW_MS + 1,
            provider_token_impacts=[{"symbol": "BTC", "signal": "short", "score": 85}],
        )
        edges = conn.execute(
            "SELECT provider_article_key, news_item_id, match_type FROM news_item_observation_edges ORDER BY provider_article_key"
        ).fetchall()
        item_count = conn.execute("SELECT COUNT(*) AS count FROM news_items").fetchone()["count"]
        stored = conn.execute("SELECT * FROM news_items WHERE news_item_id = %s", (public_news["news_item_id"],)).fetchone()
    finally:
        conn.close()

    assert fallback_news["news_item_id"] == public_news["news_item_id"]
    assert item_count == 1
    assert stored["duplicate_observation_count"] == 2
    assert [dict(row) for row in edges] == [
        {"provider_article_key": "opennews:2514740", "news_item_id": public_news["news_item_id"], "match_type": "same_canonical_url"},
        {"provider_article_key": "opennews:2514742", "news_item_id": public_news["news_item_id"], "match_type": "same_material_title"},
    ]


def test_opennews_public_url_later_remaps_existing_material_duplicate_item(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repo = NewsRepository(conn)
        repo.upsert_source(
            source_id="opennews-news",
            provider_type="opennews",
            feed_url="opennews://news",
            source_domain="6551.io",
            source_name="OpenNews News",
            refresh_interval_seconds=60,
            now_ms=NOW_MS,
        )
        fallback_provider = repo.upsert_provider_item(
            source_id="opennews-news",
            fetch_run_id=repo.start_fetch_run(source_id="opennews-news", started_at_ms=NOW_MS),
            source_item_key="2514742",
            canonical_url="opennews://item/2514742",
            payload_hash="payload-fallback",
            raw_payload_json={"id": "2514742", "link": ""},
            fetched_at_ms=NOW_MS,
            provider_article_id="2514742",
        )
        fallback_news = repo.upsert_canonical_news_item(
            provider_item_id=fallback_provider["provider_item_id"],
            canonical_url="opennews://item/2514742",
            title="COINDESK: Live Markets: Bitcoin crashes to $62,000 as billions of longs get liquidated",
            summary="",
            body_text="COINDESK: Live Markets: Bitcoin crashes to $62,000 as billions of longs get liquidated",
            language="en",
            published_at_ms=NOW_MS,
            fetched_at_ms=NOW_MS,
            content_hash="hash-fallback",
            title_fingerprint="coindesk live markets bitcoin crashes to 62 000 as billions of longs get liquidated",
            now_ms=NOW_MS,
            provider_token_impacts=[{"symbol": "BTC", "signal": "short", "score": 85}],
        )
        canonical_url = (
            "https://www.coindesk.com/tech/2026/06/03/"
            "live-markets-bitcoin-crashes-to-usd62-000-as-billions-of-longs-get-liquidated"
        )
        public_provider = repo.upsert_provider_item(
            source_id="opennews-news",
            fetch_run_id=repo.start_fetch_run(source_id="opennews-news", started_at_ms=NOW_MS + 1),
            source_item_key="2514740",
            canonical_url=canonical_url,
            payload_hash="payload-public",
            raw_payload_json={"id": "2514740", "link": canonical_url},
            fetched_at_ms=NOW_MS + 1,
            provider_article_id="2514740",
        )
        public_news = repo.upsert_canonical_news_item(
            provider_item_id=public_provider["provider_item_id"],
            canonical_url=canonical_url,
            title="Live Markets: Bitcoin crashes to $62,000 as billions of longs get liquidated",
            summary="",
            body_text="Live Markets: Bitcoin crashes to $62,000 as billions of longs get liquidated",
            language="en",
            published_at_ms=NOW_MS + 1,
            fetched_at_ms=NOW_MS + 1,
            content_hash="hash-public",
            title_fingerprint="live markets bitcoin crashes to 62 000 as billions of longs get liquidated",
            now_ms=NOW_MS + 1,
            provider_token_impacts=[{"symbol": "BTC", "signal": "short", "score": 85}],
        )
        edges = conn.execute(
            "SELECT provider_article_key, news_item_id, match_type FROM news_item_observation_edges ORDER BY provider_article_key"
        ).fetchall()
        item_count = conn.execute("SELECT COUNT(*) AS count FROM news_items").fetchone()["count"]
    finally:
        conn.close()

    assert public_news["news_item_id"] != fallback_news["news_item_id"]
    assert item_count == 1
    assert [dict(row) for row in edges] == [
        {"provider_article_key": "opennews:2514740", "news_item_id": public_news["news_item_id"], "match_type": "same_canonical_url"},
        {"provider_article_key": "opennews:2514742", "news_item_id": public_news["news_item_id"], "match_type": "same_material_title"},
    ]
```

- [ ] **Step 2: Run test and confirm failure**

Run:

```bash
uv run pytest tests/integration/domains/news_intel/test_news_repository.py::test_opennews_missing_link_material_duplicate_attaches_to_existing_public_url_item -q
```

Expected: fails with two `news_items` rows.

- [ ] **Step 3: Implement repository material duplicate helper**

Implement `_material_duplicate_identity_for_observation()`, material group advisory locking, fallback-first/public-later remap, stale dirty-target cleanup, and agent audit preservation. Call the material helper before provider article reuse and before the final canonical item key advisory lock.

- [ ] **Step 4: Run repository tests**

Run:

```bash
uv run pytest tests/integration/domains/news_intel/test_news_repository.py -k 'material_duplicate or public_url_later or single_segment_public_url_collapses or opennews_article_id_collapses' -q
```

Expected: all selected tests pass.

### Task 6: Hard-Cut Repair Command

**Status:** Completed in current workspace; subagent review issue fixed and focused tests pass.

**Files:**
- Create: `src/parallax/domains/news_intel/services/news_duplicate_hard_cut_repair.py`
- Modify: `src/parallax/app/surfaces/cli/parser.py`
- Modify: `src/parallax/app/surfaces/cli/commands/ops.py`
- Modify: `tests/unit/test_cli.py`
- Modify: `tests/integration/domains/news_intel/test_news_duplicate_hard_cut_repair.py`

- [x] **Step 1: Write CLI registration test**

Add:

```python
def test_ops_repair_news_duplicates_hard_cut_is_registered_without_compat_flags() -> None:
    parser = build_parser()

    dry_run = parser.parse_args(["ops", "repair-news-duplicates-hard-cut", "--dry-run"])
    execute = parser.parse_args(["ops", "repair-news-duplicates-hard-cut", "--execute", "--limit", "100"])

    assert dry_run.ops_command == "repair-news-duplicates-hard-cut"
    assert dry_run.dry_run is True
    assert execute.execute is True
    assert execute.limit == 100
```

- [x] **Step 2: Write repair integration test**

Seed:
- one public URL duplicate group;
- one homepage generic URL item;
- one OpenNews missing-link material duplicate group.

Assert after `execute=True`:
- hard URL group has one `news_items` row;
- generic homepage canonical URL is rewritten to `opennews://item/{provider_article_id}`;
- material duplicate edges point to one item;
- zero-edge duplicate items are deleted;
- old page and brief dirty targets are deleted or terminalized;
- page and brief dirty targets are enqueued only for surviving representative ids;
- agent run audit rows are preserved or remapped before zero-edge delete;
- worker/lease guard prevents execute-mode repair while News workers are active.

- [x] **Step 3: Run tests and confirm failure**

Run:

```bash
uv run pytest tests/unit/test_cli.py::test_ops_repair_news_duplicates_hard_cut_is_registered_without_compat_flags tests/integration/domains/news_intel/test_news_duplicate_hard_cut_repair.py -q
```

Expected: fails because command/service do not exist.

- [x] **Step 4: Implement repair service and CLI wiring**

Use the File-Level Edits counter contract exactly, including stale dirty target and audit remap counters.

- [x] **Step 5: Run tests**

Run:

```bash
uv run pytest tests/unit/test_cli.py::test_ops_repair_news_duplicates_hard_cut_is_registered_without_compat_flags tests/integration/domains/news_intel/test_news_duplicate_hard_cut_repair.py -q
```

Expected: pass.

Verified:

```bash
uv run pytest tests/unit/domains/news_intel/test_news_duplicate_hard_cut_repair_unit.py tests/integration/domains/news_intel/test_news_duplicate_hard_cut_repair.py tests/unit/test_cli.py -q -k 'repair_news_duplicates or news_duplicate_hard_cut_repair or news_dedup'
```

Result: `11 passed, 6 deselected`.

### Task 7: Diagnostics Become The Gate

**Status:** Completed in current workspace; current-policy gates added and focused diagnostics tests pass.

**Files:**
- Modify: `src/parallax/domains/news_intel/repositories/news_repository.py`
- Modify: `tests/integration/domains/news_intel/test_news_repository.py`

- [x] **Step 1: Write diagnostics test**

Add:

```python
def test_news_dedup_diagnostics_reports_current_policy_duplicate_gates(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repo = NewsRepository(conn)
        # Seed one repaired state with no hard URL, generic URL, or material duplicate risk.
        diagnostics = repo.news_dedup_diagnostics(window_ms=8 * 3_600_000, score_threshold=80, now_ms=NOW_MS)
    finally:
        conn.close()

    assert diagnostics["hard_public_url_visible_duplicate_excess"] == 0
    assert diagnostics["generic_public_url_visible_rows"] == 0
    assert diagnostics["material_title_visible_duplicate_excess"] == 0
    assert diagnostics["top_visible_canonical_duplicate_groups"] == []
```

- [x] **Step 2: Run test and confirm failure**

Run:

```bash
uv run pytest tests/integration/domains/news_intel/test_news_repository.py::test_news_dedup_diagnostics_reports_current_policy_duplicate_gates -q
```

Expected: fails because diagnostics fields do not exist.

- [x] **Step 3: Add diagnostics fields**

Use current policy, not historical URL classification. Count enabled serving rows plus fact-layer material groups, stale duplicate current briefs, and stale duplicate dirty targets.

- [x] **Step 4: Run diagnostics tests**

Run:

```bash
uv run pytest tests/integration/domains/news_intel/test_news_repository.py -k 'dedup_diagnostics' -q
```

Expected: pass.

Verified:

```bash
uv run pytest tests/integration/domains/news_intel/test_news_repository.py -k 'dedup_diagnostics' -q
```

Result: `3 passed, 63 deselected`.

### Task 8: Agent Brief And Page Projection No-Duplicate Guardrails

**Status:** Completed in current workspace; projection enqueue guardrail and focused tests pass.

**Files:**
- Modify: `tests/integration/domains/news_intel/test_news_item_agent_brief_repository.py`
- Modify: `tests/integration/domains/news_intel/test_news_page_rows_read_path.py`

- [x] **Step 1: Add page projection test**

Assert one page row for the three-observation Coindesk case:

```python
def test_page_projection_outputs_one_row_for_public_url_and_material_duplicate() -> None:
    # Seed canonical URL observation plus OpenNews missing-link material duplicate.
    # Run page projection loader and replace rows.
    rows = query.list_news_page_rows(limit=20)

    assert [row["canonical_url"] for row in rows].count(coindesk_url) == 1
    assert rows[0]["duplicate_count"] == 3
    assert rows[0]["provider_article_keys_json"] == [
        "opennews:2514740",
        "opennews:2514742",
        "opennews:2514744",
    ]
```

- [x] **Step 2: Add brief admission test**

Assert duplicate material observation does not create a second current brief target:

```python
def test_material_duplicate_observation_reuses_current_brief_target() -> None:
    # Seed processed representative and material duplicate edge.
    # Enqueue brief_input through process/repair path.
    targets = repo.news_projection_dirty_targets.list_pending_targets(projection_name="brief_input")

    assert {target["target_id"] for target in targets} == {representative_news_item_id}
```

- [x] **Step 3: Run tests and confirm failure if repository fix is absent**

Run:

```bash
uv run pytest tests/integration/domains/news_intel/test_news_item_agent_brief_repository.py tests/integration/domains/news_intel/test_news_page_rows_read_path.py -k 'material_duplicate or duplicate_observation' -q
```

Expected before Task 5: failure or missing tests. Expected after Task 5: pass.

Verified:

```bash
uv run pytest tests/integration/domains/news_intel/test_news_item_agent_brief_repository.py tests/integration/domains/news_intel/test_news_page_rows_read_path.py -k 'material_duplicate or duplicate_observation' -q
```

Result: `2 passed, 14 deselected`.

### Task 9: Documentation Hard Cut

**Status:** Completed in current workspace; architecture/workers wording updated and CLI help regenerated with the repair command.

**Files:**
- Modify: `src/parallax/domains/news_intel/ARCHITECTURE.md`
- Modify: `docs/WORKERS.md`
- Modify: `docs/generated/cli-help.md` after CLI help regeneration

- [x] **Step 1: Update architecture wording**

Replace the public URL paragraph with:

```markdown
Public `http://` and `https://` URLs admitted by `public_url_identity_policy`
are the hard identity for `news_items`. Homepage, aggregator, live page, feed,
preview, and generic announcement URLs are provider/raw evidence only and must
not become serving canonical URLs. `url_identity_kind` is diagnostic context,
not a storage dedup gate. OpenNews missing-link observations may attach to an
existing canonical item only through bounded deterministic material identity.
```

- [x] **Step 2: Regenerate CLI help**

Run:

```bash
uv run parallax --help > docs/generated/cli-help.md
```

Expected: CLI help includes `repair-news-duplicates-hard-cut`.

Verified:

```bash
uv run python scripts/regen_cli_help.py
rg -n "repair-news-duplicates-hard-cut|news-dedup-diagnostics" docs/generated/cli-help.md
```

Result: `repair-news-duplicates-hard-cut` appears in the generated `ops` help. The regen command emitted LiteLLM optional Bedrock/SageMaker `botocore` preload warnings only.

### Task 10: Full Verification And Rollout

**Status:** Partially completed in current workspace; code-level target tests, lint/format, config path check, CLI help, and subagent reviews passed. Full `make check-all`, Docker rebuild/migration/repair, restart, and production diagnostics remain deferred rollout steps. Verification artefact: `docs/superpowers/plans/active/2026-06-04-news-duplicate-hard-cut-optimization-verification-cn.md`.

**Files:**
- Create after implementation: `docs/superpowers/plans/active/2026-06-04-news-duplicate-hard-cut-optimization-verification-cn.md`

- [x] **Step 1: Confirm real-data config paths before any live repair**

```bash
uv run parallax config
```

Expected: output reports `config_path` and `workers_config_path` under `~/.parallax/`. Report only paths and redacted booleans; do not print secret values.

- [x] **Step 2: Run target tests**

```bash
uv run pytest \
  tests/unit/domains/news_intel/test_news_url_identity.py \
  tests/unit/domains/news_intel/test_feed_item_normalizer.py \
  tests/unit/domains/news_intel/test_news_material_identity.py \
  tests/unit/domains/news_intel/test_news_canonical_identity.py \
  tests/integration/domains/news_intel/test_news_repository.py \
  tests/integration/domains/news_intel/test_news_duplicate_hard_cut_repair.py \
  -q
```

Expected: all pass.

- [x] **Step 3: Run lint**

```bash
uv run ruff check \
  src/parallax/domains/news_intel/services/news_url_identity.py \
  src/parallax/domains/news_intel/services/feed_item_normalizer.py \
  src/parallax/domains/news_intel/services/news_material_identity.py \
  src/parallax/domains/news_intel/services/news_duplicate_hard_cut_repair.py \
  src/parallax/domains/news_intel/repositories/news_repository.py \
  src/parallax/app/surfaces/cli/parser.py \
  src/parallax/app/surfaces/cli/commands/ops.py \
  tests/unit/domains/news_intel/test_news_url_identity.py \
  tests/unit/domains/news_intel/test_feed_item_normalizer.py \
  tests/unit/domains/news_intel/test_news_material_identity.py \
  tests/integration/domains/news_intel/test_news_repository.py \
  tests/integration/domains/news_intel/test_news_duplicate_hard_cut_repair.py
```

Expected: `All checks passed!`

- [ ] **Step 4: Run full gate**

```bash
make check-all
```

Expected: exit code 0. Paste full output into verification artefact.

- [ ] **Step 5: Apply migration and dry-run repair in local Docker**

```bash
docker compose build migrate app
docker compose run --rm migrate
docker compose run --rm --no-deps app parallax ops repair-news-duplicates-hard-cut --dry-run
```

Expected dry-run JSON includes non-negative counters and no secret values.

- [ ] **Step 6: Execute repair and restart**

```bash
docker compose stop app
docker compose run --rm --no-deps app parallax ops repair-news-duplicates-hard-cut --execute
docker compose up -d app
curl -fsS http://127.0.0.1:8765/healthz
```

Expected: repair JSON reports counters, app starts healthy, `/healthz` returns `ok`.

- [ ] **Step 7: Run production diagnostics**

```bash
docker compose run --rm --no-deps app parallax ops news-dedup-diagnostics --window-hours 8 --score-threshold 80
```

Expected fields:

```json
{
  "hard_public_url_visible_duplicate_excess": 0,
  "generic_public_url_visible_rows": 0,
  "material_title_visible_duplicate_excess": 0,
  "fact_layer_material_duplicate_excess": 0,
  "stale_duplicate_brief_rows": 0,
  "stale_duplicate_dirty_targets": 0,
  "top_visible_canonical_duplicate_groups": []
}
```

## PR Breakdown

1. **PR 1 — URL policy and generic URL hygiene**: Tasks 1-2, unit tests only, no storage change except incoming normalization behaviour.
2. **PR 2 — Material duplicate runtime and migration**: Tasks 3-5, includes Alembic migration and repository integration tests.
3. **PR 3 — Repair command and diagnostics gate**: Tasks 6-8, includes idempotent ops repair and acceptance diagnostics.
4. **PR 4 — Docs and verification**: Tasks 9-10, records final command output and rollout evidence.

If the team prefers one hard-cut PR, keep the same task order and still run every verification command before merge.

## Rollout Order

1. Run `uv run parallax config` and confirm `~/.parallax/` config/workers paths with secrets redacted.
2. Stop `app` workers before executing repair.
3. Apply migration to add `same_material_title` edge support and material lookup index.
4. Deploy code with URL policy, material merge, repair command, and diagnostics.
5. Run `repair-news-duplicates-hard-cut --dry-run`.
6. Run `repair-news-duplicates-hard-cut --execute`; command must fail if News workers/leases are active.
7. Start `app`.
8. Wait for `news_page_projection` to drain dirty targets.
9. Run `news-dedup-diagnostics --window-hours 8 --score-threshold 80`.
10. Confirm `/api/news` and the News UI show one row for Coindesk live / FinanceFeeds examples.

## Rollback

- Migration rollback: drop/recreate the match type check without `same_material_title` only if no rows use it. If rows use it, rollback is not safe without deleting repaired edges; prefer forward fix.
- Runtime rollback: redeploy previous image only after stopping `app`; however repaired canonical facts remain current-policy data and should not be "unrepaired".
- Repair rollback: no blind revert. Provider raw payloads remain in `news_provider_items`; if a repair bug is found, run a forward repair that remaps affected edges and re-enqueues page/brief targets.
- UI rollback is irrelevant because UI is not the root fix.

## Acceptance Criteria

- AC1. WHEN OpenNews emits two different ids with the same admitted public URL, THEN `news_items` has one row and `news_item_observation_edges` has two edges.
- AC2. WHEN OpenNews emits a generic homepage/source URL such as `https://tass.ru/`, THEN the normalized observation canonical URL is `opennews://item/{provider_article_id}`, not the homepage URL.
- AC3. WHEN OpenNews emits a live-page URL, THEN `public_url_identity_policy()` blocks hard URL identity with `blocked_reason='live_page'`.
- AC4. WHEN OpenNews emits a missing-link prefixed duplicate such as `COINDESK: Live Markets: Bitcoin crashes to $62,000 as billions of longs get liquidated`, THEN it attaches to the existing canonical item with `match_type='same_material_title'`.
- AC5. WHEN the same material duplicate arrives fallback-first and public-url-later, THEN the existing fallback edges remap to the public canonical item and only one `news_items` row remains.
- AC6. WHEN two equivalent material fallback observations ingest concurrently, THEN deterministic material advisory locking prevents two surviving canonical items.
- AC7. WHEN page projection runs after repair, THEN `/api/news` has one public row for the canonical item and `duplicate_count` includes all remapped observations.
- AC8. WHEN `news-dedup-diagnostics --window-hours 8 --score-threshold 80` runs after repair, THEN hard URL duplicate excess, generic public URL rows, material title duplicate excess, stale duplicate brief rows, and stale duplicate dirty targets are all zero.
- AC9. WHEN a duplicate observation remaps to an existing item, THEN no second current agent brief or stale `brief_input` target remains for the duplicate item.
- AC10. WHEN zero-edge duplicate items are deleted, THEN agent run audit rows are preserved or remapped according to the repair counters and no audit row disappears silently by cascade.

## Risks

| Risk | Severity | Mitigation |
|------|----------|------------|
| False merge of different same-title OpenNews alerts | High | Restrict material merge to same source, +/-10 minutes, eligible title length, compatible token symbols, and prefer existing canonical URL item. |
| Losing homepage link visibility | Low | Homepage/generic link stays in raw payload and observation evidence; it is removed only as serving canonical URL. |
| Repair deletes useful derived rows | Medium | Delete/rebuild only derived rows for remapped/zero-edge items; provider observations remain. |
| Diagnostics still report title duplicates outside policy | Medium | Current acceptance gates use policy-specific counters; old broad title diagnostics remain advisory. |
| Migration applied before code | Low | `same_material_title` only expands allowed edge values; old code does not emit it. |

## Self-Review Checklist

- [ ] No task introduces feature flags or legacy compatibility branches.
- [ ] No task hides duplicates in React or API filtering as root fix.
- [ ] Every storage mutation preserves provider raw payload evidence.
- [ ] Every duplicate class has a failing test before implementation.
- [ ] Final diagnostics define objective zero-duplicate gates.
