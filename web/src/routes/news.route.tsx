import { NewsPage } from "@features/news";
import { useParams } from "react-router-dom";

import { useShellRouteContext } from "./shellRouteContext";

export function Component() {
  const { token } = useShellRouteContext();
  const { newsItemId } = useParams();
  return <NewsPage newsItemId={newsItemId ?? null} token={token} />;
}
