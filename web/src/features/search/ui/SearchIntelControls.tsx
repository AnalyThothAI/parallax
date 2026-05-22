import type { ScopeKey, WindowKey } from "@lib/types";
import { ToggleGroup, ToggleGroupItem } from "@shared/ui/toggle-group";

import type { SearchRouteState } from "../state/searchRouteState";

const WINDOW_OPTIONS: WindowKey[] = ["5m", "1h", "4h", "24h"];
const SCOPE_OPTIONS: ScopeKey[] = ["all", "matched"];

type SearchIntelControlsProps = {
  routeState: SearchRouteState;
  onRouteChange: (patch: Partial<SearchRouteState>) => void;
};

export function SearchIntelControls({ routeState, onRouteChange }: SearchIntelControlsProps) {
  const handleWindowChange = (nextWindow: string) => {
    if (!nextWindow) {
      return;
    }
    if (!WINDOW_OPTIONS.includes(nextWindow as WindowKey)) {
      return;
    }
    onRouteChange({ window: nextWindow as WindowKey });
  };

  const handleScopeChange = (nextScope: string) => {
    if (!nextScope) {
      return;
    }
    if (!SCOPE_OPTIONS.includes(nextScope as ScopeKey)) {
      return;
    }
    onRouteChange({ scope: nextScope as ScopeKey });
  };

  return (
    <div className="search-intel-controls" aria-label="Search Intel controls">
      <section>
        <span>window</span>
        <ToggleGroup
          aria-label="search window"
          className="search-segmented"
          onValueChange={handleWindowChange}
          type="single"
          value={routeState.window}
        >
          {WINDOW_OPTIONS.map((window) => (
            <ToggleGroupItem className="search-segmented-item" key={window} value={window}>
              {window}
            </ToggleGroupItem>
          ))}
        </ToggleGroup>
      </section>

      <section>
        <span>scope</span>
        <ToggleGroup
          aria-label="search scope"
          className="search-segmented two"
          onValueChange={handleScopeChange}
          type="single"
          value={routeState.scope}
        >
          {SCOPE_OPTIONS.map((scope) => (
            <ToggleGroupItem className="search-segmented-item" key={scope} value={scope}>
              {scope}
            </ToggleGroupItem>
          ))}
        </ToggleGroup>
      </section>
    </div>
  );
}
