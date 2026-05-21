# Signal Pulse Agent Cost Guard Read-only Report

- generated_date: 2026-05-21
- lookback_hours: 24
- dry_run: true
- since_ms: 1779234774452
- now_ms: 1779321174452

## Runtime Config Confirmation

- config_path: /Users/qinghuan/.gmgn-twitter-intel/config.yaml
- workers_config_path: /Users/qinghuan/.gmgn-twitter-intel/workers.yaml
- config_path_under_operator_home: true
- workers_config_path_under_operator_home: true

## Summary

- runs_total: 1184
- backpressure_circuit_open_runs: 483
- hidden_invalid_output_runs: 354
- deepseek_total_tokens: 7939347
- hidden_invalid_output_tokens: 7757552
- predicted_deepseek_tokens_after: 163120
- predicted_deepseek_reduction_ratio: 0.9795
- duplicate_success_fingerprint_groups: 0
- extra_success_runs_same_fingerprint: 0
- display_trade_candidate: 9
- display_token_watch: 13

## Steps By Stage Model Status

| stage | model | status | steps | tokens |
| --- | --- | --- | --- | --- |
| bear_case | deepseek-v4-flash | failed | 24 | 0 |
| bear_case | deepseek-v4-flash | ok | 228 | 2731798 |
| bear_case | qwen3.6 | failed | 9 | 128470 |
| bear_case | qwen3.6 | ok | 43 | 501296 |
| bear_case | qwen3.6 | timeout | 2 | 0 |
| claim_verifier | deepseek-v4-flash | ok | 355 | 0 |
| claim_verifier | qwen3.6 | ok | 214 | 0 |
| decision_maker | qwen3.6 | failed | 17 | 26957 |
| decision_maker | qwen3.6 | ok | 84 | 882915 |
| decision_maker | qwen3.6 | timeout | 1 | 0 |
| deterministic_eval | deepseek-v4-flash | ok | 355 | 0 |
| deterministic_eval | qwen3.6 | ok | 214 | 0 |
| evidence_completeness_gate | deepseek-v4-flash | ok | 903 | 0 |
| evidence_completeness_gate | qwen3.6 | ok | 281 | 0 |
| evidence_debate | qwen3.6 | failed | 29 | 33344 |
| evidence_debate | qwen3.6 | ok | 102 | 709432 |
| evidence_debate | qwen3.6 | timeout | 5 | 0 |
| evidence_pack | deepseek-v4-flash | ok | 903 | 0 |
| evidence_pack | qwen3.6 | ok | 281 | 0 |
| recommendation_clipper | deepseek-v4-flash | ok | 355 | 0 |
| recommendation_clipper | qwen3.6 | ok | 214 | 0 |
| risk_portfolio_judge | deepseek-v4-flash | failed | 76 | 117115 |
| risk_portfolio_judge | deepseek-v4-flash | ok | 152 | 2095654 |
| risk_portfolio_judge | qwen3.6 | failed | 14 | 64288 |
| risk_portfolio_judge | qwen3.6 | ok | 27 | 416567 |
| risk_portfolio_judge | qwen3.6 | timeout | 2 | 0 |
| signal_analyst | deepseek-v4-flash | failed | 98 | 155664 |
| signal_analyst | deepseek-v4-flash | ok | 252 | 2839116 |
| signal_analyst | qwen3.6 | failed | 9 | 133908 |
| signal_analyst | qwen3.6 | ok | 54 | 623509 |
| signal_analyst | qwen3.6 | timeout | 1 | 0 |
| write_gate | deepseek-v4-flash | ok | 355 | 0 |
| write_gate | qwen3.6 | ok | 214 | 0 |

## Tokens By Display Status

| display_status | steps | tokens |
| --- | --- | --- |
| display_risk_rejected_high_info | 496 | 1073997 |
| display_token_watch | 112 | 370540 |
| display_trade_candidate | 72 | 184583 |
| hidden_abstain | 40 | 64007 |
| hidden_insufficient_evidence | 564 | 0 |
| hidden_invalid_output | 3051 | 9705696 |
| hidden_source_quality | 195 | 18675 |
| unknown | 1343 | 42535 |
