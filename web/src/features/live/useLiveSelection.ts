import type { ScopeKey, TokenFlowItem, WindowKey } from "@lib/types";
import { tokenTargetPath } from "@shared/routing/paths";
import { tokenSearchPath } from "@shared/routing/tokenSearch";
import { useNavigate } from "react-router-dom";

import { targetRefFromTokenItem } from "../../domain/tokenTarget";

type UseLiveSelectionArgs = {
  scope: ScopeKey;
};

export function useLiveSelection({ scope }: UseLiveSelectionArgs) {
  const navigate = useNavigate();

  const selectToken = (item: TokenFlowItem) => {
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

  return { selectToken };
}
