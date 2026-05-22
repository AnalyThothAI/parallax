import { SearchIntelPage } from "@features/search";

import { useShellRouteContext } from "./shellRouteContext";

export function Component() {
  const { token } = useShellRouteContext();

  return <SearchIntelPage token={token} />;
}
