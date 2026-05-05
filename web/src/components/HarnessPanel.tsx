import type { AttentionSeedItem, HarnessHealth, HarnessSnapshotItem, SocialEventItem } from "../api/types";
import { formatRelativeTime } from "../lib/format";
import { AttentionSeedList } from "./AttentionSeedList";
import { HarnessHealthStrip } from "./HarnessHealthStrip";
import { SocialEventFeed } from "./SocialEventFeed";

export type HarnessPanelMode = "events" | "seeds" | "snapshots" | "outcomes" | "evaluation";
type HarnessHorizon = "6h" | "24h";

type HarnessPanelProps = {
  health: HarnessHealth;
  horizon: HarnessHorizon;
  socialEvents: SocialEventItem[];
  seeds: AttentionSeedItem[];
  snapshots: HarnessSnapshotItem[];
  view: HarnessPanelMode;
  selectedId?: string | null;
  isLoading?: boolean;
  onHorizonChange: (horizon: HarnessHorizon) => void;
  onViewChange: (view: HarnessPanelMode) => void;
  onSelectEvent: (item: SocialEventItem) => void;
  onSelectSeed: (item: AttentionSeedItem) => void;
  onSelectSnapshot: (item: HarnessSnapshotItem) => void;
};

export function HarnessPanel({
  health,
  horizon,
  socialEvents,
  seeds,
  snapshots,
  view,
  selectedId,
  isLoading,
  onHorizonChange,
  onViewChange,
  onSelectEvent,
  onSelectSeed,
  onSelectSnapshot
}: HarnessPanelProps) {
  return (
    <div className="harness-panel">
      <HarnessHealthStrip health={health} />
      <div className="harness-toolbar">
        <div className="harness-tabs" aria-label="harness panel tabs">
          <button className={view === "events" ? "active" : ""} type="button" onClick={() => onViewChange("events")}>
            Events
          </button>
          <button className={view === "seeds" ? "active" : ""} type="button" onClick={() => onViewChange("seeds")}>
            Seeds
          </button>
          <button className={view === "snapshots" ? "active" : ""} type="button" onClick={() => onViewChange("snapshots")}>
            Snapshots
          </button>
        </div>
        <div className="harness-horizon-control" aria-label="settlement horizon">
          <span>settle</span>
          {(["6h", "24h"] as const).map((item) => (
            <button className={horizon === item ? "active" : ""} key={item} type="button" onClick={() => onHorizonChange(item)}>
              {item}
            </button>
          ))}
        </div>
      </div>
      {isLoading ? <div className="empty-state">loading harness state</div> : null}
      {!isLoading && view === "events" ? <SocialEventFeed items={socialEvents} selectedId={selectedId} onSelect={onSelectEvent} /> : null}
      {!isLoading && view === "seeds" ? <AttentionSeedList items={seeds} selectedSeedId={selectedId} onSelect={onSelectSeed} /> : null}
      {!isLoading && view === "snapshots" ? (
        <div className="harness-feed">
          {snapshots.length === 0 ? <div className="empty-state">当前窗口暂无 harness snapshot</div> : null}
          {snapshots.map((snapshot) => (
            <button
              className={`harness-row ${selectedId === snapshot.snapshot_id ? "selected" : ""}`}
              key={snapshot.snapshot_id}
              type="button"
              onClick={() => onSelectSnapshot(snapshot)}
            >
              <span className="harness-kind">SNAP</span>
              <span className="harness-row-main">
                <strong>
                  {snapshot.asset} · {snapshot.horizon} · score {snapshot.combined_score.toFixed(2)}
                </strong>
                <p>
                  shadow {snapshot.shadow_signal} · policy {snapshot.policy_signal}
                </p>
                <span className="harness-chip-line">
                  <span className="harness-anchor-chip">{snapshot.outcome_status}</span>
                  <span className="harness-anchor-chip">{snapshot.credit_status}</span>
                </span>
              </span>
              <span className="harness-row-meta">
                <b>{snapshot.shadow_signal.replaceAll("_", " ")}</b>
                <span>{formatRelativeTime(snapshot.decision_time_ms)}</span>
              </span>
            </button>
          ))}
        </div>
      ) : null}
    </div>
  );
}
