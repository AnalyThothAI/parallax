import { macroPath, newsPath, opsPath, stocksPath, watchlistPath } from "@shared/routing/paths";
import {
  BarChart3,
  BriefcaseBusiness,
  Newspaper,
  Radar,
  Search,
  ServerCog,
  Star,
} from "lucide-react";
import { NavLink } from "react-router-dom";

const ROUTES = [
  { label: "Radar", to: "/", icon: Radar, end: true },
  { label: "Stocks", to: stocksPath(), icon: BarChart3 },
  { label: "News", to: newsPath(), icon: Newspaper },
  { label: "Macro", to: macroPath(), icon: BriefcaseBusiness },
  { label: "Watchlist", to: watchlistPath(), icon: Star },
  { label: "Ops", to: opsPath(), icon: ServerCog },
  { label: "Search", to: "/search", icon: Search },
];

export function MobileRouteNav() {
  return (
    <nav aria-label="mobile route navigation" className="mobile-route-nav">
      {ROUTES.map(({ end, icon: Icon, label, to }) => (
        <NavLink
          aria-label={label}
          className={({ isActive }) => (isActive ? "active" : undefined)}
          end={end}
          key={label}
          to={to}
        >
          <Icon aria-hidden />
          <span>{label}</span>
        </NavLink>
      ))}
    </nav>
  );
}
