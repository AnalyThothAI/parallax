/* eslint-disable jsx-a11y/no-noninteractive-tabindex -- Table scrollers need keyboard focus for horizontal overflow. */
import type { CSSProperties, ReactNode } from "react";
import { useId } from "react";

import "./macroTableFrame.css";

export function MacroTableFrame({
  caption,
  children,
  hint = "横向滚动查看完整列",
  minWidth = 420,
  stickyFirstColumn = false,
}: {
  caption: string;
  children: ReactNode;
  hint?: string | null;
  minWidth?: number;
  stickyFirstColumn?: boolean;
}) {
  const hintId = useId();

  return (
    <div
      className="macro-table-frame"
      data-sticky-first-column={stickyFirstColumn ? "true" : "false"}
    >
      {hint ? (
        <div className="macro-table-frame-hint" id={hintId}>
          {hint}
        </div>
      ) : null}
      <div
        aria-describedby={hint ? hintId : undefined}
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
