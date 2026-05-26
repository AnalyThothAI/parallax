import type { MacroMetricDisplay } from "../../model/macroModulePresentation";
import "./macroMetricStrip.css";

export function MacroMetricStrip({
  ariaLabel,
  density = "auto",
  metrics,
}: {
  ariaLabel: string;
  density?: "auto" | "card" | "compact" | "list";
  metrics: MacroMetricDisplay[];
}) {
  if (metrics.length === 0) {
    return (
      <section className="macro-metric-strip" aria-label={ariaLabel} data-density={density}>
        <div className="macro-metric-empty" role="status">
          暂无关键指标
        </div>
      </section>
    );
  }

  return (
    <section
      className="macro-metric-strip"
      aria-label={ariaLabel}
      data-count={metrics.length}
      data-density={density}
    >
      {metrics.map((metric) => {
        const displayLabel = metric.shortLabel ?? metric.label;
        const showFullLabel = metric.label !== displayLabel;
        return (
          <article
            className="macro-metric"
            data-quality={metric.quality ?? undefined}
            key={metric.key}
          >
            <div className="macro-metric-label-zone">
              <span className="macro-metric-short-label" data-macro-metric-label="true">
                {displayLabel}
              </span>
              {showFullLabel ? <b>{metric.label}</b> : null}
            </div>
            <div className="macro-metric-value-zone">
              <strong>{metric.value}</strong>
              {metric.unitLabel ? <em>{metric.unitLabel}</em> : null}
            </div>
            {metric.observedAtLabel ? <small>{metric.observedAtLabel}</small> : null}
          </article>
        );
      })}
    </section>
  );
}
