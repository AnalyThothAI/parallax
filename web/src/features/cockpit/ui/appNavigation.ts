import {
  BarChart3,
  BriefcaseBusiness,
  CalendarDays,
  FlaskConical,
  Newspaper,
  Radar,
  ServerCog,
  Star,
  type LucideIcon,
} from "lucide-react";

export type AppNavigationItem = {
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
        end: true,
        icon: Radar,
        label: "Token Radar",
        to: "/",
      },
      {
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
        icon: Newspaper,
        label: "News",
        matchPath: "/news/*",
        to: "/news",
      },
      {
        icon: CalendarDays,
        label: "Earnings",
        matchPath: "/earnings/*",
        to: "/earnings",
      },
      {
        children: [
          { end: true, label: "总览", to: "/macro" },
          { end: true, label: "资产", to: "/macro/assets" },
          { end: true, label: "相关性", to: "/macro/assets/correlation" },
        ],
        icon: BriefcaseBusiness,
        label: "宏观",
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
