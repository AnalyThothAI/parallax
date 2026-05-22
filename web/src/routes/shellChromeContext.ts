import { createContext, useContext } from "react";

import type { ShellChromeData } from "./shellChromeData";

export const ShellChromeContext = createContext<ShellChromeData | null>(null);

export function useShellChrome(): ShellChromeData {
  const chrome = useContext(ShellChromeContext);
  if (!chrome) {
    throw new Error("Shell chrome data is not available.");
  }
  return chrome;
}
