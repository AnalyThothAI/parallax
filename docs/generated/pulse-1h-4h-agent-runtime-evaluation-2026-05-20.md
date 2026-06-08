# Pulse 1h/4h Agent Runtime Evaluation

- generated_date: 2026-05-20
- lookback_hours: 24
- Recommendation: stop

## Runtime Config Confirmation

- config_path: /Users/qinghuan/.parallax/config.yaml
- workers_config_path: /Users/qinghuan/.parallax/workers.yaml
- config_path_under_operator_home: true
- workers_config_path_under_operator_home: true

## Policy Comparison

### Radar

- sample_kind=latest_snapshot, computed_at_ms={latest:1779243593715, max:1779243593715, min:1779241577276}
- overall: total=588, single_author_ratio=0.54, ge3_author_ratio=0.38, top_author_share_buckets={50_65:49, 65_80:25, ge_80:320, lt_50:194, unknown:0}, watched_to_matched_ratio=0.59, watched_only=55, matched_only=94, failures=0, failure_rate=0.00, invalid_refs=0, invalid_ref_rate=0.00, backpressure=0, backpressure_rate=0.00, display_status_counts={}, outcome_counts={}, status_counts={}, no_run_count=0, due_pending_count=0
- current_policy: total=588, single_author_ratio=0.54, ge3_author_ratio=0.38, top_author_share_buckets={50_65:49, 65_80:25, ge_80:320, lt_50:194, unknown:0}, watched_to_matched_ratio=0.59, watched_only=55, matched_only=94, failures=0, failure_rate=0.00, invalid_refs=0, invalid_ref_rate=0.00, backpressure=0, backpressure_rate=0.00, display_status_counts={}, outcome_counts={}, status_counts={}, no_run_count=0, due_pending_count=0
- proposed_primary: total=262, single_author_ratio=0.43, ge3_author_ratio=0.45, top_author_share_buckets={50_65:38, 65_80:17, ge_80:113, lt_50:94, unknown:0}, watched_to_matched_ratio=0.00, watched_only=14, matched_only=0, failures=0, failure_rate=0.00, invalid_refs=0, invalid_ref_rate=0.00, backpressure=0, backpressure_rate=0.00, display_status_counts={}, outcome_counts={}, status_counts={}, no_run_count=0, due_pending_count=0

### Candidates

- overall: total=669, single_author_ratio=0.36, ge3_author_ratio=0.35, top_author_share_buckets={50_65:185, 65_80:44, ge_80:244, lt_50:196, unknown:0}, watched_to_matched_ratio=0.29, watched_only=45, matched_only=154, failures=0, failure_rate=0.00, invalid_refs=0, invalid_ref_rate=0.00, backpressure=0, backpressure_rate=0.00, display_status_counts={display_risk_rejected_high_info:188, display_token_watch:18, display_trade_candidate:28, hidden_abstain:18, hidden_hold_publish:219, hidden_insufficient_evidence:104, hidden_invalid_output:94}, outcome_counts={}, status_counts={}, no_run_count=0, due_pending_count=0
- current_policy: total=669, single_author_ratio=0.36, ge3_author_ratio=0.35, top_author_share_buckets={50_65:185, 65_80:44, ge_80:244, lt_50:196, unknown:0}, watched_to_matched_ratio=0.29, watched_only=45, matched_only=154, failures=0, failure_rate=0.00, invalid_refs=0, invalid_ref_rate=0.00, backpressure=0, backpressure_rate=0.00, display_status_counts={display_risk_rejected_high_info:188, display_token_watch:18, display_trade_candidate:28, hidden_abstain:18, hidden_hold_publish:219, hidden_insufficient_evidence:104, hidden_invalid_output:94}, outcome_counts={}, status_counts={}, no_run_count=0, due_pending_count=0
- proposed_primary: total=182, single_author_ratio=0.00, ge3_author_ratio=0.93, top_author_share_buckets={50_65:29, 65_80:10, ge_80:0, lt_50:143, unknown:0}, watched_to_matched_ratio=0.00, watched_only=26, matched_only=0, failures=0, failure_rate=0.00, invalid_refs=0, invalid_ref_rate=0.00, backpressure=0, backpressure_rate=0.00, display_status_counts={display_risk_rejected_high_info:8, display_token_watch:9, display_trade_candidate:23, hidden_abstain:1, hidden_hold_publish:90, hidden_insufficient_evidence:26, hidden_invalid_output:25}, outcome_counts={}, status_counts={}, no_run_count=0, due_pending_count=0

