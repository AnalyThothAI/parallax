import { MACRO_NAVIGATION_TREE, type MacroNavigationNode } from "@features/macro";
import {
  BarChart3,
  BriefcaseBusiness,
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
  const visibleChildren = node.children?.map(adaptMacroNavigationNode);
  const children = visibleChildren?.length ? visibleChildren : undefined;
  const matchPath = node.matchPath ?? (children?.length ? `${node.href}/*` : undefined);

  return {
    children,
    end: !matchPath,
    label: node.label,
    matchPath,
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
