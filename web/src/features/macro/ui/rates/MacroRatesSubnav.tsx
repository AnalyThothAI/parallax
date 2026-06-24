import { Link } from "react-router-dom";

import type { RatesModuleId } from "../../model/macroRatesWorkbenchModel";

const RATES_NAV_ITEMS: Array<{ href: string; label: string; moduleId: RatesModuleId }> = [
  { href: "/macro/rates/fed-funds", label: "联邦基金", moduleId: "rates/fed-funds" },
  { href: "/macro/rates/yield-curve", label: "收益率曲线", moduleId: "rates/yield-curve" },
  { href: "/macro/rates/real-rates", label: "实际利率", moduleId: "rates/real-rates" },
];

export function MacroRatesSubnav({ activeModuleId }: { activeModuleId: RatesModuleId }) {
  return (
    <section aria-label="利率页导航" className="macro-rates-subnav-region">
      <nav aria-label="利率模块" className="macro-rates-subnav">
        {RATES_NAV_ITEMS.map((item) => {
          const isActive = item.moduleId === activeModuleId;
          return (
            <Link
              aria-current={isActive ? "page" : undefined}
              className="macro-rates-subnav-link"
              data-active={isActive ? "true" : "false"}
              key={item.moduleId}
              to={item.href}
            >
              {item.label}
            </Link>
          );
        })}
      </nav>
    </section>
  );
}
