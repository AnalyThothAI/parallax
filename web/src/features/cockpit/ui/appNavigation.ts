import { MACRO_NAVIGATION_ITEMS } from "@features/macro/shell";
import {
  BarChart3,
  BriefcaseBusiness,
  Newspaper,
  Radar,
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

const macroNavigationChildren: AppNavigationItem[] = MACRO_NAVIGATION_ITEMS.map((item) => ({
  end: item.href === "/macro",
  label: item.label,
  to: item.href,
}));

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
        children: macroNavigationChildren,
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
    ],
  },
];
