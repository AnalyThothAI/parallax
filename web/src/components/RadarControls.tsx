import { UserRound } from "lucide-react";
import type { ScopeKey, WindowKey } from "../api/types";
import { OBSERVATION_WINDOWS } from "../lib/observationWindows";

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
  onHandlesChange
}: RadarControlsProps) {
  return (
    <>
      <div className="segmented" aria-label="radar window">
        {OBSERVATION_WINDOWS.map((item) => (
          <button key={item} className={item === windowKey ? "active" : ""} onClick={() => onWindowChange(item)} type="button">
            {item}
          </button>
        ))}
      </div>
      <div className="segmented scope-toggle" aria-label="token flow scope">
        <button className={scope === "matched" ? "active" : ""} onClick={() => onScopeChange("matched")} type="button">
          watched
        </button>
        <button className={scope === "all" ? "active" : ""} onClick={() => onScopeChange("all")} type="button">
          all
        </button>
      </div>
      {onHandlesChange ? (
        <label className="handle-filter compact">
          <UserRound aria-hidden />
          <input value={handles ?? ""} onChange={(event) => onHandlesChange(event.target.value)} placeholder={handlePlaceholder} />
        </label>
      ) : null}
    </>
  );
}
