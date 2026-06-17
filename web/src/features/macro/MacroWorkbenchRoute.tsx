import type { MacroModuleView } from "@lib/types";
import * as PageState from "@shared/ui/PageState";

import { useMacroModuleQuery } from "./api/useMacroModuleQuery";
import type { MacroPageKind, MacroProductTier } from "./model/macroPageRegistry";
import {
  macroAsOfLabel,
  macroFreshnessAlert,
  macroModuleTitle,
  macroStatusLabel,
} from "./model/macroPageViewModel";
import { isRatesModuleId } from "./model/macroRatesWorkbenchModel";
import { buildMacroBreadcrumbs, type MacroModuleId } from "./model/macroRoutes";
import { MacroModulePageRenderer } from "./ui/pages/MacroModulePageRenderer";
import {
  MacroShell,
  type MacroShellHeaderModel,
  type MacroShellStatusItem,
} from "./ui/shell/MacroShell";

type MacroWorkbenchRouteProps = {
  moduleId: MacroModuleId;
  pageKind: MacroPageKind;
  productTier: MacroProductTier;
  token: string;
};

export function MacroWorkbenchRoute(props: MacroWorkbenchRouteProps) {
  return (
    <MacroModuleWorkbenchRoute
      moduleId={props.moduleId}
      pageKind={props.pageKind}
      productTier={props.productTier}
      token={props.token}
    />
  );
}

function MacroModuleWorkbenchRoute({
  moduleId,
  pageKind,
  productTier,
  token,
}: {
  moduleId: MacroModuleId;
  pageKind: MacroPageKind;
  productTier: MacroProductTier;
  token: string;
}) {
  const query = useMacroModuleQuery({ moduleId, token });
  const module = query.data ?? null;

  return (
    <section className="macro-module-route" aria-label="宏观">
      {query.isLoading ? <PageState.Loading layout="route" label="加载宏观模块" /> : null}
      {query.isError ? <PageState.Error error={query.error} /> : null}
      {module ? (
        <PageState.Stale updating={query.isFetching && !query.isLoading}>
          <MacroShell
            freshnessAlert={macroFreshnessAlert(module)}
            header={macroModuleHeader({ module, moduleId })}
            pageKind={pageKind}
            productTier={productTier}
          >
            <MacroModulePageRenderer
              module={module}
              moduleId={moduleId}
              pageKind={pageKind}
              token={token}
            />
          </MacroShell>
        </PageState.Stale>
      ) : null}
    </section>
  );
}

function macroModuleHeader({
  module,
  moduleId,
}: {
  module: MacroModuleView;
  moduleId: MacroModuleId;
}): MacroShellHeaderModel {
  if (moduleId === "assets") {
    return {
      breadcrumbs: buildMacroBreadcrumbs(moduleId),
      eyebrow: "Assets",
      question: null,
      statusItems: compactStatusItems([statusItem("截至", macroAsOfLabel(module))]),
      title: macroModuleTitle(moduleId, module),
    };
  }

  if (isRatesModuleId(moduleId)) {
    return {
      breadcrumbs: buildMacroBreadcrumbs(moduleId),
      eyebrow: "利率工作台",
      question: module.snapshot.question ?? module.snapshot.subtitle ?? null,
      statusItems: compactStatusItems([
        statusItem("数据", macroStatusLabel(module)),
        statusItem("截至", macroAsOfLabel(module)),
      ]),
      title: macroModuleTitle(moduleId, module),
    };
  }

  return {
    breadcrumbs: buildMacroBreadcrumbs(moduleId),
    eyebrow: module.snapshot.section ?? "宏观工作台",
    question: module.snapshot.question ?? module.snapshot.subtitle ?? null,
    statusItems: compactStatusItems([
      statusItem("状态", macroStatusLabel(module)),
      statusItem("截至", macroAsOfLabel(module)),
    ]),
    title: macroModuleTitle(moduleId, module),
  };
}

function statusItem(label: string, value: string | null): MacroShellStatusItem | null {
  return value ? { label, value } : null;
}

function compactStatusItems(items: Array<MacroShellStatusItem | null>): MacroShellStatusItem[] {
  return items.filter((item): item is MacroShellStatusItem => item !== null);
}
