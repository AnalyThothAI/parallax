import { Link } from "react-router-dom";

import type { MacroBreadcrumb as MacroBreadcrumbItem } from "../../model/macroRoutes";

export function MacroBreadcrumb({ breadcrumbs }: { breadcrumbs: MacroBreadcrumbItem[] }) {
  return (
    <nav aria-label="宏观面包屑" className="macro-shell-breadcrumb">
      {breadcrumbs.map((crumb, index) => (
        <span key={`${crumb.href}:${index}`}>
          {index > 0 ? <span aria-hidden="true">/</span> : null}
          {index === breadcrumbs.length - 1 ? (
            <span aria-current="page">{crumb.label}</span>
          ) : (
            <Link to={crumb.href}>{crumb.label}</Link>
          )}
        </span>
      ))}
    </nav>
  );
}
