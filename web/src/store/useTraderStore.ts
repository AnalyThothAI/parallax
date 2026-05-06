import { create } from "zustand";
import type {
  RadarSortMode,
  ScopeKey,
  SignalLabInspectorTab,
  SignalLabStageFilter,
  TokenDetailMode,
  TokenDetailTab,
  TokenPostRange,
  TokenPostSortMode,
  WindowKey
} from "../api/types";

type ActiveView = "live" | "signal_lab";
type SignalLabHorizon = "6h" | "24h";

type TraderState = {
  token: string;
  window: WindowKey;
  scope: ScopeKey;
  handles: string;
  search: string;
  submittedSearch: string;
  radarSortMode: RadarSortMode;
  detailTab: TokenDetailTab;
  detailWindow: WindowKey;
  detailMode: TokenDetailMode;
  selectedBucketStartMs: number | null;
  selectedEventId: string | null;
  postRange: TokenPostRange;
  postSortMode: TokenPostSortMode;
  hideDuplicateClusters: boolean;
  watchedPostsOnly: boolean;
  activeView: ActiveView;
  signalLabStage: SignalLabStageFilter;
  signalLabHorizon: SignalLabHorizon;
  signalLabAsset: string;
  signalLabHandle: string;
  signalLabSearch: string;
  signalLabInspectorTab: SignalLabInspectorTab;
  setToken: (token: string) => void;
  setWindow: (window: WindowKey) => void;
  setScope: (scope: ScopeKey) => void;
  setHandles: (handles: string) => void;
  setSearch: (search: string) => void;
  submitSearch: () => void;
  runSearch: (search: string) => void;
  setRadarSortMode: (mode: RadarSortMode) => void;
  setDetailTab: (tab: TokenDetailTab) => void;
  setDetailWindow: (window: WindowKey) => void;
  setDetailMode: (mode: TokenDetailMode) => void;
  setSelectedBucketStartMs: (bucketStartMs: number | null) => void;
  setSelectedEventId: (eventId: string | null) => void;
  setPostRange: (range: TokenPostRange) => void;
  setPostSortMode: (mode: TokenPostSortMode) => void;
  setHideDuplicateClusters: (enabled: boolean) => void;
  setWatchedPostsOnly: (enabled: boolean) => void;
  setActiveView: (view: ActiveView) => void;
  setSignalLabStage: (stage: SignalLabStageFilter) => void;
  setSignalLabHorizon: (horizon: SignalLabHorizon) => void;
  setSignalLabAsset: (asset: string) => void;
  setSignalLabHandle: (handle: string) => void;
  setSignalLabSearch: (search: string) => void;
  setSignalLabInspectorTab: (tab: SignalLabInspectorTab) => void;
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
  detailWindow: "1h",
  detailMode: "compact",
  selectedBucketStartMs: null,
  selectedEventId: null,
  postRange: "current_window",
  postSortMode: "recent",
  hideDuplicateClusters: false,
  watchedPostsOnly: false,
  activeView: "live",
  signalLabStage: "all",
  signalLabHorizon: "6h",
  signalLabAsset: "",
  signalLabHandle: "",
  signalLabSearch: "",
  signalLabInspectorTab: "trace",
  setToken: (token) => set({ token }),
  setWindow: (window) => set({ window }),
  setScope: (scope) => set({ scope }),
  setHandles: (handles) => set({ handles }),
  setSearch: (search) => set({ search }),
  submitSearch: () => set({ submittedSearch: get().search.trim() }),
  runSearch: (search) => set({ search, submittedSearch: search.trim() }),
  setRadarSortMode: (radarSortMode) => set({ radarSortMode }),
  setDetailTab: (detailTab) => set({ detailTab }),
  setDetailWindow: (detailWindow) => set({ detailWindow }),
  setDetailMode: (detailMode) => set({ detailMode }),
  setSelectedBucketStartMs: (selectedBucketStartMs) => set({ selectedBucketStartMs }),
  setSelectedEventId: (selectedEventId) => set({ selectedEventId }),
  setPostRange: (postRange) => set({ postRange }),
  setPostSortMode: (postSortMode) => set({ postSortMode }),
  setHideDuplicateClusters: (hideDuplicateClusters) => set({ hideDuplicateClusters }),
  setWatchedPostsOnly: (watchedPostsOnly) => set({ watchedPostsOnly }),
  setActiveView: (activeView) => set({ activeView }),
  setSignalLabStage: (signalLabStage) => set({ signalLabStage }),
  setSignalLabHorizon: (signalLabHorizon) => set({ signalLabHorizon }),
  setSignalLabAsset: (signalLabAsset) => set({ signalLabAsset }),
  setSignalLabHandle: (signalLabHandle) => set({ signalLabHandle }),
  setSignalLabSearch: (signalLabSearch) => set({ signalLabSearch }),
  setSignalLabInspectorTab: (signalLabInspectorTab) => set({ signalLabInspectorTab })
}));
