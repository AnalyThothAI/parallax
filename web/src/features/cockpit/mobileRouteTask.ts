import type { MobileTask } from "../../components/MobileTaskNav";

export function requiredMobileTaskForPathname(pathname: string): MobileTask | null {
  if (pathname.startsWith("/signal-lab")) {
    return "lab";
  }
  if (pathname.startsWith("/token/")) {
    return "radar";
  }
  return null;
}
