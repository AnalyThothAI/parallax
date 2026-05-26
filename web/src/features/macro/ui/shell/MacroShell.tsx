import type { ReactNode } from "react";

import type { MacroPageKind, MacroProductTier } from "../../model/macroPageRegistry";
import type { MacroBreadcrumb as MacroBreadcrumbItem } from "../../model/macroRoutes";

import { MacroPageHeader } from "./MacroPageHeader";

import "./macroShell.css";

export type MacroShellStatusItem = {
  label: string;
  value: ReactNode;
};

export type MacroShellHeaderModel = {
  actions?: ReactNode;
  breadcrumbs: MacroBreadcrumbItem[];
  eyebrow: string;
  question?: string | null;
  statusItems: MacroShellStatusItem[];
  title: string;
};

export function MacroShell({
  children,
  header,
  pageKind,
  productTier,
}: {
  children: ReactNode;
  header: MacroShellHeaderModel;
  pageKind: MacroPageKind;
  productTier: MacroProductTier;
}) {
  return (
    <section
      className="macro-shell"
      aria-label="宏观工作台"
      data-page-kind={pageKind}
      data-product-tier={productTier}
    >
      <div className="macro-shell-main">
        <MacroPageHeader header={header} />
        <div className="macro-shell-content">{children}</div>
      </div>
    </section>
  );
}
