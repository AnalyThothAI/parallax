export type MacroResearchSectionData = {
  section_id: string;
  title: string;
  body_markdown: string;
  citation_ids: string[];
};

export type MacroResearchEvidenceGapData = {
  gap_id: string;
  summary: string;
  details: string | null;
  citation_ids: string[];
};

export type MacroResearchCitationData = {
  citation_id: string;
  source_type: string;
  source_ref: string;
  source_label: string;
  observed_at: string | null;
  published_at_ms: number | null;
  available_at_ms: number | null;
  source_url: string | null;
  lineage: Record<string, unknown>;
};

export type MacroResearchPublicationData = {
  schema_version: string;
  session_date: string;
  market_cutoff_ms: number;
  title: string;
  executive_summary: string;
  sections: MacroResearchSectionData[];
  evidence_gaps: MacroResearchEvidenceGapData[];
  citations: MacroResearchCitationData[];
  reviewer_notes: string[];
  audit: Record<string, unknown>;
  published_at_ms: number | null;
};

export type MacroResearchRunData = {
  session_date: string;
  status: string;
  attempt_count: number;
  max_attempts: number;
  last_error: string | null;
  updated_at_ms: number;
};

export type MacroResearchReadData = {
  state: "current" | "historical" | "generating" | "failed" | "missing";
  requested_session_date: string;
  current_session_date: string;
  publication: MacroResearchPublicationData | null;
  run: MacroResearchRunData | null;
};

export type MacroLiveViewId =
  | "overview"
  | "rates-inflation"
  | "growth-labor"
  | "liquidity-funding"
  | "credit"
  | "cross-asset";

export type MacroLiveReadViewId = "dashboard" | MacroLiveViewId;
export type MacroLiveWindow = "30d" | "90d" | "1y" | "5y";

export type MacroLiveCalculationData = {
  formula_id: string;
  formula: string;
  operands: string[];
  window: MacroLiveWindow;
  sample_size: number;
  result: number | null;
  unit: string;
};

export type MacroLiveHistoryPointData = {
  observed_at: string;
  value_numeric: number | null;
  source_timestamp: string | null;
  received_at_ms: number | null;
  source_name: string | null;
  series_key: string | null;
  source_priority: number | null;
  frequency: string | null;
  data_quality: string | null;
  source_url: string | null;
};

export type MacroLiveMetricData = {
  concept_key: string;
  page_id: MacroLiveViewId | null;
  section_id: string;
  section_label: string;
  display_label: string;
  display_order: number;
  summary: boolean;
  kind: "material" | "derived";
  availability: "available" | "missing";
  value_numeric: number | null;
  unit: string | null;
  frequency: string | null;
  observed_at: string | null;
  source_timestamp: string | null;
  received_at_ms: number | null;
  source_name: string | null;
  series_key: string | null;
  source_priority: number | null;
  data_quality: string | null;
  source_url: string | null;
  history: MacroLiveHistoryPointData[];
  calculation: MacroLiveCalculationData | null;
};

export type MacroLiveViewData = {
  view_id: MacroLiveViewId;
  title: string;
  description: string;
  metrics: MacroLiveMetricData[];
  total_metric_count: number;
  available_count: number;
  latest_observed_at: string | null;
  max_received_at_ms: number | null;
};

export type MacroLiveResearchLinkData = {
  state: "current" | "generating" | "failed" | "missing";
  session_date: string;
  market_cutoff_ms: number | null;
  title: string | null;
  executive_summary: string | null;
  evidence_gap_summaries: string[];
  href: "/macro/research";
};

export type MacroLiveEvidenceReadData = {
  schema_version: "macro_live_evidence_v1";
  view_id: MacroLiveReadViewId;
  window: MacroLiveWindow;
  read_at_ms: number;
  views: MacroLiveViewData[];
  unclassified: MacroLiveMetricData[];
  research: MacroLiveResearchLinkData | null;
};
