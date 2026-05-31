# Sidebar Navigation Latency Root Fix Verification

## Coverage

- Shell navigation data dependency removed.
- Sidebar badges and server-derived topbar stats removed.
- Live route data reads moved from global shell chrome to `/`.
- Notification summary/list closed-drawer polling removed.
- Notification summary SQL aggregation implemented.
- Sidebar e2e covers normal, delayed API, and failed API route switching.

## Commands

```text
cd web && npm install
added 656 packages; found 0 vulnerabilities

cd web && npm test -- --run tests/routes/notifications.route.test.tsx
Test Files  1 passed (1)
Tests  3 passed (3)

cd web && npm test -- --run tests/routes/live-radar.route.test.tsx tests/routes/notifications.route.test.tsx tests/component/features/cockpit/ui/CockpitTopbar.test.tsx tests/component/features/cockpit/ui/AppSidebar.test.tsx
Test Files  4 passed (4)
Tests  13 passed (13)

cd web && npm run typecheck
tsc --noEmit passed

cd web && npm run lint
ESLint passed
Architecture tests: 10 files passed, 59 tests passed

cd web && npm run test:e2e -- --project=desktop-1366 tests/e2e/golden-paths/sidebar-navigation.spec.ts --reporter=line
4 passed, 1 skipped

uv run pytest tests/integration/test_notification_repository.py::test_summary_uses_sql_aggregates_without_materializing_unread_rows -q
1 passed in 24.05s

uv run pytest tests/integration/test_api_http.py::test_api_exposes_notification_list_summary_and_read_state tests/integration/test_api_http.py::test_api_marks_author_notifications_read -q
2 passed in 151.98s

uv run ruff check src/parallax/domains/notifications/repositories/notification_repository.py tests/integration/test_notification_repository.py
All checks passed

make check-all
Failed in repository-wide format check before tests:
73 existing Python files would be reformatted.
The listed files did not include this change's notification repository/test files or frontend files.
```

## Skipped Tests

- `desktop-1366` sidebar spec skipped the mobile-only test by design.
- Full `make check-all` did not complete because the repository baseline has unrelated Python formatting drift.

## E2E Golden Path

- `desktop-1366` sidebar navigation spec passed normal route switching, delayed non-bootstrap API route switching, and failed non-bootstrap API route switching.

## Remaining Risks

- Full repository gate is still blocked by unrelated formatting drift outside this change.
