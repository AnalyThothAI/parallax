import type { ScopeKey, WindowKey } from "@lib/types";

import type { SearchRouteState } from "../state/searchRouteState";

const WINDOW_OPTIONS: WindowKey[] = ["5m", "1h", "4h", "24h"];
const SCOPE_OPTIONS: ScopeKey[] = ["all", "matched"];

type SearchIntelControlsProps = {
  routeState: SearchRouteState;
  onRouteChange: (patch: Partial<SearchRouteState>) => void;
};

export function SearchIntelControls({ routeState, onRouteChange }: SearchIntelControlsProps) {
  return (
    <div className="search-intel-controls" aria-label="Search Intel controls">
      <section>
        <span>window</span>
        <div className="search-segmented" role="group" aria-label="search window">
          {WINDOW_OPTIONS.map((window) => (
            <button
              aria-pressed={routeState.window === window}
              className={routeState.window === window ? "active" : ""}
              key={window}
              onClick={() => onRouteChange({ window })}
              type="button"
            >
              {window}
            </button>
          ))}
        </div>
      </section>

      <section>
        <span>scope</span>
        <div className="search-segmented two" role="group" aria-label="search scope">
          {SCOPE_OPTIONS.map((scope) => (
            <button
              aria-pressed={routeState.scope === scope}
              className={routeState.scope === scope ? "active" : ""}
              key={scope}
              onClick={() => onRouteChange({ scope })}
              type="button"
            >
              {scope}
            </button>
          ))}
        </div>
      </section>
    </div>
  );
}
