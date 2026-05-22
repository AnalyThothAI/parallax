import clsx from "clsx";
import type { ReactNode } from "react";

import { Alert, AlertDescription, AlertTitle } from "./alert";
import { Button } from "./button";
import { Panel } from "./panel";
import { Skeleton } from "./skeleton";
import "./PageState.css";

type PageStateLayout = "route" | "panel" | "inline";

type PageStateLoadingProps = {
  layout: PageStateLayout;
  rows?: number;
  label: string;
};

type PageStateEmptyProps = {
  title: ReactNode;
  hint?: ReactNode;
  action?: ReactNode;
};

type PageStateErrorProps = {
  error: unknown;
  onRetry?: () => void;
};

type PageStateStaleProps = {
  updating: boolean;
  children: ReactNode;
};

type PageStateTableSkeletonProps = {
  rows?: number;
  label?: string;
  compact?: boolean;
  className?: string;
};

export function Loading({ layout, rows = 5, label }: PageStateLoadingProps) {
  return (
    <TableSkeleton
      className={clsx("page-state-loading", `page-state-layout-${layout}`)}
      compact={layout === "inline"}
      label={label}
      rows={rows}
    />
  );
}

export function Empty({ title, hint, action }: PageStateEmptyProps) {
  return (
    <Panel className="page-state-empty">
      <b>{title}</b>
      {hint ? <span>{hint}</span> : null}
      {action ? <div className="page-state-empty-action">{action}</div> : null}
    </Panel>
  );
}

export function Error({ error, onRetry }: PageStateErrorProps) {
  return (
    <Alert className="page-state-error" variant="destructive">
      <AlertTitle>请求失败</AlertTitle>
      <AlertDescription>{errorMessage(error)}</AlertDescription>
      {onRetry ? (
        <Button size="sm" type="button" variant="outline" onClick={onRetry}>
          Retry
        </Button>
      ) : null}
    </Alert>
  );
}

export function Stale({ updating, children }: PageStateStaleProps) {
  return (
    <div
      aria-busy={updating}
      className={clsx("page-state-stale", updating && "page-state-stale-updating")}
    >
      {children}
      {updating ? <span className="sr-only">Updating</span> : null}
    </div>
  );
}

export function TableSkeleton({
  rows = 5,
  label = "loading table",
  compact = false,
  className,
}: PageStateTableSkeletonProps) {
  return (
    <div
      aria-busy="true"
      aria-label={label}
      className={clsx(
        "page-state-table-skeleton",
        compact && "page-state-table-skeleton-compact",
        className,
      )}
      role="status"
    >
      {Array.from({ length: rows }, (_, index) => (
        <div aria-hidden="true" className="page-state-table-row" key={index}>
          <Skeleton className="page-state-table-block page-state-table-block-leading" />
          <Skeleton className="page-state-table-block page-state-table-block-body" />
          <Skeleton className="page-state-table-block page-state-table-block-trailing" />
        </div>
      ))}
    </div>
  );
}

function errorMessage(error: unknown): string {
  if (error instanceof globalThis.Error) {
    return error.message;
  }
  if (typeof error === "string") {
    return error;
  }
  return "unknown error";
}
