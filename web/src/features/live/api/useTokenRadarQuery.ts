import { getApi } from "@lib/api/client";
import type { AssetFlowData, ScopeKey, WindowKey } from "@lib/types";
import type { TokenRadarVenueFilter } from "@lib/venue";
import { queryKeys } from "@shared/query/queryKeys";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useRef } from "react";

import {
  radarIdentityKey,
  radarResponseMatchesIdentity,
  type RadarQueryIdentity,
} from "../model/radarContentStatus";

export function useTokenRadarQuery({
  token,
  window,
  scope,
  venue,
  limit = 48,
  enabled = true,
}: {
  token: string;
  window: WindowKey;
  scope: ScopeKey;
  venue: TokenRadarVenueFilter;
  limit?: number;
  enabled?: boolean;
}) {
  const identity: RadarQueryIdentity = { scope, venue, window };
  const identityKey = radarIdentityKey(identity);
  const successfulHttpReads = useRef(new Map<string, number>());
  const query = useQuery({
    queryKey: queryKeys.tokenRadar(window, scope, venue, limit),
    queryFn: async () => {
      const response = await getApi<AssetFlowData>("/api/token-radar", {
        token,
        params: { window, limit, scope, venue },
      });
      if (radarResponseMatchesIdentity(response.data, identity)) {
        successfulHttpReads.current.set(identityKey, Date.now());
      }
      return response;
    },
    enabled: Boolean(token) && enabled,
    refetchInterval: 10_000,
    placeholderData: keepPreviousData,
  });
  return {
    ...query,
    lastSuccessfulHttpAtMs: successfulHttpReads.current.get(identityKey) ?? null,
  };
}
