# Macro Intel Architecture

Macro Intel owns deterministic macro regime read models inside
`gmgn-twitter-intel`. It does not fetch FRED, NY Fed, Treasury, Cboe, CFTC, or
crypto provider data directly; normalized observations arrive as persisted
facts from an importer or operator-maintained path.

## Ownership

| Object | Category | Runtime writer |
|--------|----------|----------------|
| `macro_observations` | Fact | Importer / operator maintenance path. Normal runtime projection does not mutate it. |
| `macro_view_snapshots` | Read model | `MacroViewProjectionWorker` only. |

## Flow

```text
macro_observations
  -> services/macro_regime_engine.py
  -> runtime/macro_view_projection_worker.py
  -> macro_view_snapshots
  -> /api/views/macro
  -> web /views
```

The macro regime engine emits component scores with evidence and data gaps. UI
and LLM-facing surfaces must read those deterministic fields rather than
recomputing or inventing macro conclusions.
