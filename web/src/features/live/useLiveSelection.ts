import { requiredMobileTaskForPathname, useCockpitStore, type MobileTask } from "@features/cockpit";
import { tokenSearchPath } from "@features/search";
import type { LivePayload, ScopeKey, SignalPulseItem, TokenFlowItem, WindowKey } from "@lib/types";
import {
  livePath,
  searchPath,
  signalLabPath,
  signalLabPulsePath,
  tokenTargetPath,
} from "@shared/routing/paths";
import { searchWithOptionalPrefix } from "@shared/routing/searchParams";
import { useEffect, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";

import { targetRefFromTokenItem } from "../../domain/tokenTarget";

import { tapeItemId, type LiveSignalTapeItem } from "./liveTapeModel";

export type SelectedSignal =
  | { kind: "event"; item: LivePayload }
  | { kind: "pulse"; item: SignalPulseItem }
  | null;

type UseLiveSelectionArgs = {
  scope: ScopeKey;
  windowKey: WindowKey;
};

export function useLiveSelection({ scope, windowKey }: UseLiveSelectionArgs) {
  const navigate = useNavigate();
  const location = useLocation();
  const isSignalLabRoute = location.pathname.startsWith("/signal-lab");
  const [selectedSignal, setSelectedSignal] = useState<SelectedSignal>(null);
  const [selectedTapeEventId, setSelectedTapeEventId] = useState<string | null>(null);
  const mobileTask = useCockpitStore((state) => state.mobileTask);
  const setMobileTask = useCockpitStore((state) => state.setMobileTask);

  useEffect(() => {
    const requiredTask = requiredMobileTaskForPathname(location.pathname);
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
    const target = targetRefFromTokenItem(item);
    if (!target) {
      navigate(tokenSearchPath(item, windowKey, scope));
      return;
    }
    navigate(
      tokenTargetPath({
        targetId: target.target_id,
        targetType: target.target_type,
        scope,
        window: windowKey,
      }),
    );
  };

  const openTokenSearchPage = (item: TokenFlowItem) => {
    setSelectedSignal(null);
    setSelectedTapeEventId(null);
    setMobileTask("radar");
    navigate(tokenSearchPath(item, windowKey, scope));
  };

  const selectPulseItem = (item: SignalPulseItem) => {
    setSelectedSignal({ kind: "pulse", item });
    setSelectedTapeEventId(item.candidate_id);
    setMobileTask("lab");
    navigate(item.candidate_id ? signalLabPulsePath(item.candidate_id) : signalLabPath());
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

  const handleMobileTaskChange = (task: MobileTask) => {
    setMobileTask(task);
    if (task === "radar" || task === "tape") {
      navigate(livePath());
    }
  };

  const onOpenLab = () => {
    navigate(signalLabPath());
    setMobileTask("lab");
  };

  return {
    handleMobileTaskChange,
    handleTapeSelect,
    mobileTask,
    onOpenLab,
    openTokenSearchPage,
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
