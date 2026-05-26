import type { MacroModuleView } from "@lib/types";
import * as PageState from "@shared/ui/PageState";

import { useMacroModuleQuery } from "./api/useMacroModuleQuery";
import type { MacroPageKind, MacroProductTier } from "./model/macroPageRegistry";
import {
  buildMacroBreadcrumbs,
  type MacroModuleId,
} from "./model/macroRoutes";
import {
  macroAsOfLabel,
  macroModuleTitle,
  macroStatusLabel,
} from "./model/macroPageViewModel";
import { MacroModulePageRenderer } from "./ui/pages/MacroModulePageRenderer";
import { MacroShell, type MacroShellHeaderModel } from "./ui/shell/MacroShell";

type MacroWorkbenchRouteProps =
  | {
      moduleId: MacroModuleId;
      pageKind: Exclude<MacroPageKind, "matrix" | "unsupported">;
      productTier: Exclude<MacroProductTier, "unsupported">;
      routeKind?: "module";
      token: string;
    }
  | {
      routeKind: "unsupported";
      routeTail: string;
      token: string;
    };

export function MacroWorkbenchRoute(props: MacroWorkbenchRouteProps) {
  if (props.routeKind === "unsupported") {
    return (
      <section className="macro-module-route" aria-label="宏观">
        <div aria-label="不支持的宏观页面" className="macro-route-unsupported" role="status">
          <strong>不支持的宏观页面</strong>
          <span>/macro/{props.routeTail}</span>
        </div>
      </section>
    );
  }

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
  pageKind: Exclude<MacroPageKind, "matrix" | "unsupported">;
  productTier: Exclude<MacroProductTier, "unsupported">;
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
  return {
    breadcrumbs: buildMacroBreadcrumbs(moduleId),
    eyebrow: module.snapshot.section ?? "宏观工作台",
    question: module.snapshot.question ?? module.snapshot.subtitle ?? null,
    statusItems: [
      { label: "状态", value: macroStatusLabel(module) },
      { label: "截至", value: macroAsOfLabel(module) },
      { label: "版本", value: module.snapshot.projection_version ?? "暂无版本" },
    ],
    title: macroModuleTitle(moduleId, module),
  };
}
