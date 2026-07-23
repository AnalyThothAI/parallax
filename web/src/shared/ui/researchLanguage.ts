export type ResearchTone = "opportunity" | "health" | "info" | "risk" | "neutral";

export type ResearchSource = "official" | "deterministic" | "market" | "social";

export type ResearchStringField = {
  detail: string;
  label: string;
  source: ResearchSource;
  tone: ResearchTone;
  value: string;
};

export type ResearchStringEvidence = {
  body: string;
  id: string;
  meta?: string;
  title?: string;
  tone?: ResearchTone;
};
