import { tokenKey } from "@lib/format";
import type {
  LivePayload,
  ScopeKey,
  SignalPulseItem,
  TokenFlowItem,
  WindowKey,
} from "@lib/types";
import { livePath, searchPath, signalLabPath } from "@shared/routing/paths";
import { searchWithOptionalPrefix } from "@shared/routing/searchParams";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";

import { targetRefFromTokenItem } from "../../domain/tokenTarget";
import { requiredMobileTaskForPathname } from "../cockpit/model/mobileRouteTask";
import type { MobileTask } from "../cockpit/model/mobileTask";
import { useCockpitStore } from "../cockpit/state/cockpitStore";
import { tokenSearchPath } from "../search/tokenSearchRoute";

import { tapeItemId, type LiveSignalTapeItem } from "./liveTapeModel";
import { useLiveSelectionStore } from "./state/liveSelectionSlice";

export type SelectedSignal =
  | { kind: "token"; key: string; item: TokenFlowItem }
  | { kind: "event"; item: LivePayload }
  | { kind: "pulse"; item: SignalPulseItem }
  | null;

type UseLiveSelectionArgs = {
  compactSignalPulseItems: SignalPulseItem[];
  signalPulseFetching: boolean;
  scope: ScopeKey;
  tokenItems: TokenFlowItem[];
  windowKey: WindowKey;
};

