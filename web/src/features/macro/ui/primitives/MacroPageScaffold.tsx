import type { ReactNode } from "react";

import type { MacroPageKind } from "../../model/macroPageRegistry";
import "./macroPageScaffold.css";

export function MacroPageScaffold({
  children,
  label,
  pageKind,
}: {
  children: ReactNode;
  label: string;
  pageKind: MacroPageKind;
}) {
  return (
    <section className="macro-page-scaffold" aria-label={label} data-page-kind={pageKind}>
      {children}
    </section>
  );
}
