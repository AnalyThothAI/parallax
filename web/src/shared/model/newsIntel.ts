export type NewsMarketScope = {
  scope?: string[];
  primary?: string | null;
  status?: string | null;
  reason?: string | null;
  basis?: Record<string, unknown>;
  version?: string | null;
};

export type NewsAgentAdmission = {
  eligible?: boolean | null;
  status?: string | null;
  reason?: string | null;
  representative_news_item_id?: string | null;
  basis?: Record<string, unknown>;
  version?: string | null;
};

export type NewsAlertEligibility = {
  in_app_eligible?: boolean | null;
  external_push_ready?: boolean | null;
  external_push_block_reason?: string | null;
  external_push_basis?: string | null;
  agent_status?: string | null;
  decision_class?: string | null;
  provider_status?: string | null;
  provider_score?: number | null;
  market_scope?: NewsMarketScope | null;
  agent_admission_status?: string | null;
  agent_admission_reason?: string | null;
};

export type NewsSignalSummary = {
  source: "provider" | "agent" | "partial" | string;
  provider?: string | null;
  status: "ready" | "partial" | "pending" | "failed" | string;
  direction: "bullish" | "bearish" | "neutral" | string;
  label_zh?: string | null;
  signal?: "long" | "short" | "neutral" | string | null;
  score?: number | null;
  grade?: string | null;
  title_zh?: string | null;
  summary_zh?: string | null;
  summary_en?: string | null;
  method?: string | null;
};

export type NewsSignalEnvelope = {
  display_signal: NewsSignalSummary;
  provider_signal: NewsSignalSummary | null;
  agent_signal: Record<string, unknown>;
  alert_eligibility: NewsAlertEligibility;
};

export type NewsTokenLane = {
  lane: "resolved" | "attention" | "ignored" | string;
  resolution_status?: string | null;
  symbol?: string | null;
  target_type?: string | null;
  target_id?: string | null;
  provider_signal?: string | null;
  provider_score?: number | null;
  provider_grade?: string | null;
  market_type?: string | null;
  reason_codes?: string[];
};

export type NewsFactLane = {
  claim?: string | null;
  event_type?: string | null;
  realis?: string | null;
  status?: "accepted" | "rejected" | "attention" | string | null;
  affected_targets?: unknown[];
  rejection_reasons?: string[];
};

export type NewsAgentBriefStatus =
  | "ready"
  | "insufficient"
  | "pending"
  | "failed"
  | "stale"
  | "disabled"
  | string;

export type NewsAgentBriefView = {
  strength?: string | null;
  thesis_zh?: string | null;
  evidence_refs?: NewsAgentEvidenceRef[];
};

export type NewsAgentEvidenceRef =
  | string
  | {
      ref?: string | null;
      label?: string | null;
      quote?: string | null;
      source?: string | null;
    };

export type NewsAgentDataGap =
  | string
  | {
      description_zh?: string | null;
      description?: string | null;
      kind?: string | null;
      reason?: string | null;
      severity?: string | null;
    };

export type NewsAgentBrief = {
  status: NewsAgentBriefStatus;
  direction?: "bullish" | "bearish" | "mixed" | "neutral" | string | null;
  decision_class?: "driver" | "watch" | "context" | "discard" | string | null;
  title_zh?: string | null;
  summary_zh?: string | null;
  market_read_zh?: string | null;
  research_todos_zh?: string[];
  market_impacts?: unknown[];
  bull_strength?: string | null;
  bear_strength?: string | null;
  data_gap_count?: number | null;
  computed_at_ms?: number | null;
  agent_run_id?: string | null;
  schema_version?: string | null;
  prompt_version?: string | null;
  artifact_version_hash?: string | null;
  input_hash?: string | null;
  output_hash?: string | null;
  brief_json?: Record<string, unknown> | null;
  bull_view?: NewsAgentBriefView | null;
  bear_view?: NewsAgentBriefView | null;
  data_gaps?: NewsAgentDataGap[];
  watch_triggers?: string[];
  invalidation_conditions?: string[];
  evidence_refs?: NewsAgentEvidenceRef[];
};

