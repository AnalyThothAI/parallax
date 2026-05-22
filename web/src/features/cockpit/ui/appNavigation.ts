import {
  BarChart3,
  BriefcaseBusiness,
  FlaskConical,
  Newspaper,
  Radar,
  ServerCog,
  Star,
  type LucideIcon,
} from "lucide-react";

export type AppNavigationBadgeKey = "news" | "stocks" | "token";

export type AppNavigationItem = {
  badgeKey?: AppNavigationBadgeKey;
  children?: AppNavigationItem[];
  end?: boolean;
  icon?: LucideIcon;
  label: string;
  matchPath?: string;
  to: string;
};

export type AppNavigationGroup = {
  items: AppNavigationItem[];
  label: string;
};

export const APP_NAVIGATION_GROUPS: AppNavigationGroup[] = [
  {
    label: "Radar",
    items: [
      {
        badgeKey: "token",
        end: true,
        icon: Radar,
        label: "Token Radar",
        to: "/",
      },
      {
        badgeKey: "stocks",
        icon: BarChart3,
        label: "Stocks",
        matchPath: "/stocks/*",
        to: "/stocks",
      },
    ],
  },
  {
    label: "Intel",
    items: [
      {
        badgeKey: "news",
        icon: Newspaper,
        label: "News",
        matchPath: "/news/*",
        to: "/news",
      },
      {
        children: [
          { end: true, label: "Overview", to: "/macro" },
          { end: true, label: "Assets", to: "/macro/assets" },
          { end: true, label: "Correlation", to: "/macro/assets/correlation" },
        ],
        icon: BriefcaseBusiness,
        label: "Macro",
        matchPath: "/macro/*",
        to: "/macro",
      },
      {
        icon: Star,
        label: "Watchlist",
        matchPath: "/watchlist/*",
        to: "/watchlist",
      },
      {
        icon: FlaskConical,
        label: "Signal Lab",
        matchPath: "/signal-lab/*",
        to: "/signal-lab",
      },
    ],
  },
  {
    label: "System",
    items: [
      {
        icon: ServerCog,
        label: "Ops",
        matchPath: "/ops/*",
        to: "/ops",
      },
    ],
  },
];
