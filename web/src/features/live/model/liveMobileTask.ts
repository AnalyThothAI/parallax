export type LiveMobileTask = "radar" | "tape" | "lab";

export function requiredLiveMobileTaskForPathname(pathname: string): LiveMobileTask | null {
  const routeRoot = pathname.split("/").filter(Boolean)[0] ?? "";
  if (routeRoot === "token") {
    return "radar";
  }
  return null;
}
