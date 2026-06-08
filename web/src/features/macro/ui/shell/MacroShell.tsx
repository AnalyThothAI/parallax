import type { ReactNode } from "react";

import type { MacroPageKind, MacroProductTier } from "../../model/macroPageRegistry";
import type { MacroFreshnessAlertModel } from "../../model/macroPageViewModel";
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
  freshnessAlert,
  header,
  pageKind,
  productTier,
}: {
  children: ReactNode;
  freshnessAlert?: MacroFreshnessAlertModel | null;
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
        {freshnessAlert ? (
          <section
            aria-label={freshnessAlert.title}
            className="macro-shell-freshness-alert"
            role="status"
          >
            <div className="macro-shell-freshness-copy">
              <strong>{freshnessAlert.title}</strong>
              <span>{freshnessAlert.detail}</span>
            </div>
            {freshnessAlert.items.length > 0 ? (
              <ul>
                {freshnessAlert.items.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            ) : null}
          </section>
        ) : null}
        <div className="macro-shell-content">{children}</div>
      </div>
    </section>
  );
}
