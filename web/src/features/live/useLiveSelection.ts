import { tokenSearchPath } from "@features/search";
import type { LivePayload, ScopeKey, SignalPulseItem, TokenFlowItem, WindowKey } from "@lib/types";
import { livePath, searchPath, signalLabPulsePath, tokenTargetPath } from "@shared/routing/paths";
import { searchWithOptionalPrefix } from "@shared/routing/searchParams";
import { useEffect, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";

import { targetRefFromTokenItem } from "../../domain/tokenTarget";

import { tapeItemId, type LiveSignalTapeItem } from "./liveTapeModel";
import { requiredLiveMobileTaskForPathname, type LiveMobileTask } from "./model/liveMobileTask";
import { useLiveTaskStore } from "./state/liveTaskStore";

export type SelectedSignal =
  | { kind: "event"; item: LivePayload }
  | { kind: "pulse"; item: SignalPulseItem }
  | null;

type UseLiveSelectionArgs = {
  scope: ScopeKey;
};

export function useLiveSelection({ scope }: UseLiveSelectionArgs) {
  const navigate = useNavigate();
  const location = useLocation();
  const isSignalLabRoute = location.pathname.startsWith("/signal-lab");
  const [selectedSignal, setSelectedSignal] = useState<SelectedSignal>(null);
  const [selectedTapeEventId, setSelectedTapeEventId] = useState<string | null>(null);
  const mobileTask = useLiveTaskStore((state) => state.mobileTask);
  const setMobileTask = useLiveTaskStore((state) => state.setMobileTask);

  useEffect(() => {
    const requiredTask = requiredLiveMobileTaskForPathname(location.pathname);
    if (requiredTask && mobileTask !== requiredTask) {
      setMobileTask(requiredTask);
    }
  }, [location.pathname, mobileTask, setMobileTask]);

  const selectedPulseItemId =
    selectedSignal?.kind === "pulse" ? selectedSignal.item.candidate_id : null;
  const selectedAccountEventId =
    selectedSignal?.kind === "event" ? selectedSignal.item.event.event_id : null;

  const selectToken = (item: TokenFlowItem, tapeId: string | null = null) => {
    setSelectedSignal(null);
    setSelectedTapeEventId(tapeId);
    setMobileTask("radar");
    const detailWindow: WindowKey = "24h";
    const target = targetRefFromTokenItem(item);
    if (!target) {
      navigate(tokenSearchPath(item, detailWindow, scope));
      return;
    }
    navigate(
      tokenTargetPath({
        targetId: target.target_id,
        targetType: target.target_type,
        scope,
        window: detailWindow,
      }),
    );
  };

  const selectPulseItem = (item: SignalPulseItem) => {
    setSelectedSignal({ kind: "pulse", item });
    setSelectedTapeEventId(item.candidate_id);
    setMobileTask("lab");
    const search = item.display_status?.startsWith("hidden_") ? "?visibility=hidden" : "";
    navigate(signalLabPulsePath(item.candidate_id, search));
  };

  const selectAccountEvent = (item: LivePayload) => {
    setSelectedSignal({ kind: "event", item });
    setSelectedTapeEventId(item.event.event_id);
    setMobileTask("lab");
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
    setMobileTask("tape");
  };

  const handleMobileTaskChange = (task: LiveMobileTask) => {
    setMobileTask(task);
    if (task === "radar" || task === "tape") {
      navigate(livePath());
    }
  };

  return {
    handleMobileTaskChange,
    handleTapeSelect,
    mobileTask,
    selectAccountEvent,
    selectPulseItem,
    selectToken,
    selectedAccountEventId,
    selectedPulseItemId,
    selectedSignal,
    selectedTapeEventId,
    setMobileTask,
    submitEvidenceSearch,
  };
}
