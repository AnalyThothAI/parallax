# Token Image Local Mirror Hard Cut Verification

## Scope

This verifies the hard cut from provider-hosted token image URLs and the old
`/api/token-image?url=...` proxy to local mirrored token image assets.

## Expected Runtime Chain

```text
asset_profiles / exact token evidence / cex_token_profiles provider logo URLs
  -> token_image_mirror
  -> token_image_assets + ~/.gmgn-twitter-intel/cache/token-images/*
  -> token_profile_current.logo_url
  -> /api/token-images/{image_id}
  -> frontend img src
```

`profile.identity.logo_url` is valid only when it is `null` or starts with
`/api/token-images/`. Provider URLs such as GMGN `external-res` remain source
provenance and mirror inputs, not public image URLs.

## Commands Run

```bash
uv run pytest tests/unit/test_token_profile_current_projection.py tests/unit/test_token_profile_current_repository.py tests/unit/test_token_profile_source_query.py tests/unit/test_token_profile_read_model.py tests/unit/test_token_profile_current_worker.py
uv run pytest tests/unit/test_token_image_mirror.py tests/integration/test_token_image_source_query.py
uv run pytest tests/unit/test_token_image_mirror_worker.py tests/architecture/test_worker_runtime_contracts.py tests/unit/test_worker_settings.py tests/unit/test_bootstrap_worker_runtime_wiring.py tests/integration/test_cli.py tests/unit/test_cli.py
uv run pytest tests/integration/test_api_http.py tests/architecture/test_project_structure.py -q
uv run pytest tests/architecture/test_project_structure.py tests/architecture/test_token_profile_current_hard_cut.py tests/architecture/test_worker_inventory_contract.py -q
uv run pytest tests/architecture
uv run ruff check .
cd web && npm run typecheck
cd web && npm run lint
cd web && npm run build
cd web && npm run test -- --run tests/component/shared/ui/TokenProfileCard.test.tsx tests/component/features/live/ui/TokenRadarTable.test.tsx tests/unit/features/token-case/model/buildTokenCaseViewModel.test.ts tests/unit/shared/model/tokenRadarCompactCase.test.ts tests/unit/lib/tokenRadar.test.ts
cd web && npm run test -- --run tests/architecture
```

## Passing Focused Gates

- Token image asset storage, mirror service, source query, profile projection,
  read model, API route, and frontend focused tests passed.
- Frontend `typecheck`, `lint`, and production `build` passed.
- The removed route file `routes_token_image.py` is absent.
- The removed frontend helper `web/src/shared/model/tokenImageUrl.ts` is
  absent.
- Runtime profile reads null stale remote `https://...` logo rows before they
  reach public payloads.
- Image-related architecture gates passed:
  `test_project_structure.py`, `test_token_profile_current_hard_cut.py`,
  `test_worker_inventory_contract.py`, and all frontend architecture tests.

## Known Unrelated Baseline Failures

- `tests/integration/test_api_http.py tests/architecture/test_project_structure.py`
  has two existing Signal Pulse failures unrelated to token images:
  `visibility: public` is present in the empty contract response, and
  `status=token_watch` returns `400` instead of the historical expected `200`.
- The broader worker settings command has existing agent-runtime default model
  expectation failures unrelated to token image mirroring.
- Full frontend `npm run test` has existing route-test failures in watchlist
  and live-radar WebSocket/MSW setup unrelated to token image rendering.
- Full `uv run pytest tests/architecture` has existing failures unrelated to
  token images in Pulse/Agent/Narrative architecture boundaries: concrete model
  token strings in Pulse cost guard, a cross-domain token_intel constant import,
  narrative repository/query upward imports, raw SQL inside Pulse services, and
  an OpenAI integration importing a Pulse service.

## Live Smoke Checklist

Run against the deployment after `uv run gmgn-twitter-intel config` confirms the
operator-owned `~/.gmgn-twitter-intel/config.yaml` and `workers.yaml` paths:

```bash
uv run gmgn-twitter-intel ops mirror-token-images --limit 50 --source-limit 500
uv run gmgn-twitter-intel ops rebuild-token-profiles --limit 500
curl -s 'http://127.0.0.1:8765/api/token-radar?window=1h&scope=all&limit=20' | jq '.. | objects | select(has("logo_url")) | .logo_url'
curl -i 'http://127.0.0.1:8765/api/token-image?url=https%3A%2F%2Fgmgn.ai%2Fexternal-res%2Ftoken.webp'
```

Expected:

- `profile.identity.logo_url` values are `null` or `/api/token-images/{image_id}`.
- No Token Radar API response contains `https://gmgn.ai/external-res/`.
- Old `/api/token-image?url=...` returns `404`.
- Browser network traces show local `/api/token-images/{image_id}` requests or
  fallback marks, not provider image requests.
