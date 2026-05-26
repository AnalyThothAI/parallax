import { MACRO_NAVIGATION_TREE, type MacroNavigationNode } from "@features/macro";
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

const macroNavigationRoot = MACRO_NAVIGATION_TREE[0];

function adaptMacroNavigationNode(node: MacroNavigationNode): AppNavigationItem {
  const children = node.children?.map(adaptMacroNavigationNode);

  return {
    children,
    end: !children?.length,
    label: node.label,
    matchPath: children?.length ? `${node.href}/*` : undefined,
    to: node.href,
  };
}

const macroNavigationChildren = macroNavigationRoot.children?.map(adaptMacroNavigationNode) ?? [];

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
        children: macroNavigationChildren,
        icon: BriefcaseBusiness,
        label: macroNavigationRoot.label,
        matchPath: "/macro/*",
        to: macroNavigationRoot.href,
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