export function useLiveSelection({
  compactSignalPulseItems,
  signalPulseFetching,
  scope,
  tokenItems,
  windowKey,
}: UseLiveSelectionArgs) {
  const navigate = useNavigate();
  const location = useLocation();
  const isSignalLabRoute = location.pathname.startsWith("/signal-lab");
  const isTokenRadarRoute = location.pathname === "/";
  const suppressTokenDetailRoute =
    location.pathname.startsWith("/search") || location.pathname.startsWith("/stocks");
  const detailTab = useLiveSelectionStore((state) => state.detailTab);
  const detailWindow = useLiveSelectionStore((state) => state.detailWindow);
  const detailMode = useLiveSelectionStore((state) => state.detailMode);
  const selectedBucketStartMs = useLiveSelectionStore((state) => state.selectedBucketStartMs);
  const selectedEventId = useLiveSelectionStore((state) => state.selectedEventId);
  const postRange = useLiveSelectionStore((state) => state.postRange);
  const postSortMode = useLiveSelectionStore((state) => state.postSortMode);
  const hideDuplicateClusters = useLiveSelectionStore((state) => state.hideDuplicateClusters);
  const watchedPostsOnly = useLiveSelectionStore((state) => state.watchedPostsOnly);
  const setDetailTab = useLiveSelectionStore((state) => state.setDetailTab);
  const setDetailWindow = useLiveSelectionStore((state) => state.setDetailWindow);
  const setDetailMode = useLiveSelectionStore((state) => state.setDetailMode);
  const setSelectedBucketStartMs = useLiveSelectionStore((state) => state.setSelectedBucketStartMs);
  const setSelectedEventId = useLiveSelectionStore((state) => state.setSelectedEventId);
  const setPostRange = useLiveSelectionStore((state) => state.setPostRange);
  const setPostSortMode = useLiveSelectionStore((state) => state.setPostSortMode);
  const setHideDuplicateClusters = useLiveSelectionStore((state) => state.setHideDuplicateClusters);
  const setWatchedPostsOnly = useLiveSelectionStore((state) => state.setWatchedPostsOnly);
  const [selectedSignal, setSelectedSignal] = useState<SelectedSignal>(null);
  const [selectedTapeEventId, setSelectedTapeEventId] = useState<string | null>(null);
  const mobileTask = useCockpitStore((state) => state.mobileTask);
  const setMobileTask = useCockpitStore((state) => state.setMobileTask);

  const resetDetailPanel = useCallback(
    (nextWindow: WindowKey) => {
      setDetailTab("timeline");
      setDetailWindow(nextWindow);
      setDetailMode("compact");
      setSelectedBucketStartMs(null);
      setSelectedEventId(null);
      setPostRange("current_window");
    },
    [
      setDetailMode,
      setDetailTab,
      setDetailWindow,
      setPostRange,
      setSelectedBucketStartMs,
      setSelectedEventId,
    ],
  );

  useEffect(() => {
    const requiredTask = requiredMobileTaskForPathname(location.pathname);
    if (requiredTask && mobileTask !== requiredTask) {
      setMobileTask(requiredTask);
    }
  }, [location.pathname, mobileTask, setMobileTask]);

  useEffect(() => {
    if (!isTokenRadarRoute) {
      return;
    }
    if (!selectedSignal && tokenItems.length) {
      setSelectedSignal({ kind: "token", key: tokenKey(tokenItems[0]), item: tokenItems[0] });
      resetDetailPanel(windowKey);
    }
  }, [isTokenRadarRoute, resetDetailPanel, selectedSignal, tokenItems, windowKey]);

  useEffect(() => {
    if (selectedSignal?.kind !== "token") {
      return;
    }
    const latest = tokenItems.find((item) => tokenKey(item) === selectedSignal.key);
    if (latest && latest !== selectedSignal.item) {
      setSelectedSignal({ kind: "token", key: selectedSignal.key, item: latest });
      return;
    }
    if (!latest && tokenItems.length) {
      setSelectedSignal({ kind: "token", key: tokenKey(tokenItems[0]), item: tokenItems[0] });
      resetDetailPanel(windowKey);
      return;
    }
    if (!latest) {
      setSelectedSignal(null);
    }
  }, [resetDetailPanel, selectedSignal, tokenItems, windowKey]);

  useEffect(() => {
    if (selectedSignal?.kind !== "pulse") {
      return;
    }
    const latest = compactSignalPulseItems.find(
      (item) => item.candidate_id === selectedSignal.item.candidate_id,
    );
    if (latest && latest !== selectedSignal.item) {
      setSelectedSignal({ kind: "pulse", item: latest });
      return;
    }
    if (!latest && !signalPulseFetching) {
      setSelectedSignal(null);
    }
  }, [compactSignalPulseItems, selectedSignal, signalPulseFetching]);

  const selectedToken =
    !suppressTokenDetailRoute && selectedSignal?.kind === "token"
      ? latestTokenForSelection(selectedSignal, tokenItems)
      : null;
  const selectedTokenKey = selectedToken ? tokenKey(selectedToken) : null;
  const drawerTargetRef = targetRefFromTokenItem(selectedToken);
  const selectedPulseItemId =
    selectedSignal?.kind === "pulse" ? selectedSignal.item.candidate_id : null;
  const selectedPulseItem =
    selectedSignal?.kind === "pulse"
      ? latestPulseForSelection(selectedSignal.item, compactSignalPulseItems)
      : null;
  const selectedAccountEventId =
    selectedSignal?.kind === "event" ? selectedSignal.item.event.event_id : null;

  const selectToken = (item: TokenFlowItem, tapeId: string | null = null) => {
    setSelectedSignal({ kind: "token", key: tokenKey(item), item });
    resetDetailPanel(windowKey);
    setSelectedTapeEventId(tapeId);
    setMobileTask("detail");
  };

  const openTokenSearchPage = (item: TokenFlowItem) => {
    setSelectedSignal(null);
    setSelectedBucketStartMs(null);
    setSelectedEventId(null);
    setSelectedTapeEventId(null);
    setMobileTask("radar");
    navigate(tokenSearchPath(item, windowKey, scope));
  };

  const selectPulseItem = (item: SignalPulseItem, options: { openLab?: boolean } = {}) => {
    setSelectedSignal({ kind: "pulse", item });
    setSelectedTapeEventId(item.candidate_id);
    setMobileTask("detail");
    if (options.openLab) {
      navigate(signalLabPath());
      setMobileTask("lab");
    }
  };

  const selectAccountEvent = (item: LivePayload) => {
    setSelectedSignal({ kind: "event", item });
    setSelectedTapeEventId(item.event.event_id);
    setMobileTask("detail");
  };

  const submitEvidenceSearch = (searchText: string) => {
    const query = searchText.trim();
    if (isSignalLabRoute) {
      const next = new URLSearchParams(location.search);
      if (query) {
        next.set("q", query);
      } else {
        next.delete("q");
      }
      navigate({
        pathname: "/signal-lab",
        search: searchWithOptionalPrefix(next),
      });
      setSelectedSignal(null);
      setSelectedTapeEventId(null);
      setMobileTask("lab");
      return;
    }
    navigate(searchPath({ q: query, window: "24h", scope }));
    setSelectedSignal(null);
    setSelectedBucketStartMs(null);
    setSelectedEventId(null);
    setSelectedTapeEventId(null);
    setMobileTask("radar");
  };

  const handleTapeSelect = (item: LiveSignalTapeItem) => {
    const id = tapeItemId(item);
    setSelectedTapeEventId(id);
    if (item.kind === "token") {
      selectToken(item.token, id);
      return;
    }
    setSelectedSignal({ kind: "event", item: item.payload });
    setMobileTask("detail");
  };

  const handleMobileTaskChange = (task: MobileTask) => {
    setMobileTask(task);
    if (task === "radar" || task === "tape") {
      navigate(livePath());
    }
  };

  const handleDetailTabChange = (tab: typeof detailTab) => {
    onTimelineExit(tab);
    setDetailTab(tab);
  };

  const handleDetailWindowChange = (window: typeof detailWindow) => {
    setDetailWindow(window);
    setDetailMode("compact");
    setSelectedBucketStartMs(null);
    setSelectedEventId(null);
  };

  const handleTimelineBucketSelect = (bucketStartMs: number) => {
    setDetailTab("timeline");
    setSelectedBucketStartMs(bucketStartMs);
    setSelectedEventId(null);
    setDetailMode("replay");
  };

  const handleTimelineBack = () => {
    setDetailMode("compact");
    setSelectedEventId(null);
  };

  const onOpenLab = () => {
    navigate(signalLabPath());
    setMobileTask("lab");
  };

  const detailAvailable = useMemo(
    () => !suppressTokenDetailRoute && Boolean(selectedSignal || selectedToken),
    [selectedSignal, selectedToken, suppressTokenDetailRoute],
  );

  return {
    detailAvailable,
    detailMode,
    detailTab,
    detailWindow,
    drawerTargetRef,
    handleDetailTabChange,
    handleDetailWindowChange,
    handleMobileTaskChange,
    handleTapeSelect,
    handleTimelineBack,
    handleTimelineBucketSelect,
    hideDuplicateClusters,
    mobileTask,
    onOpenLab,
    openTokenSearchPage,
    postRange,
    postSortMode,
    selectAccountEvent,
    selectPulseItem,
    selectToken,
    selectedAccountEventId,
    selectedBucketStartMs,
    selectedEventId,
    selectedPulseItem,
    selectedPulseItemId,
    selectedSignal,
    selectedTapeEventId,
    selectedToken,
    selectedTokenKey,
    setHideDuplicateClusters,
    setMobileTask,
    setPostRange,
    setPostSortMode,
    setSelectedEventId,
    setWatchedPostsOnly,
    submitEvidenceSearch,
    watchedPostsOnly,
  };

  function onTimelineExit(tab: typeof detailTab) {
    if (tab !== "timeline") {
      setDetailMode("compact");
      setSelectedBucketStartMs(null);
      setSelectedEventId(null);
    }
  }
}

function latestTokenForSelection(
  signal: Extract<SelectedSignal, { kind: "token" }>,
  items: TokenFlowItem[],
) {
  return items.find((item) => tokenKey(item) === signal.key) ?? null;
}

function latestPulseForSelection(
  selected: SignalPulseItem,
  items: SignalPulseItem[],
): SignalPulseItem {
  return items.find((item) => item.candidate_id === selected.candidate_id) ?? selected;
}
