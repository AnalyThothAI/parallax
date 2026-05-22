import type { AppSession } from "@app/useAppSession";
import { createContext, useContext } from "react";

export const AppRouteSessionContext = createContext<AppSession | null>(null);

export function useAppRouteSession(): AppSession {
  const session = useContext(AppRouteSessionContext);
  if (!session) {
    throw new Error("App route session is not available.");
  }
  return session;
}
