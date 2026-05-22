import { ErrorBoundary } from "@shared/ui/ErrorBoundary";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import React from "react";

import { CockpitApp } from "./CockpitApp";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: false,
      retry: 1,
      staleTime: 8_000,
    },
  },
});

export function AppRoot() {
  return (
    <React.StrictMode>
      <ErrorBoundary>
        <QueryClientProvider client={queryClient}>
          <CockpitApp />
        </QueryClientProvider>
      </ErrorBoundary>
    </React.StrictMode>
  );
}
