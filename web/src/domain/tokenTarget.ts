import type { TokenFlowItem } from "@lib/types";

export type TargetRef = {
  target_type: "Asset" | "CexToken";
  target_id: string;
};

export function targetRefFromTokenItem(item: TokenFlowItem | null | undefined): TargetRef | null {
  const targetType = item?.identity.target_type;
  const targetId = item?.identity.target_id;
  if ((targetType !== "Asset" && targetType !== "CexToken") || !targetId) {
    return null;
  }
  return { target_type: targetType, target_id: targetId };
}

export function targetRefKey(ref: TargetRef): string {
  return `${ref.target_type}:${ref.target_id}`;
}

export function targetRefEquals(
  left: TargetRef | null | undefined,
  right: TargetRef | null | undefined,
): boolean {
  if (!left || !right) {
    return false;
  }
  return left.target_type === right.target_type && left.target_id === right.target_id;
}

export function isDexMarket(item: TokenFlowItem): boolean {
  return item.identity.venue_type === "dex" || item.identity.target_type === "Asset";
}
