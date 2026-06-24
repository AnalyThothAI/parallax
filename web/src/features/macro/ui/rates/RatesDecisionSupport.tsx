import type { RatesDecisionGroup } from "../../model/macroRatesWorkbenchModel";
import { MacroPanel } from "../primitives/MacroPanel";

export function RatesDecisionSupport({ groups }: { groups: RatesDecisionGroup[] }) {
  const visibleGroups = groups.filter((group) => group.items.length > 0);
  const itemCount = visibleGroups.reduce((count, group) => count + group.items.length, 0);

  if (itemCount === 0) {
    return null;
  }

  return (
    <MacroPanel
      ariaLabel="决策支持"
      className="macro-rates-decision-support macro-rates-decision-panel"
      meta={`${itemCount} 条`}
      span="full"
      title="决策支持"
    >
      <div className="macro-rates-decision-grid">
        {visibleGroups.map((group) => (
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
            <ul className="macro-rates-decision-list">
              {group.items.map((item) => (
                <li key={`${group.key}:${item.label}`}>
                  <b>{item.label}</b>
                  {item.detail ? <span>{item.detail}</span> : null}
                </li>
              ))}
            </ul>
          </section>
        ))}
      </div>
    </MacroPanel>
  );
}
