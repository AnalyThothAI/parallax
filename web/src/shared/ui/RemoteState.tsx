import clsx from "clsx";
import type { ReactNode } from "react";

import "./RemoteState.css";

type SkeletonRowsProps = {
  count?: number;
  label: string;
  compact?: boolean;
};

type RemoteStateLoadingProps = {
  layout: "route" | "panel" | "inline";
  rows?: number;
  label: string;
};

type RemoteStateEmptyProps = {
  title: ReactNode;
  hint?: ReactNode;
  action?: ReactNode;
};

type RemoteStateErrorProps = {
  error: unknown;
  onRetry?: () => void;
};

type RemoteStateStaleProps = {
  updating: boolean;
  children: ReactNode;
};

export function SkeletonRows({ count = 5, label, compact = false }: SkeletonRowsProps) {
  return (
    <div aria-label={label} className={clsx("skeleton-rows", compact && "compact")} role="status">
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

function Loading({ layout, rows = 5, label }: RemoteStateLoadingProps) {
  return (
    <div
      aria-label={label}
      className={clsx(
        "remote-state-loading",
        layout,
        "skeleton-rows",
        layout === "inline" && "compact",
      )}
      role="status"
    >
      {Array.from({ length: rows }, (_, index) => (
        <span className="skeleton-row" key={index}>
          <i />
          <b />
          <em />
        </span>
      ))}
    </div>
  );
}

function Empty({ title, hint, action }: RemoteStateEmptyProps) {
  return (
    <div className="remote-state-empty">
      <b>{title}</b>
      {hint ? <span>{hint}</span> : null}
      {action}
    </div>
  );
}

function ErrorState({ error, onRetry }: RemoteStateErrorProps) {
  return (
    <div className="remote-state-error" role="alert">
      <b>请求失败</b>
      <span>{errorMessage(error)}</span>
      {onRetry ? (
        <button type="button" onClick={onRetry}>
          Retry
        </button>
      ) : null}
    </div>
  );
}

function Stale({ updating, children }: RemoteStateStaleProps) {
  return (
    <div className={clsx("remote-state-stale", updating && "updating")} aria-busy={updating}>
      {children}
      {updating ? <span className="sr-only">Updating</span> : null}
    </div>
  );
}

function errorMessage(error: unknown): string {
  if (error instanceof Error) {
    return error.message;
  }
  if (typeof error === "string") {
    return error;
  }
  return "unknown error";
}

export const RemoteState = {
  Loading,
  Empty,
  Error: ErrorState,
  Stale,
};
