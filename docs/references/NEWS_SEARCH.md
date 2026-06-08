# News Search

> **Scope.** Defines the simple end-to-end contract for searching the News
> page. News search is a News Intel read-model query. It is not global token
> search, not a resolver entry point, and not a provider fetch trigger.

## Problem

The News page has two search-looking controls:

- the shell topbar search
- the News route's own filter input

On `/news`, both must mean the same thing: filter the News tape. They must not
route to `/search`, call `/api/search/inspect`, or resolve a token case.

Real-data checks exposed two separate issues:

- `q=zec` returns time-ordered News rows, but `next_cursor` is returned even
  when no next page exists, so the UI can navigate to an empty page.
- The UI says users can search by source, but the backend currently searches
  headline, summary, and token lanes only.

## KISS Contract

Keep the chain narrow and boring:

```text
Topbar on /news or News filter input
  -> /news?q=<query>
  -> useNewsPageWithToken({ q, cursor, filters })
  -> GET /api/news?q=<query>&cursor=<cursor>&...
  -> news_page_rows
  -> rows sorted by latest_at_ms DESC, row_id DESC
```

There is no fallback path:

- no `/api/search/inspect`
- no Token Intel resolver
- no provider call
- no raw `news_items` fallback
- no frontend recomputation of ranking, narrative, or identity
- no compatibility branch for retired search behavior

## Route Behavior

`/news` owns shareable News query state.

- `q` lives in the URL.
- Typing in the News filter updates `q`.
- Submitting the shell topbar while on `/news` or `/news/items/:newsItemId`
  navigates to `/news?q=<submitted-query>`.
- Changing `q`, signal, score, or status resets pagination to page 1.
- Leaving `/news` restores the normal global topbar behavior.

The topbar label and placeholder must reflect the active route:

- News route: `news search`, "search news / source / token"
- Other routes: `global search`, token / handle / contract-address search

## API Behavior

`GET /api/news` is read-only.

Accepted filters:

- `q`
- `cursor`
- `limit`
- `signal`
- `min_score`
- `status`

Response ordering is always:

```text
latest_at_ms DESC, row_id DESC
```

Cursor identity is:

```text
<latest_at_ms>:<row_id>
```

Pagination uses `limit + 1` internally:

- fetch one extra row
- return at most `limit` rows
- set `next_cursor` only when the extra row exists
- set `next_cursor: null` at the true end

This makes `next_cursor` mean "there is another page", not "this page has a
last row".

## Search Document

The read model should expose one deterministic search document per
`news_page_rows` row.

Recommended field:

```text
news_page_rows.search_text
```

Optional indexed companion:

```text
news_page_rows.search_tsv
```

Build `search_text` during News page projection from fields already present in
the projected row:

- headline
- summary
- source domain
- source provider/type/id when projected
- token lane symbols and target ids
- token lane resolution status
- fact lane event type/status/text labels

Do not include noisy full URLs, raw provider frames, prompts, agent execution
state, or transient runtime fields.

The repository search predicate should query this document only. It should not
keep the old scattered predicate over `headline`, `summary`, and
`token_lanes_json::text`.

## Source Search

If the UI says "source", source search must be real.

Examples that should match when projected rows contain those values:

- `6551.io`
- `opennews`
- source ids or compact source names, if those are projected

If a value is not in `search_text`, the UI must not promise it.

## Token-Like Queries

News search accepts token-like text such as `zec`, `upbit`, or `spacex`, but it
does not resolve the query as a token.

The query only matches News rows whose projected search document contains that
text. Token lanes may be shown as evidence attached to the News row, but they
do not change the route into Token Case or Search Intel.

Examples:

- `zec` should show ZEC-related News rows by time.
- `upbit` should show Upbit listing or exchange News rows by time.
- `spacex` should show SpaceX News rows by time, even if a provider also
  attached token lanes named `SPACEX` or `SPCX`.

## Tests

Backend tests should prove:

- `/api/news?q=zec&limit=5` returns the first 5 rows and a cursor when a 6th
  exists.
- The next cursor returns the 6th row and `next_cursor: null`.
- `/api/news?q=zec&limit=100` returns all current matching rows and
  `next_cursor: null`.
- Source queries match source fields included in `search_text`.
- News search does not call Token Intel search or resolver services.

Frontend tests should prove:

- topbar search on `/news` calls `/api/news?q=...`
- topbar search on `/news` never calls `/api/search/inspect`
- `/news?q=zec` hydrates the News filter input
- Next is disabled when `next_cursor` is null
- changing `q` resets page state

Browser verification should check:

- `/news?q=zec`
- `/news?q=upbit`
- `/news?q=spacex`
- a source query such as `/news?q=6551.io`

For each query, confirm sorted rows, correct empty state, and no
`/api/search/inspect` request.

## Implementation Order

1. Add failing backend tests for true `next_cursor` semantics.
2. Add failing backend tests for source and token-like News search.
3. Add `search_text` and optional `search_tsv` to `news_page_rows`.
4. Populate `search_text` in the News page projection.
5. Replace the repository `q` predicate with the new search document predicate.
6. Change API pagination to `limit + 1`.
7. Update frontend tests for route-scoped search and terminal pagination.
8. Run backend, frontend, and browser verification gates.

## Non-Goals

- Do not add fuzzy token resolution to News search.
- Do not fetch providers during search.
- Do not expose raw News items as fallback rows.
- Do not add old behavior compatibility code.
- Do not reorder News rows by search rank.
- Do not duplicate search business logic in the frontend.
