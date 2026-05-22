import clsx from "clsx";
import { Link } from "react-router-dom";

import {
  MACRO_MODULE_ROUTES,
  MACRO_ROUTE_GROUPS,
  type MacroModuleId,
} from "../../model/macroRoutes";

export function MacroLocalNav({ moduleId }: { moduleId: MacroModuleId }) {
  return (
    <nav aria-label="Macro modules" className="macro-shell-nav">
      {MACRO_ROUTE_GROUPS.map((group) => {
        const routes = MACRO_MODULE_ROUTES.filter((route) => route.section === group.section);
        return (
          <section className="macro-shell-nav-group" key={group.section}>
            <span className="macro-shell-nav-group-label">{group.label}</span>
            <div className="macro-shell-nav-links">
              {routes.map((route) => {
                const active = route.moduleId === moduleId;
                return (
                  <Link
                    aria-current={active ? "page" : undefined}
                    className={clsx("macro-shell-nav-link", active && "active")}
                    key={route.moduleId}
                    to={route.href}
                  >
                    {navLabel(route)}
                  </Link>
                );
              })}
            </div>
          </section>
        );
      })}
    </nav>
  );
}

function navLabel(route: (typeof MACRO_MODULE_ROUTES)[number]): string {
  return route.moduleId === route.section && route.section !== "overview"
    ? `${route.label} Overview`
    : route.label;
}
