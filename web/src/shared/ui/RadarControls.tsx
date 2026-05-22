import { OBSERVATION_WINDOWS } from "@lib/observationWindows";
import type { ScopeKey, WindowKey } from "@lib/types";

import { HandleFilter } from "./HandleFilter";
import { ToggleGroup, ToggleGroupItem } from "./toggle-group";
import "./RadarControls.css";

type RadarControlsProps = {
  windowKey: WindowKey;
  scope: ScopeKey;
  handles?: string;
  handlePlaceholder?: string;
  onWindowChange: (window: WindowKey) => void;
  onScopeChange: (scope: ScopeKey) => void;
  onHandlesChange?: (handles: string) => void;
};

export function RadarControls({
  windowKey,
  scope,
  handles,
  handlePlaceholder = "handles",
  onWindowChange,
  onScopeChange,
  onHandlesChange,
}: RadarControlsProps) {
  const handleWindowChange = (nextWindow: string) => {
    if (!nextWindow) {
      return;
    }
    if (!OBSERVATION_WINDOWS.includes(nextWindow as WindowKey)) {
      return;
    }
    onWindowChange(nextWindow as WindowKey);
  };

  const handleScopeChange = (nextScope: string) => {
    if (!nextScope) {
      return;
    }
    if (nextScope !== "matched" && nextScope !== "all") {
      return;
    }
    onScopeChange(nextScope);
  };

  return (
    <>
      <ToggleGroup
        aria-label="radar window"
        className="radar-controls-group radar-controls-window"
        onValueChange={handleWindowChange}
        type="single"
        value={windowKey}
      >
        {OBSERVATION_WINDOWS.map((item) => (
          <ToggleGroupItem className="radar-controls-item" key={item} value={item}>
            {item}
          </ToggleGroupItem>
        ))}
      </ToggleGroup>
      <ToggleGroup
        aria-label="token flow scope"
        className="radar-controls-group radar-controls-scope"
        onValueChange={handleScopeChange}
        type="single"
        value={scope}
      >
        <ToggleGroupItem className="radar-controls-item" value="matched">
          watched
        </ToggleGroupItem>
        <ToggleGroupItem className="radar-controls-item" value="all">
          all
        </ToggleGroupItem>
      </ToggleGroup>
      {onHandlesChange ? (
        <HandleFilter
          ariaLabel="radar handles"
          placeholder={handlePlaceholder}
          value={handles ?? ""}
          onChange={onHandlesChange}
        />
      ) : null}
    </>
  );
}
