import type { ReactNode } from "react";
import { Link, useLocation } from "react-router-dom";

import { MACRO_NAVIGATION_TREE, type MacroNavigationNode } from "../../model/macroNavigationTree";
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
  const location = useLocation();
  const moduleNavItems = macroShellModuleNavItems();

  return (
    <section
      className="macro-shell"
      aria-label="宏观工作台"
      data-page-kind={pageKind}
      data-product-tier={productTier}
    >
      <div className="macro-shell-main">
        <MacroPageHeader header={header} />
        {moduleNavItems.length ? (
          <nav aria-label="宏观模块" className="macro-shell-module-nav">
            {moduleNavItems.map((item) => {
              const isActive = isActiveMacroModule(item, location.pathname);
              return (
                <Link
                  aria-current={isActive ? "page" : undefined}
                  data-state={isActive ? "active" : undefined}
                  key={item.label}
                  to={item.href}
                >
                  {item.label}
                </Link>
              );
            })}
          </nav>
        ) : null}
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

type MacroShellModuleNavItem = {
  href: string;
  label: string;
  matchPath?: string;
};

function macroShellModuleNavItems(): MacroShellModuleNavItem[] {
  const root = MACRO_NAVIGATION_TREE[0];
  return (root.children ?? []).flatMap((node) => {
    const href = visibleHref(node);
    if (!href) return [];
    return [{ href, label: node.label, matchPath: node.matchPath }];
  });
}

function visibleHref(node: MacroNavigationNode): string | null {
  if (node.pageKind) {
    return node.href;
  }
  const visibleChild = node.children?.find((child) => visibleHref(child));
  return visibleChild ? visibleHref(visibleChild) : null;
}

function isActiveMacroModule(item: MacroShellModuleNavItem, pathname: string): boolean {
  if (item.href === "/macro") {
    return pathname === "/macro";
  }
  const prefix = item.matchPath?.replace(/\/\*$/, "") ?? item.href;
  return pathname === item.href || pathname.startsWith(`${prefix}/`) || pathname === prefix;
}
