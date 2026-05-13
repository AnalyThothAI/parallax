import type { RadarSortMode, ScopeKey, TokenPostRange, TokenPostSortMode, WindowKey } from "@lib/types";

import { compactSearch } from "./searchParams";

export function livePath(params: {
  window?: WindowKey;
  scope?: ScopeKey;
  handles?: string;
  sort?: RadarSortMode;
} = {}): string {
  const search = compactSearch(params);
  return "/" + (search ? `?${search}` : "");
}

export function searchPath({
  q,
  window = "24h",
  scope = "all",
}: {
  q: string;
  window?: WindowKey;
  scope?: ScopeKey;
}): string {
  const search = compactSearch({ q, window, scope });
  return "/search" + (search ? `?${search}` : "");
}

export function signalLabPath(params: { q?: string | null; handle?: string | null } = {}): string {
  const search = compactSearch(params);
  return "/signal-lab" + (search ? `?${search}` : "");
}

export function signalLabPulsePath(candidateId: string, search = ""): string {
  return `/signal-lab/pulse/${encodeURIComponent(candidateId)}${search}`;
}

export function stocksPath({
  window = "1h",
  scope = "all",
}: {
  window?: WindowKey;
  scope?: ScopeKey;
} = {}): string {
  const search = compactSearch({ window, scope });
  return "/stocks" + (search ? `?${search}` : "");
}

export function tokenTargetPath({
  targetType,
  targetId,
  window = "1h",
  scope = "all",
  tab,
  postRange,
  postSort,
}: {
  targetType: string;
  targetId: string;
  window?: WindowKey;
  scope?: ScopeKey;
  tab?: string;
  postRange?: TokenPostRange;
  postSort?: TokenPostSortMode;
}): string {
  const search = compactSearch({ window, scope, tab, postRange, postSort });
  return `/token/${encodeURIComponent(targetType)}/${encodeURIComponent(targetId)}${
    search ? `?${search}` : ""
  }`;
}
