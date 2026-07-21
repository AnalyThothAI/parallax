import { getApi } from "@lib/api/client";
import { queryKeys } from "@shared/query/queryKeys";
import { useQuery } from "@tanstack/react-query";

import type { OpsDiagnostics, OpsQueueData } from "../model/opsDiagnostics";

export function useOpsDiagnosticsQuery({ token }: { token: string }) {
  return useQuery({
    queryKey: queryKeys.opsDiagnostics(),
    queryFn: () => getApi<OpsDiagnostics>("/api/ops/diagnostics", { token }),
    enabled: Boolean(token),
    refetchInterval: 12_000,
  });
}

export function useOpsQueueQuery({
  enabled,
  limit = 50,
  queueName,
  status,
  token,
}: {
  enabled: boolean;
  limit?: number;
  queueName: string | null;
  status?: string | null;
  token: string;
}) {
  return useQuery({
    queryKey: queryKeys.opsQueue(queueName, status ?? null, limit),
    queryFn: () =>
      getApi<OpsQueueData>(`/api/ops/queues/${encodeURIComponent(queueName ?? "")}`, {
        params: { limit, status },
        token,
      }),
    enabled: Boolean(token && queueName && enabled),
    refetchInterval: 12_000,
  });
}
