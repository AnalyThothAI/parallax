import { tokenSearchPath } from "@features/search";
import type { ScopeKey, TokenFlowItem, WindowKey } from "@lib/types";
import { tokenTargetPath } from "@shared/routing/paths";

import { targetRefFromTokenItem } from "../../../domain/tokenTarget";

const TOKEN_RADAR_DETAIL_WINDOW: WindowKey = "24h";
const TOKEN_RADAR_DETAIL_TARGET = "_blank";
const TOKEN_RADAR_DETAIL_FEATURES = "noopener,noreferrer";

export function tokenRadarDetailHref(item: TokenFlowItem, scope: ScopeKey): string {
  const target = targetRefFromTokenItem(item);
  if (!target) {
    return tokenSearchPath(item, TOKEN_RADAR_DETAIL_WINDOW, scope);
  }
  return tokenTargetPath({
    targetId: target.target_id,
    targetType: target.target_type,
    scope,
    window: TOKEN_RADAR_DETAIL_WINDOW,
  });
}

export function openTokenRadarDetailInNewTab(href: string): void {
  window.open(href, TOKEN_RADAR_DETAIL_TARGET, TOKEN_RADAR_DETAIL_FEATURES);
}

export const tokenRadarDetailLinkProps = {
  rel: "noopener noreferrer",
  target: TOKEN_RADAR_DETAIL_TARGET,
} as const;
