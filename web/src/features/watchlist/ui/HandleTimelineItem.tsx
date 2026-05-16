import type { WatchlistTimelineItem } from "@lib/types";
import { TokenCasePostEventCard } from "@shared/ui/case-file";

import { buildWatchlistTimelineEvent } from "../model/watchlistTimelineEvent";

export function HandleTimelineItem({ item }: { item: WatchlistTimelineItem }) {
  return <TokenCasePostEventCard item={buildWatchlistTimelineEvent(item)} />;
}