export type NewsResearchToolResult = {
  tool_call_id?: string | null;
  tool_name?: string | null;
  schema_version?: string | null;
  query_version?: string | null;
  input?: Record<string, unknown> | null;
  source_tables?: string[];
  rows?: unknown[];
  row_count?: number | null;
  truncated?: boolean | null;
  skipped_reason?: string | null;
  result_hash?: string | null;
  generated_at_ms?: number | null;
  latency_ms?: number | null;
  redaction_notes?: string[];
  evidence_refs?: NewsAgentEvidenceRef[];
};

export type NewsAgentRunSummary = {
  run_id?: string | null;
  backend?: string | null;
  status?: string | null;
  outcome?: string | null;
  provider?: string | null;
  model?: string | null;
  lane?: string | null;
  workflow_name?: string | null;
  agent_name?: string | null;
  execution_trace_id?: string | null;
  artifact_version_hash?: string | null;
  prompt_version?: string | null;
  schema_version?: string | null;
  validator_version?: string | null;
  guardrail_version?: string | null;
  input_hash?: string | null;
  output_hash?: string | null;
  started_at_ms?: number | null;
  finished_at_ms?: number | null;
  latency_ms?: number | null;
  execution_started?: boolean | null;
  error_class?: string | null;
  error?: string | null;
  error_message?: string | null;
  request_json?: Record<string, unknown> | null;
  response_json?: Record<string, unknown> | null;
  validation_errors_json?: unknown[];
  usage_json?: Record<string, unknown>;
  trace_metadata_json?: Record<string, unknown>;
  research_plan?: Record<string, unknown> | null;
  tool_results?: NewsResearchToolResult[];
  research_execution?: Record<string, unknown> | null;
  research_hashes?: Record<string, unknown> | null;
  base_packet?: Record<string, unknown> | null;
};

export type NewsRow = {
  row_id: string;
  news_item_id: string;
  latest_at_ms?: number | null;
  lifecycle_status: string;
  headline: string;
  title?: string | null;
  summary?: string | null;
  body_text?: string | null;
  language?: string | null;
  published_at_ms?: number | null;
  fetched_at_ms?: number | null;
  duplicate_observation_count?: number | null;
  source_domain?: string | null;
  provider_type?: string | null;
  source_role?: string | null;
  trust_tier?: string | null;
  coverage_tags?: string[];
  source_quality_status?: string | null;
  source?: NewsSourceSummary | null;
  canonical_url?: string | null;
  content_class?: string | null;
  content_tags?: string[];
  content_classification?: Record<string, unknown>;
  signal: NewsSignalEnvelope;
  token_impacts?: NewsTokenLane[];
  token_lanes: NewsTokenLane[];
  fact_lanes: NewsFactLane[];
  agent_brief?: NewsAgentBrief;
  agent_brief_status?: NewsAgentBriefStatus | null;
  agent_status?: NewsAgentBriefStatus | null;
  agent_brief_computed_at_ms?: number | null;
  market_scope?: NewsMarketScope | null;
  agent_admission_status?: string | null;
  agent_admission_reason?: string | null;
  agent_admission?: NewsAgentAdmission | null;
  agent_representative_news_item_id?: string | null;
};

export type NewsSourceSummary = {
  source_id?: string | null;
  source_name?: string | null;
  source_domain?: string | null;
  provider_type?: string | null;
  source_role?: string | null;
  trust_tier?: string | null;
  coverage_tags?: string[];
  source_quality_status?: string | null;
};

export type NewsItemDetail = NewsRow & {
  content?: string | null;
  body_text?: string | null;
  entities?: unknown[];
  token_mentions?: unknown[];
  fact_candidates?: NewsFactLane[];
  agent_run?: NewsAgentRunSummary | null;
  provider_item?: Record<string, unknown> | null;
  fetch_run?: Record<string, unknown> | null;
  observation_edges?: Record<string, unknown>[];
  provider_observations?: Record<string, unknown>[];
};

export type NewsRowsData = {
  items: NewsRow[];
  next_cursor?: string | null;
};

export const newsLifecycleLabel = (status: string): string => {
  const labels: Record<string, string> = {
    raw: "Raw",
    processed: "Processed",
    entity_extracted: "Entities",
    fact_candidate: "Fact",
    accepted: "Accepted",
    rejected: "Rejected",
    attention: "Attention",
  };
  return labels[status] ?? status;
};

export const newsTokenLaneLabel = (lane: NewsTokenLane): string => {
  const symbol = lane.symbol || "Unknown";
  return `${symbol} · ${lane.lane}`;
};
