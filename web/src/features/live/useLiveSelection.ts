import type { ScopeKey, TokenFlowItem, WindowKey } from "@lib/types";
import { tokenTargetPath } from "@shared/routing/paths";
import { tokenSearchPath } from "@shared/routing/tokenSearch";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { targetRefFromTokenItem } from "../../domain/tokenTarget";

import { tapeItemId, type LiveSignalTapeItem } from "./liveTapeModel";
import type { LiveMobileTask } from "./model/liveMobileTask";

type UseLiveSelectionArgs = {
  scope: ScopeKey;
};

export function useLiveSelection({ scope }: UseLiveSelectionArgs) {
  const navigate = useNavigate();
  const [selectedTapeEventId, setSelectedTapeEventId] = useState<string | null>(null);
  const [mobileTask, setMobileTask] = useState<LiveMobileTask>("radar");

  const selectToken = (item: TokenFlowItem, tapeId: string | null = null) => {
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

  const handleTapeSelect = (item: LiveSignalTapeItem) => {
    const id = tapeItemId(item);
    setSelectedTapeEventId(id);
    if (item.kind === "token") {
      selectToken(item.token, id);
      return;
    }
    setMobileTask("tape");
  };

  const handleMobileTaskChange = (task: LiveMobileTask) => {
    setMobileTask(task);
  };

  return {
    handleMobileTaskChange,
    handleTapeSelect,
    mobileTask,
    selectToken,
    selectedTapeEventId,
  };
}
