import type { components } from "@lib/types";

export type NewsFactRow = components["schemas"]["NewsRow"];
export type NewsFactItem = components["schemas"]["NewsObjectData"];
export type NewsFactLane = components["schemas"]["NewsFactLane"];
export type NewsMarketScope = components["schemas"]["NewsMarketScope"];
export type NewsProviderRating = components["schemas"]["NewsProviderRating"];
export type NewsTokenLane = components["schemas"]["NewsTokenLane"];

export const newsLifecycleTone = (status: string): string => {
  if (status === "accepted" || status === "processed" || status === "entity_extracted") {
    return "is-ready";
  }
  if (status === "rejected") {
    return "is-blocked";
  }
  return "is-waiting";
};

export const tokenLaneLabel = (lane: Pick<NewsTokenLane, "resolution_status" | "lane">): string =>
  lane.resolution_status || lane.lane || "token";
