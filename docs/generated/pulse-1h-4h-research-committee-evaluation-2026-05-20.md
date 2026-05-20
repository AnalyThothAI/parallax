# Pulse 1h/4h Research Committee Evaluation

- generated_date: 2026-05-20
- lookback_hours: 24
- Recommendation: stop

## Runtime Config Confirmation

- config_path: /Users/qinghuan/.gmgn-twitter-intel/config.yaml
- workers_config_path: /Users/qinghuan/.gmgn-twitter-intel/workers.yaml
- config_path_under_operator_home: true
- workers_config_path_under_operator_home: true

## Policy Comparison

### Radar

- sample_kind=latest_snapshot, computed_at_ms={latest:1779242011263, max:1779242011263, min:1779241386633}
- overall: total=585, single_author_ratio=0.52, ge3_author_ratio=0.40, top_author_share_buckets={50_65:54, 65_80:22, ge_80:306, lt_50:203, unknown:0}, watched_to_matched_ratio=0.60, watched_only=58, matched_only=97, failures=0, failure_rate=0.00, invalid_refs=0, invalid_ref_rate=0.00, backpressure=0, backpressure_rate=0.00, display_status_counts={}, outcome_counts={}, status_counts={}, no_run_count=0, due_pending_count=0
- current_policy: total=585, single_author_ratio=0.52, ge3_author_ratio=0.40, top_author_share_buckets={50_65:54, 65_80:22, ge_80:306, lt_50:203, unknown:0}, watched_to_matched_ratio=0.60, watched_only=58, matched_only=97, failures=0, failure_rate=0.00, invalid_refs=0, invalid_ref_rate=0.00, backpressure=0, backpressure_rate=0.00, display_status_counts={}, outcome_counts={}, status_counts={}, no_run_count=0, due_pending_count=0
- proposed_primary: total=273, single_author_ratio=0.41, ge3_author_ratio=0.47, top_author_share_buckets={50_65:42, 65_80:13, ge_80:115, lt_50:103, unknown:0}, watched_to_matched_ratio=0.00, watched_only=16, matched_only=0, failures=0, failure_rate=0.00, invalid_refs=0, invalid_ref_rate=0.00, backpressure=0, backpressure_rate=0.00, display_status_counts={}, outcome_counts={}, status_counts={}, no_run_count=0, due_pending_count=0

### Candidates

- overall: total=667, single_author_ratio=0.36, ge3_author_ratio=0.35, top_author_share_buckets={50_65:186, 65_80:44, ge_80:243, lt_50:194, unknown:0}, watched_to_matched_ratio=0.29, watched_only=45, matched_only=153, failures=0, failure_rate=0.00, invalid_refs=0, invalid_ref_rate=0.00, backpressure=0, backpressure_rate=0.00, display_status_counts={display_risk_rejected_high_info:185, display_token_watch:18, display_trade_candidate:27, hidden_abstain:18, hidden_hold_publish:224, hidden_insufficient_evidence:102, hidden_invalid_output:93}, outcome_counts={}, status_counts={}, no_run_count=0, due_pending_count=0
- current_policy: total=667, single_author_ratio=0.36, ge3_author_ratio=0.35, top_author_share_buckets={50_65:186, 65_80:44, ge_80:243, lt_50:194, unknown:0}, watched_to_matched_ratio=0.29, watched_only=45, matched_only=153, failures=0, failure_rate=0.00, invalid_refs=0, invalid_ref_rate=0.00, backpressure=0, backpressure_rate=0.00, display_status_counts={display_risk_rejected_high_info:185, display_token_watch:18, display_trade_candidate:27, hidden_abstain:18, hidden_hold_publish:224, hidden_insufficient_evidence:102, hidden_invalid_output:93}, outcome_counts={}, status_counts={}, no_run_count=0, due_pending_count=0
- proposed_primary: total=179, single_author_ratio=0.00, ge3_author_ratio=0.94, top_author_share_buckets={50_65:29, 65_80:9, ge_80:0, lt_50:141, unknown:0}, watched_to_matched_ratio=0.00, watched_only=26, matched_only=0, failures=0, failure_rate=0.00, invalid_refs=0, invalid_ref_rate=0.00, backpressure=0, backpressure_rate=0.00, display_status_counts={display_risk_rejected_high_info:7, display_token_watch:10, display_trade_candidate:22, hidden_abstain:1, hidden_hold_publish:91, hidden_insufficient_evidence:24, hidden_invalid_output:24}, outcome_counts={}, status_counts={}, no_run_count=0, due_pending_count=0

