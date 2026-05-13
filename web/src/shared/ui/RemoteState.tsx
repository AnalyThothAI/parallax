import type { ReactNode } from "react";

type SkeletonRowsProps = {
  count?: number;
  label: string;
  compact?: boolean;
};

export function SkeletonRows({ count = 5, label, compact = false }: SkeletonRowsProps) {
  return (
    <div
      aria-label={label}
      className={`skeleton-rows ${compact ? "compact" : ""}`.trim()}
      role="status"
    >
      {Array.from({ length: count }, (_, index) => (
        <span className="skeleton-row" key={index}>
          <i />
          <b />
          <em />
        </span>
      ))}
    </div>
  );
}

export function PanelSkeleton({ label }: { label: string }) {
  return (
    <div className="route-state-panel">
      <SkeletonRows count={4} label={label} />
    </div>
  );
}

export function RouteStatePanel({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="route-state-panel">
      <b>{title}</b>
      {children ? <p>{children}</p> : null}
    </div>
  );
}
