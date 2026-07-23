import type { ReactNode } from "react";
import { Outlet } from "react-router-dom";

import "./live.css";

type LivePageProps = {
  children?: ReactNode;
};

/**
 * LivePage gives the route-owned Token Radar the full available research surface.
 */
export function LivePage({ children }: LivePageProps) {
  return (
    <div className="live-page" data-page-archetype="scan" data-testid="live-page">
      {children ?? <Outlet />}
    </div>
  );
}
