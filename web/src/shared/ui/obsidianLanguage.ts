export type ObsidianTone = "opportunity" | "health" | "info" | "risk" | "neutral";

export type ObsidianSource = "official" | "deterministic" | "market" | "social";

export type ObsidianStringField = {
  detail: string;
  label: string;
  source: ObsidianSource;
  tone: ObsidianTone;
  value: string;
};

export type ObsidianStringEvidence = {
  body: string;
  id: string;
  meta?: string;
  title?: string;
  tone?: ObsidianTone;
};
