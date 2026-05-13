import type {
  TokenDetailMode,
  TokenDetailTab,
  TokenPostRange,
  TokenPostSortMode,
  WindowKey,
} from "@lib/types";
import { create } from "zustand";

type LiveSelectionState = {
  detailTab: TokenDetailTab;
  detailWindow: WindowKey;
  detailMode: TokenDetailMode;
  selectedBucketStartMs: number | null;
  selectedEventId: string | null;
  postRange: TokenPostRange;
  postSortMode: TokenPostSortMode;
  hideDuplicateClusters: boolean;
  watchedPostsOnly: boolean;
  setDetailTab: (tab: TokenDetailTab) => void;
  setDetailWindow: (window: WindowKey) => void;
  setDetailMode: (mode: TokenDetailMode) => void;
  setSelectedBucketStartMs: (bucketStartMs: number | null) => void;
  setSelectedEventId: (eventId: string | null) => void;
  setPostRange: (range: TokenPostRange) => void;
  setPostSortMode: (mode: TokenPostSortMode) => void;
  setHideDuplicateClusters: (enabled: boolean) => void;
  setWatchedPostsOnly: (enabled: boolean) => void;
};

export const useLiveSelectionStore = create<LiveSelectionState>((set) => ({
  detailTab: "timeline",
  detailWindow: "1h",
  detailMode: "compact",
  selectedBucketStartMs: null,
  selectedEventId: null,
  postRange: "current_window",
  postSortMode: "recent",
  hideDuplicateClusters: false,
  watchedPostsOnly: false,
  setDetailTab: (detailTab) => set({ detailTab }),
  setDetailWindow: (detailWindow) => set({ detailWindow }),
  setDetailMode: (detailMode) => set({ detailMode }),
  setSelectedBucketStartMs: (selectedBucketStartMs) => set({ selectedBucketStartMs }),
  setSelectedEventId: (selectedEventId) => set({ selectedEventId }),
  setPostRange: (postRange) => set({ postRange }),
  setPostSortMode: (postSortMode) => set({ postSortMode }),
  setHideDuplicateClusters: (hideDuplicateClusters) => set({ hideDuplicateClusters }),
  setWatchedPostsOnly: (watchedPostsOnly) => set({ watchedPostsOnly }),
}));
