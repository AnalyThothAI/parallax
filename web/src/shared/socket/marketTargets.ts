import type { MarketTargetRef, NormalizedMarketTarget } from "./socketTypes";

export function normalizeMarketTargets(values: MarketTargetRef[]): NormalizedMarketTarget[] {
  const seen = new Set<string>();
  const targets = [];
  for (const value of values) {
    const targetType = String(value.target_type ?? "").trim();
    const targetId = String(value.target_id ?? "").trim();
    if (!targetType || !targetId) {
      continue;
    }
    const key = targetKey({ target_type: targetType, target_id: targetId });
    if (seen.has(key)) {
      continue;
    }
    seen.add(key);
    targets.push({ target_type: targetType, target_id: targetId });
  }
  return targets.sort((left, right) => targetKey(left).localeCompare(targetKey(right)));
}

export function targetKey(target: NormalizedMarketTarget): string {
  return `${target.target_type}:${target.target_id}`;
}

export function targetFromKey(key: string): NormalizedMarketTarget | null {
  const separator = key.indexOf(":");
  if (separator < 0) {
    return null;
  }
  return {
    target_type: key.slice(0, separator),
    target_id: key.slice(separator + 1),
  };
}

export function isTarget(value: NormalizedMarketTarget | null): value is NormalizedMarketTarget {
  return Boolean(value?.target_type && value.target_id);
}
