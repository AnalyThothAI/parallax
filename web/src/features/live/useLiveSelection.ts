import { useEffect, useMemo, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import type { LivePayload, ScopeKey, SignalPulseItem, TokenFlowItem, WindowKey } from "../../api/types";
import type { MobileTask } from "../../components/MobileTaskNav";
import { targetRefFromTokenItem } from "../../domain/tokenTarget";
import { tokenKey } from "../../lib/format";
import { tokenForSearchQuery } from "../../lib/searchIntent";
import { useTraderStore } from "../../store/useTraderStore";
import { requiredMobileTaskForPathname } from "../cockpit/mobileRouteTask";
import { tapeItemId, type LiveSignalTapeItem } from "./liveTapeModel";

export type SelectedSignal =
  | { kind: "token"; key: string; item: TokenFlowItem }
  | { kind: "event"; item: LivePayload }
  | { kind: "pulse"; item: SignalPulseItem }
  | { kind: "query"; query: string }
  | null;

type UseLiveSelectionArgs = {
  compactSignalPulseItems: SignalPulseItem[];
  isSignalLabPulseFetching: boolean;
  scope: ScopeKey;
  tokenItems: TokenFlowItem[];
  windowKey: WindowKey;
};

export function useLiveSelection({
  compactSignalPulseItems,
  isSignalLabPulseFetching,
  scope,
  tokenItems,
  windowKey
}: UseLiveSelectionArgs) {
  const navigate = useNavigate();
  const location = useLocation();
  const isSignalLabRoute = location.pathname.startsWith("/signal-lab");
  const search = useTraderStore((state) => state.search);
  const detailTab = useTraderStore((state) => state.detailTab);
  const detailWindow = useTraderStore((state) => state.detailWindow);
  const detailMode = useTraderStore((state) => state.detailMode);
  const selectedBucketStartMs = useTraderStore((state) => state.selectedBucketStartMs);
  const selectedEventId = useTraderStore((state) => state.selectedEventId);
  const postRange = useTraderStore((state) => state.postRange);
  const postSortMode = useTraderStore((state) => state.postSortMode);
  const hideDuplicateClusters = useTraderStore((state) => state.hideDuplicateClusters);
  const watchedPostsOnly = useTraderStore((state) => state.watchedPostsOnly);
  const submitSearch = useTraderStore((state) => state.submitSearch);
  const setDetailTab = useTraderStore((state) => state.setDetailTab);
  const setDetailWindow = useTraderStore((state) => state.setDetailWindow);
  const setDetailMode = useTraderStore((state) => state.setDetailMode);
  const setSelectedBucketStartMs = useTraderStore((state) => state.setSelectedBucketStartMs);
  const setSelectedEventId = useTraderStore((state) => state.setSelectedEventId);
  const setPostRange = useTraderStore((state) => state.setPostRange);
  const setPostSortMode = useTraderStore((state) => state.setPostSortMode);
  const setHideDuplicateClusters = useTraderStore((state) => state.setHideDuplicateClusters);
  const setWatchedPostsOnly = useTraderStore((state) => state.setWatchedPostsOnly);
  const [selectedSignal, setSelectedSignal] = useState<SelectedSignal>(null);
  const [selectedTapeEventId, setSelectedTapeEventId] = useState<string | null>(null);
  const [mobileTask, setMobileTask] = useState<MobileTask>("radar");

  useEffect(() => {
    const requiredTask = requiredMobileTaskForPathname(location.pathname);
    if (requiredTask && mobileTask !== requiredTask) {
      setMobileTask(requiredTask);
    }
  }, [location.pathname, mobileTask]);

  useEffect(() => {
    if (!selectedSignal && tokenItems.length) {
      setSelectedSignal({ kind: "token", key: tokenKey(tokenItems[0]), item: tokenItems[0] });
      resetTokenDetail(windowKey);
    }
  }, [selectedSignal, tokenItems, windowKey]);

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
      resetTokenDetail(windowKey);
      return;
    }
    if (!latest) {
      setSelectedSignal(null);
    }
  }, [selectedSignal, tokenItems, windowKey]);

  useEffect(() => {
    if (selectedSignal?.kind !== "pulse") {
      return;
    }
    const latest = compactSignalPulseItems.find((item) => item.candidate_id === selectedSignal.item.candidate_id);
    if (latest && latest !== selectedSignal.item) {
      setSelectedSignal({ kind: "pulse", item: latest });
      return;
    }
    if (!latest && !isSignalLabPulseFetching) {
      setSelectedSignal(null);
    }
  }, [compactSignalPulseItems, isSignalLabPulseFetching, selectedSignal]);

  const selectedToken = selectedSignal?.kind === "token" ? latestTokenForSelection(selectedSignal, tokenItems) : null;
  const selectedTokenKey = selectedToken ? tokenKey(selectedToken) : null;
  const drawerTargetRef = targetRefFromTokenItem(selectedToken);
  const selectedPulseItemId = selectedSignal?.kind === "pulse" ? selectedSignal.item.candidate_id : null;
  const selectedPulseItem =
    selectedSignal?.kind === "pulse" ? latestPulseForSelection(selectedSignal.item, compactSignalPulseItems) : null;
  const selectedAccountEventId = selectedSignal?.kind === "event" ? selectedSignal.item.event.event_id : null;

  const selectToken = (item: TokenFlowItem, tapeId: string | null = null) => {
    setSelectedSignal({ kind: "token", key: tokenKey(item), item });
    resetTokenDetail(windowKey);
    setSelectedTapeEventId(tapeId);
    setMobileTask("detail");
  };

  const openTokenPage = (item: TokenFlowItem) => {
    const target = targetRefFromTokenItem(item);
    if (!target || !target.target_type || !target.target_id) {
      return;
    }
    setSelectedSignal({ kind: "token", key: tokenKey(item), item });
    setDetailWindow(windowKey);
    setMobileTask("radar");
    navigate(`/token/${target.target_type}/${encodeURIComponent(target.target_id)}?window=${windowKey}&scope=${scope}`);
  };

  const selectPulseItem = (item: SignalPulseItem, options: { openLab?: boolean } = {}) => {
    setSelectedSignal({ kind: "pulse", item });
    setSelectedTapeEventId(item.candidate_id);
    setMobileTask("detail");
    if (options.openLab) {
      navigate("/signal-lab");
      setMobileTask("lab");
    }
  };

  const selectAccountEvent = (item: LivePayload) => {
    setSelectedSignal({ kind: "event", item });
    setSelectedTapeEventId(item.event.event_id);
    setMobileTask("detail");
  };

  const submitEvidenceSearch = () => {
    const query = search.trim();
    const tokenMatch = tokenForSearchQuery(query, tokenItems);
    if (tokenMatch) {
      selectToken(tokenMatch);
      return;
    }
    if (isSignalLabRoute) {
      const next = new URLSearchParams(location.search);
      if (query) {
        next.set("q", query);
      } else {
        next.delete("q");
      }
      const queryString = next.toString();
      navigate("/signal-lab" + (queryString ? "?" + queryString : ""));
      setSelectedSignal(null);
      setSelectedTapeEventId(null);
      setMobileTask("lab");
      return;
    }
    submitSearch();
    setSelectedSignal(query ? { kind: "query", query } : null);
    setDetailMode("compact");
    setSelectedBucketStartMs(null);
    setSelectedEventId(null);
    setSelectedTapeEventId(null);
    setMobileTask(query ? "detail" : "radar");
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
      navigate("/");
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
    navigate("/signal-lab");
    setMobileTask("lab");
  };

  const detailAvailable = useMemo(() => Boolean(selectedSignal || selectedToken), [selectedSignal, selectedToken]);

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
    openTokenPage,
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
    watchedPostsOnly
  };

  function resetTokenDetail(nextWindow: WindowKey) {
    setDetailTab("timeline");
    setDetailWindow(nextWindow);
    setDetailMode("compact");
    setSelectedBucketStartMs(null);
    setSelectedEventId(null);
    setPostRange("current_window");
  }

  function onTimelineExit(tab: typeof detailTab) {
    if (tab !== "timeline") {
      setDetailMode("compact");
      setSelectedBucketStartMs(null);
      setSelectedEventId(null);
    }
  }
}

function latestTokenForSelection(signal: Extract<SelectedSignal, { kind: "token" }>, items: TokenFlowItem[]) {
  return items.find((item) => tokenKey(item) === signal.key) ?? null;
}

function latestPulseForSelection(selected: SignalPulseItem, items: SignalPulseItem[]): SignalPulseItem {
  return items.find((item) => item.candidate_id === selected.candidate_id) ?? selected;
}