### Runs

- overall: total=1586, single_author_ratio=0.00, ge3_author_ratio=0.00, top_author_share_buckets={}, watched_to_matched_ratio=0.00, watched_only=0, matched_only=0, failures=678, failure_rate=0.43, invalid_refs=226, invalid_ref_rate=0.14, backpressure=407, backpressure_rate=0.26, display_status_counts={display_risk_rejected_high_info:267, display_token_watch:42, display_trade_candidate:49, hidden_abstain:24, hidden_hold_publish:300, hidden_insufficient_evidence:177, hidden_invalid_output:134, unknown:593}, outcome_counts={abstain_insufficient_evidence:49, backpressure_circuit_open:140, blocked_market_contract:262, completed:456, invalid_unknown_evidence_ref:226, running:1, timeout:204, unexpected_exception:248}, status_counts={done:993, failed:452, running:1, skipped:140}, no_run_count=0, due_pending_count=0
- current_policy: total=1586, single_author_ratio=0.00, ge3_author_ratio=0.00, top_author_share_buckets={}, watched_to_matched_ratio=0.00, watched_only=0, matched_only=0, failures=678, failure_rate=0.43, invalid_refs=226, invalid_ref_rate=0.14, backpressure=407, backpressure_rate=0.26, display_status_counts={display_risk_rejected_high_info:267, display_token_watch:42, display_trade_candidate:49, hidden_abstain:24, hidden_hold_publish:300, hidden_insufficient_evidence:177, hidden_invalid_output:134, unknown:593}, outcome_counts={abstain_insufficient_evidence:49, backpressure_circuit_open:140, blocked_market_contract:262, completed:456, invalid_unknown_evidence_ref:226, running:1, timeout:204, unexpected_exception:248}, status_counts={done:993, failed:452, running:1, skipped:140}, no_run_count=0, due_pending_count=0
- proposed_primary: total=551, single_author_ratio=0.00, ge3_author_ratio=0.00, top_author_share_buckets={}, watched_to_matched_ratio=0.00, watched_only=0, matched_only=0, failures=298, failure_rate=0.54, invalid_refs=79, invalid_ref_rate=0.14, backpressure=140, backpressure_rate=0.25, display_status_counts={display_risk_rejected_high_info:8, display_token_watch:14, display_trade_candidate:31, hidden_abstain:1, hidden_hold_publish:106, hidden_insufficient_evidence:46, hidden_invalid_output:29, unknown:316}, outcome_counts={abstain_insufficient_evidence:5, backpressure_circuit_open:97, blocked_market_contract:66, completed:85, invalid_unknown_evidence_ref:79, timeout:124, unexpected_exception:95}, status_counts={done:235, failed:219, skipped:97}, no_run_count=0, due_pending_count=0

### Jobs

- overall: total=1253, single_author_ratio=0.00, ge3_author_ratio=0.00, top_author_share_buckets={}, watched_to_matched_ratio=0.00, watched_only=0, matched_only=0, failures=0, failure_rate=0.00, invalid_refs=0, invalid_ref_rate=0.00, backpressure=677, backpressure_rate=0.54, display_status_counts={}, outcome_counts={}, status_counts={dead:676, done:576, running:1}, no_run_count=334, due_pending_count=0
- current_policy: total=1253, single_author_ratio=0.00, ge3_author_ratio=0.00, top_author_share_buckets={}, watched_to_matched_ratio=0.00, watched_only=0, matched_only=0, failures=0, failure_rate=0.00, invalid_refs=0, invalid_ref_rate=0.00, backpressure=677, backpressure_rate=0.54, display_status_counts={}, outcome_counts={}, status_counts={dead:676, done:576, running:1}, no_run_count=334, due_pending_count=0
- proposed_primary: total=204, single_author_ratio=0.00, ge3_author_ratio=0.00, top_author_share_buckets={}, watched_to_matched_ratio=0.00, watched_only=0, matched_only=0, failures=0, failure_rate=0.00, invalid_refs=0, invalid_ref_rate=0.00, backpressure=23, backpressure_rate=0.11, display_status_counts={}, outcome_counts={}, status_counts={dead:23, done:181}, no_run_count=13, due_pending_count=0

## Recommendation Rationale

stop based on proposed 1h/all and 4h/all radar latest-snapshot sample size 262, ge3 author ratio 0.45, single-author ratio 0.43, run failure rate 0.54, and invalid-ref rate 0.14, job backpressure rate 0.11.
