export type NewsTokenLane = {
  lane: "resolved" | "attention" | string;
  resolution_status?: string | null;
  symbol?: string | null;
  target_type?: string | null;
  target_id?: string | null;
  reason_codes?: string[];
};

export type NewsFactLane = {
  event_type?: string | null;
  status?: "accepted" | "rejected" | "attention" | string | null;
  rejection_reasons?: string[];
};

export type NewsRow = {
  row_id: string;
  news_item_id: string;
  story_id?: string | null;
  latest_at_ms?: number | null;
  lifecycle_status: string;
  headline: string;
  summary?: string | null;
  source_domain?: string | null;
  canonical_url?: string | null;
  token_lanes?: NewsTokenLane[];
  fact_lanes?: NewsFactLane[];
  token_lanes_json?: NewsTokenLane[];
  fact_lanes_json?: NewsFactLane[];
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
