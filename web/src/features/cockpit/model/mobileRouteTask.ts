import type { MobileTask } from "./mobileTask";

export function requiredMobileTaskForPathname(pathname: string): MobileTask | null {
  const routeRoot = pathname.split("/").filter(Boolean)[0] ?? "";
  if (routeRoot === "signal-lab") {
    return "lab";
  }
  if (routeRoot === "token") {
    return "radar";
  }
  return null;
}
