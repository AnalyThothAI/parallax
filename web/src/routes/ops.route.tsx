import { OpsDiagnosticsPage, useOpsDiagnosticsQuery, useOpsQueueQuery } from "@features/ops";
import { useState } from "react";

import { useShellRouteContext } from "./shellRouteContext";

export function Component() {
  const { scope, token, windowKey } = useShellRouteContext();
  const [selectedQueueName, setSelectedQueueName] = useState<string | null>(null);
  const diagnosticsQuery = useOpsDiagnosticsQuery({
    scope,
    token,
    window: windowKey,
  });
  const queueQuery = useOpsQueueQuery({
    enabled: Boolean(selectedQueueName),
    queueName: selectedQueueName,
    token,
  });

  return (
    <OpsDiagnosticsPage
      diagnostics={diagnosticsQuery.data?.data ?? null}
      error={diagnosticsQuery.error}
      loading={diagnosticsQuery.isPending}
      queue={queueQuery.data?.data ?? null}
      queueLoading={queueQuery.isPending && Boolean(selectedQueueName)}
      selectedQueueName={selectedQueueName}
      onRefresh={() => void diagnosticsQuery.refetch()}
      onSelectQueue={setSelectedQueueName}
    />
  );
}
