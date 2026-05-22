import clsx from "clsx";
import type { ReactNode } from "react";

import "./CompactPanel.css";

type CompactPanelProps = {
  children: ReactNode;
  className?: string;
  mobileTaskPanel?: "tape" | "lab";
};

export function CompactPanel({ children, className, mobileTaskPanel }: CompactPanelProps) {
  return (
    <section className={clsx("compact-panel", className)} data-mobile-task-panel={mobileTaskPanel}>
      {children}
    </section>
  );
}
