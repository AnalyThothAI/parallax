import clsx from "clsx";
import type { ReactNode } from "react";

import "./CompactPanel.css";

type CompactPanelProps = {
  children: ReactNode;
  className?: string;
};

export function CompactPanel({ children, className }: CompactPanelProps) {
  return <section className={clsx("compact-panel", className)}>{children}</section>;
}
