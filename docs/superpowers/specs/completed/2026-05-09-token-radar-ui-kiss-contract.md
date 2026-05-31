# Spec - Token Radar UI KISS Contract

**Status**: Approved
**Date**: 2026-05-09
**Owner**: Codex
**Related**: `docs/superpowers/plans/2026-05-09-token-radar-ui-kiss-contract.md`

## Background

The backend already owns the current token radar projection version. `src/parallax/pipeline/token_radar_contract.py:3` defines the projection name and `src/parallax/pipeline/token_radar_contract.py:4` defines the current projection version. `src/parallax/retrieval/asset_flow_service.py:28` queries only that current version through `TokenRadarRepository.latest_rows`, and `src/parallax/retrieval/asset_flow_service.py:40` returns projection metadata in the public response. The repository uses projection version for storage selection and current-window reads in `src/parallax/storage/token_radar_repository.py:86`.

The web client currently duplicates an internal backend version string in `web/src/App.tsx:63`, then drops all token radar rows when `data.projection.version` differs in `web/src/App.tsx:1109`. This means an internal projection bump can make the UI display zero rows even when `/api/token-radar` returns fresh `targets` and `attention`.

## Problem

Token Radar should not disappear in the web UI because the backend projection version changed. The user-facing API boundary is `/api/token-radar`; the frontend should render the current API payload if the row shape is valid. Hard-coding `token-radar-v6-*` or `token-radar-v7-*` in web code adds accidental compatibility logic and creates false empty states.

## First Principles

- The backend owns projection selection. `AssetFlowService` already asks storage for `TOKEN_RADAR_PROJECTION_VERSION`, so the web client receives one current semantic payload, not a multi-version history.
- The UI owns presentation and row-shape validation. `tokenRadarRowToTokenItem` already validates required row fields, score blocks, and market fields before rendering.
- Version metadata is useful for operations and offline evaluation, but it is not a user-facing render contract.

## Goals

- G1. When `/api/token-radar` returns rows with any projection version string, the web UI renders those rows if their required semantic fields are valid.
- G2. The web bundle contains no hard-coded `token-radar-v6-*` or `token-radar-v7-*` strings.
- G3. Existing backend projection versioning remains unchanged for storage, ops, and API metadata.

## Non-Goals

- N1. Do not remove `projection_version` from PostgreSQL tables, repository queries, projection offsets, or API metadata.
- N2. Do not introduce a frontend compatibility matrix or a version translation layer.
- N3. Do not change token extraction, intent resolution, or token radar scoring.

## Target Architecture

The backend continues to publish `/api/token-radar` with `projection.version` as informational metadata. The frontend treats `projection.version` as display/debug metadata only. Token Radar rendering depends on the presence of API data and the row-level semantic contract already enforced by the converter.

## Conceptual Data Flow

```
projection worker -> token_radar_rows -> AssetFlowService -> /api/token-radar -> web row converter -> TokenRadarTable
```

Only the final web arrow changes: the row converter stops rejecting payloads by backend projection version. It continues to reject malformed rows through required field checks.

## Core Models

- Projection metadata: `status`, `version`, `source`, `source_max_received_at_ms`, `computed_at_ms`. Informational for UI; authoritative for backend operations.
- Token radar row: semantic presentation payload containing `intent`, `target`, `attention`, `resolution`, `price`, `score`, `decision`, `data_health`, and `source_event_ids`. This is the UI render contract.

## Interface Contracts

`GET /api/token-radar` remains unchanged. The web client accepts the endpoint's current response regardless of the exact `projection.version` string. If rows are empty, the UI shows the existing empty state. If rows are malformed, the existing converter error path remains the guardrail.

## Acceptance Criteria

- AC1. WHEN the mocked `/api/token-radar` response uses a new projection version and includes a valid row THEN the web UI SHALL render that token row.
- AC2. WHEN searching web source for `token-radar-v6` or `token-radar-v7` THEN no web production code SHALL contain those strings.
- AC3. WHEN backend tests inspect `projection.version` THEN they SHALL still see `TOKEN_RADAR_PROJECTION_VERSION` from the backend contract.

## Risks

| Risk | Severity | Mitigation |
|------|----------|------------|
| UI renders a payload whose backend shape changed incompatibly. | Medium | Keep row-level required-field validation in `tokenRadarRowToTokenItem`. |
| Removing the frontend gate hides backend migration mistakes. | Low | Backend still exposes projection metadata and ops status; UI should not be the migration guard. |
| Test fixtures continue to encode old versions and reintroduce coupling. | Medium | Update fixtures to use a deliberately arbitrary version in the regression test. |

## Evolution Path

If the API needs a breaking frontend contract in the future, add an explicit semantic field such as `schema: "token-radar-row-v1"` to the API and test the field shape. Do not use backend projection version strings as UI compatibility gates.

## Alternatives Considered

- Update the web constant from v6 to v7. Rejected because it preserves the root coupling and will break again on the next backend projection bump.
- Keep a list of accepted frontend versions. Rejected because it creates a compatibility matrix without a real multi-version UI requirement.
- Remove backend projection versioning entirely. Rejected because storage isolation and projection audit still need version metadata.

## Boundaries

| Class | Behaviour |
|-------|-----------|
| Always | Render valid `/api/token-radar` rows independent of backend projection version string. |
| Ask first | Introduce a new explicit API schema/version field for frontend compatibility. |
| Never | Hard-code backend projection version strings in web rendering logic. |
