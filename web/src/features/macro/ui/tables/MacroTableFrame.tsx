import type { CSSProperties, ReactNode } from "react";
import { useId } from "react";

import "./macroTableFrame.css";

export function MacroTableFrame({
  caption,
  children,
  minWidth = 420,
  stickyFirstColumn = false,
}: {
  caption: string;
  children: ReactNode;
  minWidth?: number;
  stickyFirstColumn?: boolean;
}) {
  const hintId = useId();

  return (
    <div
      className="macro-table-frame"
      data-sticky-first-column={stickyFirstColumn ? "true" : "false"}
    >
      <div className="macro-table-frame-hint" id={hintId}>
        横向滚动查看完整列
      </div>
      <div
        aria-describedby={hintId}
        aria-label={`${caption}，可横向滚动`}
        className="macro-table-frame-scroller"
        role="region"
        style={{ "--macro-table-min-width": `${minWidth}px` } as CSSProperties}
        tabIndex={0}
      >
        {children}
      </div>
    </div>
  );
}
