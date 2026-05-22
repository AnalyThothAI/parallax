import { OBSERVATION_WINDOWS } from "@lib/observationWindows";
import type { ScopeKey, WindowKey } from "@lib/types";

import { HandleFilter } from "./HandleFilter";
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
  return (
    <>
      <div className="radar-controls-group radar-controls-window" aria-label="radar window">
        {OBSERVATION_WINDOWS.map((item) => (
          <button
            key={item}
            className={item === windowKey ? "active" : ""}
            onClick={() => onWindowChange(item)}
            type="button"
          >
            {item}
          </button>
        ))}
      </div>
      <div className="radar-controls-group radar-controls-scope" aria-label="token flow scope">
        <button
          className={scope === "matched" ? "active" : ""}
          onClick={() => onScopeChange("matched")}
          type="button"
        >
          watched
        </button>
        <button
          className={scope === "all" ? "active" : ""}
          onClick={() => onScopeChange("all")}
          type="button"
        >
          all
        </button>
      </div>
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
