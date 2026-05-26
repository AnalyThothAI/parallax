import type { ReactNode } from "react";

import "./macroPanel.css";

export function MacroPanel({
  ariaLabel,
  children,
  className,
  meta,
  span = "half",
  title,
}: {
  ariaLabel: string;
  children: ReactNode;
  className?: string;
  meta?: ReactNode;
  span?: "full" | "half" | "major" | "minor";
  title?: ReactNode;
}) {
  const panelClassName = ["macro-panel", className].filter(Boolean).join(" ");
  return (
    <section className={panelClassName} aria-label={ariaLabel} data-span={span}>
      {title || meta ? (
        <div className="macro-panel-head">
          {title ? <h3>{title}</h3> : null}
          {meta ? <span>{meta}</span> : null}
        </div>
      ) : null}
      {children}
    </section>
  );
}
