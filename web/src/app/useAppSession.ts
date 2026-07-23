import { getBootstrap, setAuthToken } from "@lib/api/client";
import { queryKeys } from "@shared/query/queryKeys";
import { useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";

export function useAppSession() {
  const [token, setToken] = useState("");
  const bootstrapQuery = useQuery({
    queryKey: queryKeys.bootstrap(),
    queryFn: getBootstrap,
    staleTime: Infinity,
  });

  useEffect(() => {
    const wsToken = bootstrapQuery.data?.data.ws_token;
    if (!wsToken) return;
    setAuthToken(wsToken);
    setToken(wsToken);
  }, [bootstrapQuery.data?.data.ws_token]);

  return useMemo(
    () => ({
      bootstrapError: bootstrapQuery.isError,
      bootstrapHandles: bootstrapQuery.data?.data.handles ?? [],
      bootstrapLoading: bootstrapQuery.isPending,
      token,
    }),
    [
      bootstrapQuery.data?.data.handles,
      bootstrapQuery.isError,
      bootstrapQuery.isPending,
      token,
    ],
  );
}

export type AppSession = ReturnType<typeof useAppSession>;
