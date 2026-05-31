export type NewsAlertEligibility = {
  in_app_eligible?: boolean | null;
  external_push_ready?: boolean | null;
  external_push_block_reason?: string | null;
  external_push_basis?: string | null;
  agent_status?: string | null;
  decision_class?: string | null;
  provider_status?: string | null;
  provider_score?: number | null;
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
  provider_signal?: NewsSignalSummary | Record<string, unknown> | null;
  alert_eligibility?: NewsAlertEligibility | null;
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
  model?: string | null;
  brief_json?: Record<string, unknown> | null;
  bull_view?: NewsAgentBriefView | null;
  bear_view?: NewsAgentBriefView | null;
  data_gaps?: NewsAgentDataGap[];
  watch_triggers?: string[];
  invalidation_conditions?: string[];
  evidence_refs?: NewsAgentEvidenceRef[];
};

export type NewsAgentRunSummary = {
  run_id?: string | null;
  status?: string | null;
  outcome?: string | null;
  model?: string | null;
  prompt_version?: string | null;
  schema_version?: string | null;
  started_at_ms?: number | null;
  finished_at_ms?: number | null;
  execution_started?: boolean | null;
  error_class?: string | null;
  error?: string | null;
  error_message?: string | null;
};

export type NewsRow = {
  row_id: string;
  news_item_id: string;
  latest_at_ms?: number | null;
  lifecycle_status: string;
  headline: string;
  title?: string | null;
  summary?: string | null;
  source_domain?: string | null;
  provider_type?: string | null;
  source_role?: string | null;
  trust_tier?: string | null;
  coverage_tags?: string[];
  source_quality_status?: string | null;
  source_json?: NewsSourceSummary | Record<string, unknown> | null;
  source?: NewsSourceSummary | null;
  canonical_url?: string | null;
  content_class?: string | null;
  content_tags_json?: string[];
  content_tags?: string[];
  content_classification_json?: Record<string, unknown>;
  content_classification?: Record<string, unknown>;
  signal: NewsSignalSummary;
  token_impacts?: NewsTokenLane[];
  token_lanes: NewsTokenLane[];
  fact_lanes: NewsFactLane[];
  agent_brief?: NewsAgentBrief;
  agent_brief_status?: NewsAgentBriefStatus | null;
  agent_status?: NewsAgentBriefStatus | null;
  agent_brief_computed_at_ms?: number | null;
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
