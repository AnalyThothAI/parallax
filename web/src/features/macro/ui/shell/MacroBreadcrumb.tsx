import { Link } from "react-router-dom";

import { buildMacroBreadcrumbs, type MacroModuleId } from "../../model/macroRoutes";

export function MacroBreadcrumb({ moduleId }: { moduleId: MacroModuleId }) {
  const breadcrumbs = buildMacroBreadcrumbs(moduleId);
  return (
    <nav aria-label="Macro breadcrumb" className="macro-shell-breadcrumb">
      {breadcrumbs.map((crumb, index) => (
        <span key={crumb.href}>
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
