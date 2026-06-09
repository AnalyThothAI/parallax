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
import { MacroMatrixPage } from "./ui/pages/MacroMatrixPage";
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
      routeKind: "matrix";
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
  if (props.routeKind === "matrix") {
    return <MacroMatrixPage token={props.token} />;
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
      statusItems: [{ label: "截至", value: macroAsOfLabel(module) }],
      title: macroModuleTitle(moduleId, module),
    };
  }

  if (isRatesModuleId(moduleId)) {
    return {
      breadcrumbs: buildMacroBreadcrumbs(moduleId),
      eyebrow: "利率工作台",
      question: module.snapshot.question ?? module.snapshot.subtitle ?? null,
      statusItems: [
        { label: "数据", value: macroStatusLabel(module) },
        { label: "截至", value: macroAsOfLabel(module) },
      ],
      title: macroModuleTitle(moduleId, module),
    };
  }

  return {
    breadcrumbs: buildMacroBreadcrumbs(moduleId),
    eyebrow: module.snapshot.section ?? "宏观工作台",
    question: module.snapshot.question ?? module.snapshot.subtitle ?? null,
    statusItems: [
      { label: "状态", value: macroStatusLabel(module) },
      { label: "截至", value: macroAsOfLabel(module) },
    ],
    title: macroModuleTitle(moduleId, module),
  };
}
