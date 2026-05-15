# Token Case Redesign Verification

日期：2026-05-15

## 结论

PASS。Token Case dossier hard cut 已完成，`/token/:targetType/:targetId` 与 Search token_result 均复用同一 Token Case panel；旧 token-target audit UI 已删除；OpenAPI 与前端生成类型已同步。

## 覆盖范围

- 后端新增 `TokenCaseService`、target identity repository read path、`GET /api/token-case`。
- `/api/search/inspect` 的 `token_result` 复用 Token Case dossier shape。
- 前端新增 `features/token-case` adapter、route state、React Query hooks、shared Token Case panel。
- `/token/Asset/...` hard cut 到 Token Case route；Search token_result 直接渲染 dossier，不二次请求 `/api/token-case`。
- Playwright/MSW fixture 使用 HANSA 真实视觉基线数据 shape 覆盖 route 与 search 复用。
- `docs/CONTRACTS.md`、`docs/FRONTEND.md`、`docs/generated/openapi.json`、`web/src/lib/types/openapi.ts` 已更新。

## 命令证据

- `uv run ruff check .`：PASS。
- `uv run mypy src`：PASS。
- `uv run pytest tests/unit/test_token_case_service.py tests/unit/test_search_inspect_service.py tests/integration/test_api_http.py -v`：55 passed。
- `cd web && npm run typecheck`：PASS。
- `cd web && npm run lint`：PASS。
- `cd web && npm run format:check`：PASS。
- `cd web && npm test -- --run`：51 files / 161 tests passed。
- `cd web && npm run build`：PASS；Vite reported the existing chunk-size warning.
- `cd web && npm run test:e2e`：7 passed。
- `make regen-contract`：PASS；regenerated OpenAPI and frontend OpenAPI types.
- `make check-all`：PASS：
  - check stage: 573 passed, 13 skipped.
  - integration stage: 202 passed, 9 skipped.
  - Python e2e stage: 5 passed.
  - coverage stage: 882 passed, 14 skipped, total coverage 83.02% >= 80%.

## Notes

- First `make check-all` attempt failed on `mypy` because `live_price_gateway.snapshot()` returned `Any`; fixed with an explicit cast in `TokenCaseService._market_live`.
- Second `make check-all` attempt failed on `test_make_docs_generated_clean_diff` because `docs/generated/openapi.json` was regenerated but not staged. After staging the generated OpenAPI artifact, the full gate passed.
- Manual browser screenshot artefacts were not captured in this pass because the user requested immediate local merge to `main`; Playwright golden paths exercised the HANSA Token Case route and Search token_result reuse.
