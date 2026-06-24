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
  const header = module ? macroModuleHeader({ module, moduleId }) : null;

  return (
    <section className="macro-module-route" aria-label="宏观">
      {query.isLoading ? <PageState.Loading layout="route" label="加载宏观模块" /> : null}
      {query.isError ? <PageState.Error error={query.error} /> : null}
      {module && !header ? (
        <PageState.Error error={new Error("macro_module_title_missing")} />
      ) : null}
      {module && header ? (
        <PageState.Stale updating={query.isFetching && !query.isLoading}>
          <MacroShell
            freshnessAlert={macroFreshnessAlert(module)}
            header={header}
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
}): MacroShellHeaderModel | null {
  const title = macroModuleTitle(module);
  if (!title) {
    return null;
  }

  if (moduleId === "assets") {
    return {
      breadcrumbs: buildMacroBreadcrumbs(moduleId),
      eyebrow: macroModuleSection(module),
      statusItems: compactStatusItems([statusItem("截至", macroAsOfLabel(module))]),
      title,
    };
  }

  if (isRatesModuleId(moduleId)) {
    return {
      breadcrumbs: buildMacroBreadcrumbs(moduleId),
      eyebrow: macroModuleSection(module),
      statusItems: compactStatusItems([
        statusItem("数据", macroStatusLabel(module)),
        statusItem("截至", macroAsOfLabel(module)),
      ]),
      title,
    };
  }

  return {
    breadcrumbs: buildMacroBreadcrumbs(moduleId),
    eyebrow: macroModuleSection(module),
    statusItems: compactStatusItems([
      statusItem("状态", macroStatusLabel(module)),
      statusItem("截至", macroAsOfLabel(module)),
    ]),
    title,
  };
}

function macroModuleSection(module: MacroModuleView): string | null {
  const section = module.snapshot.section;
  return typeof section === "string" && section.trim() ? section.trim() : null;
}

function statusItem(label: string, value: string | null): MacroShellStatusItem | null {
  return value ? { label, value } : null;
}

function compactStatusItems(items: Array<MacroShellStatusItem | null>): MacroShellStatusItem[] {
  return items.filter((item): item is MacroShellStatusItem => item !== null);
}
