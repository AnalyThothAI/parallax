import { create } from "zustand";
import type { RadarSortMode, ScopeKey, TimelineBucket, TokenDetailTab, WindowKey } from "../api/types";

type PostSortMode = "recent" | "quality";

type TraderState = {
  token: string;
  window: WindowKey;
  scope: ScopeKey;
  handles: string;
  search: string;
  submittedSearch: string;
  radarSortMode: RadarSortMode;
  detailTab: TokenDetailTab;
  timelineBucket: TimelineBucket;
  postSortMode: PostSortMode;
  hideDuplicateClusters: boolean;
  watchedPostsOnly: boolean;
  setToken: (token: string) => void;
  setWindow: (window: WindowKey) => void;
  setScope: (scope: ScopeKey) => void;
  setHandles: (handles: string) => void;
  setSearch: (search: string) => void;
  submitSearch: () => void;
  runSearch: (search: string) => void;
  setRadarSortMode: (mode: RadarSortMode) => void;
  setDetailTab: (tab: TokenDetailTab) => void;
  setTimelineBucket: (bucket: TimelineBucket) => void;
  setPostSortMode: (mode: PostSortMode) => void;
  setHideDuplicateClusters: (enabled: boolean) => void;
  setWatchedPostsOnly: (enabled: boolean) => void;
};

export const useTraderStore = create<TraderState>((set, get) => ({
  token: "",
  window: "1h",
  scope: "all",
  handles: "",
  search: "$PEPE",
  submittedSearch: "$PEPE",
  radarSortMode: "opportunity",
  detailTab: "timeline",
  timelineBucket: "1m",
  postSortMode: "recent",
  hideDuplicateClusters: false,
  watchedPostsOnly: false,
  setToken: (token) => set({ token }),
  setWindow: (window) => set({ window }),
  setScope: (scope) => set({ scope }),
  setHandles: (handles) => set({ handles }),
  setSearch: (search) => set({ search }),
  submitSearch: () => set({ submittedSearch: get().search.trim() }),
  runSearch: (search) => set({ search, submittedSearch: search.trim() }),
  setRadarSortMode: (radarSortMode) => set({ radarSortMode }),
  setDetailTab: (detailTab) => set({ detailTab }),
  setTimelineBucket: (timelineBucket) => set({ timelineBucket }),
  setPostSortMode: (postSortMode) => set({ postSortMode }),
  setHideDuplicateClusters: (hideDuplicateClusters) => set({ hideDuplicateClusters }),
  setWatchedPostsOnly: (watchedPostsOnly) => set({ watchedPostsOnly })
}));
