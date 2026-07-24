# Generated

> **DO NOT HAND-EDIT files in this directory.** They are regenerated from the source of truth listed in each file's header. Edit the source, then run the regenerator.

## Regenerate

```bash
make docs-generated
make regen-contract
```

These commands run the source generators below:

| File | Source | Script |
|------|--------|--------|
| `db-schema.md` | Alembic head + `pg_catalog` introspection | `scripts/regen_db_schema.py` |
| `cli-help.md` | `tracefold --help` recursively | `scripts/regen_cli_help.py` |
| `score-versions.md` | grep `score_version=` literals in `src/` | `scripts/regen_score_versions.py` |
| `ws-protocol.md` | extract WebSocket message type literals and source classes from `src/tracefold/app/http/ws.py` | `scripts/regen_ws_protocol.py` |
| `openapi.json` | mounted FastAPI routes and schemas | `scripts/regen_openapi.py` |

CI verifies that regeneration produces no diff against the committed tree.
