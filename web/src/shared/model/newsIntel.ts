export type NewsTokenLane = {
  lane: "resolved" | "attention" | string;
  resolution_status?: string | null;
  symbol?: string | null;
  target_type?: string | null;
  target_id?: string | null;
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

export type NewsRow = {
  row_id: string;
  news_item_id: string;
  story_id?: string | null;
  latest_at_ms?: number | null;
  lifecycle_status: string;
  headline: string;
  title?: string | null;
  summary?: string | null;
  source_domain?: string | null;
  canonical_url?: string | null;
  token_lanes?: NewsTokenLane[];
  fact_lanes?: NewsFactLane[];
  token_lanes_json?: NewsTokenLane[];
  fact_lanes_json?: NewsFactLane[];
};

export type NewsItemDetail = NewsRow & {
  content?: string | null;
  body_text?: string | null;
  source?: {
    source_name?: string | null;
    source_domain?: string | null;
    trust_tier?: string | null;
    source_role?: string | null;
  } | null;
  story_members?: Array<{
    story_id?: string | null;
    status?: string | null;
    representative_title?: string | null;
    latest_seen_at_ms?: number | null;
  }>;
  entities?: unknown[];
  token_mentions?: unknown[];
  fact_candidates?: NewsFactLane[];
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
