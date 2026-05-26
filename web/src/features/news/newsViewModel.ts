import type { NewsAgentBrief, NewsItemDetail } from "@shared/model/newsIntel";

export type NewsInstrument = {
  label: string;
  priceState: string;
  primary?: boolean;
  type: string;
  use: string;
};

export const agentBriefLabel = (status?: string | null): string => status || "pending";

export const agentBriefMissingText = (brief?: Pick<NewsAgentBrief, "status"> | null): string => {
  const status = brief?.status || "pending";
  const messages: Record<string, string> = {
    disabled: "Agent brief disabled.",
    failed: "Agent brief failed.",
    insufficient: "Agent brief insufficient.",
    pending: "Agent brief pending.",
    stale: "Agent brief stale.",
  };
  return messages[status] ?? `Agent brief ${status}.`;
};

export const formatAgentBriefStrength = (strength?: string | null): string => strength || "absent";

export const inferNewsInstruments = (
  item: Pick<NewsItemDetail, "token_lanes">,
): NewsInstrument[] => {
  const seen = new Set<string>();
  const instruments: NewsInstrument[] = [];
  for (const lane of item.token_lanes ?? []) {
    const label = lane.symbol || lane.target_id || "linked token";
    if (seen.has(label)) {
      continue;
    }
    seen.add(label);
    const resolved = isResolvedTokenLane(lane);
    instruments.push({
      label,
      priceState: resolved ? "identity resolved" : "identity unresolved",
      primary: resolved,
      type: lane.target_type || "token mention",
      use: resolved
        ? "Backend token lane has production identity."
        : "Observed token text is awaiting backend identity resolution.",
    });
  }
  return instruments.length
    ? instruments
    : [
        {
          label: "No token lane",
          priceState: "identity absent",
          type: "data gap",
          use: "No backend token mention is attached yet.",
        },
      ];
};

function isResolvedTokenLane(lane: {
  lane?: string | null;
  resolution_status?: string | null;
  target_id?: string | null;
}): boolean {
  return Boolean(
    lane.target_id || lane.lane === "resolved" || lane.resolution_status === "resolved",
  );
}
