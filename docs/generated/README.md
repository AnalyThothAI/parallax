# Generated

> **DO NOT HAND-EDIT files in this directory.** They are regenerated from the source of truth listed in each file's header. Edit the source, then run the regenerator.

## Regenerate

```bash
make docs-generated
```

This runs five scripts in sequence:

| File | Source | Script |
|------|--------|--------|
| `db-schema.md` | Alembic head + `pg_catalog` introspection | `scripts/regen_db_schema.py` |
| `cli-help.md` | `gmgn-twitter-intel --help` recursively | `scripts/regen_cli_help.py` |
| `score-versions.md` | grep `score_version=` literals in `src/` | `scripts/regen_score_versions.py` |
| `ws-protocol.md` | extract message-type union from `src/gmgn_twitter_intel/api/ws.py` | `scripts/regen_ws_protocol.py` |
| `pulse-agent-desk-decisions.md` | Pulse Agent Desk OQ + hardening decision constants | `scripts/regen_pulse_agent_desk_decisions.py` |

CI verifies that `make docs-generated` produces no diff against the committed tree.