### Runs

- overall: total=1586, single_author_ratio=0.00, ge3_author_ratio=0.00, top_author_share_buckets={}, watched_to_matched_ratio=0.00, watched_only=0, matched_only=0, failures=683, failure_rate=0.43, invalid_refs=225, invalid_ref_rate=0.14, backpressure=414, backpressure_rate=0.26, display_status_counts={display_risk_rejected_high_info:264, display_token_watch:41, display_trade_candidate:46, hidden_abstain:24, hidden_hold_publish:306, hidden_insufficient_evidence:175, hidden_invalid_output:131, unknown:599}, outcome_counts={abstain_insufficient_evidence:48, backpressure_circuit_open:140, blocked_market_contract:263, completed:451, invalid_unknown_evidence_ref:225, running:1, timeout:210, unexpected_exception:248}, status_counts={done:987, failed:458, running:1, skipped:140}, no_run_count=0, due_pending_count=0
- current_policy: total=1586, single_author_ratio=0.00, ge3_author_ratio=0.00, top_author_share_buckets={}, watched_to_matched_ratio=0.00, watched_only=0, matched_only=0, failures=683, failure_rate=0.43, invalid_refs=225, invalid_ref_rate=0.14, backpressure=414, backpressure_rate=0.26, display_status_counts={display_risk_rejected_high_info:264, display_token_watch:41, display_trade_candidate:46, hidden_abstain:24, hidden_hold_publish:306, hidden_insufficient_evidence:175, hidden_invalid_output:131, unknown:599}, outcome_counts={abstain_insufficient_evidence:48, backpressure_circuit_open:140, blocked_market_contract:263, completed:451, invalid_unknown_evidence_ref:225, running:1, timeout:210, unexpected_exception:248}, status_counts={done:987, failed:458, running:1, skipped:140}, no_run_count=0, due_pending_count=0
- proposed_primary: total=550, single_author_ratio=0.00, ge3_author_ratio=0.00, top_author_share_buckets={}, watched_to_matched_ratio=0.00, watched_only=0, matched_only=0, failures=302, failure_rate=0.55, invalid_refs=78, invalid_ref_rate=0.14, backpressure=144, backpressure_rate=0.26, display_status_counts={display_risk_rejected_high_info:7, display_token_watch:14, display_trade_candidate:29, hidden_abstain:1, hidden_hold_publish:107, hidden_insufficient_evidence:44, hidden_invalid_output:27, unknown:321}, outcome_counts={abstain_insufficient_evidence:4, backpressure_circuit_open:97, blocked_market_contract:64, completed:83, invalid_unknown_evidence_ref:78, timeout:129, unexpected_exception:95}, status_counts={done:229, failed:224, skipped:97}, no_run_count=0, due_pending_count=0

### Jobs

- overall: total=1245, single_author_ratio=0.00, ge3_author_ratio=0.00, top_author_share_buckets={}, watched_to_matched_ratio=0.00, watched_only=0, matched_only=0, failures=0, failure_rate=0.00, invalid_refs=0, invalid_ref_rate=0.00, backpressure=675, backpressure_rate=0.54, display_status_counts={}, outcome_counts={}, status_counts={dead:671, done:570, pending:3, running:1}, no_run_count=333, due_pending_count=3
- current_policy: total=1245, single_author_ratio=0.00, ge3_author_ratio=0.00, top_author_share_buckets={}, watched_to_matched_ratio=0.00, watched_only=0, matched_only=0, failures=0, failure_rate=0.00, invalid_refs=0, invalid_ref_rate=0.00, backpressure=675, backpressure_rate=0.54, display_status_counts={}, outcome_counts={}, status_counts={dead:671, done:570, pending:3, running:1}, no_run_count=333, due_pending_count=3
- proposed_primary: total=201, single_author_ratio=0.00, ge3_author_ratio=0.00, top_author_share_buckets={}, watched_to_matched_ratio=0.00, watched_only=0, matched_only=0, failures=0, failure_rate=0.00, invalid_refs=0, invalid_ref_rate=0.00, backpressure=25, backpressure_rate=0.12, display_status_counts={}, outcome_counts={}, status_counts={dead:23, done:176, pending:2}, no_run_count=13, due_pending_count=2

## Recommendation Rationale

stop based on proposed 1h/all and 4h/all radar latest-snapshot sample size 273, ge3 author ratio 0.47, single-author ratio 0.41, run failure rate 0.55, and invalid-ref rate 0.14, job backpressure rate 0.12.
