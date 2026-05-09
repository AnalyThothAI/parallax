# PostgreSQL Projection Closure Plan

## Scope

Keep projection read models on the PostgreSQL storage path and verify the runtime, migrations, repositories, and tests all use that single store.

## Execution

1. Maintain Alembic migrations as the only schema evolution path.
2. Keep repository reads and writes behind the existing PostgreSQL connection/session helpers.
3. Validate projection rebuilds through repository and API tests.
4. Preserve the Docker Compose PostgreSQL service as the local integration target.

## Verification

Run `uv run ruff check .`, `uv run pytest`, and `uv run python -m compileall src tests` before shipping projection storage changes.
