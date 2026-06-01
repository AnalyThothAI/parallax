import type { RatesDecisionGroup } from "../../model/macroRatesWorkbenchModel";
import { MacroPanel } from "../primitives/MacroPanel";

export function RatesDecisionSupport({ groups }: { groups: RatesDecisionGroup[] }) {
  const itemCount = groups.reduce((count, group) => count + group.items.length, 0);

  return (
    <MacroPanel
      ariaLabel="决策支持"
      className="macro-rates-decision-panel"
      meta={`${itemCount} 条`}
      span="full"
      title="决策支持"
    >
      <div className="macro-rates-decision-grid">
        {groups.map((group) => (
          <section
            aria-label={group.label}
            className="macro-rates-decision-group"
            key={group.key}
            role="group"
          >
            <div className="macro-rates-decision-group-head">
              <h4>{group.label}</h4>
              <span>{group.items.length}</span>
            </div>
            {group.items.length > 0 ? (
              <ul className="macro-rates-decision-list">
                {group.items.map((item) => (
                  <li key={`${group.key}:${item.label}`}>
                    <b>{item.label}</b>
                    <span>{item.detail}</span>
                  </li>
                ))}
              </ul>
            ) : (
              <div className="macro-rates-empty">暂无</div>
            )}
          </section>
        ))}
      </div>
    </MacroPanel>
  );
}
