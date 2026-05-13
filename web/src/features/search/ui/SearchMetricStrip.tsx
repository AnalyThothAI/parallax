import clsx from "clsx";

export type SearchMetric = {
  detail?: string;
  label: string;
  tone?: "positive" | "warning" | "negative";
  value: string;
};

export function SearchMetricStrip({ metrics }: { metrics: SearchMetric[] }) {
  return (
    <section className="search-metric-strip" aria-label="Search metrics">
      {metrics.map((metric) => (
        <div className={clsx(metric.tone && `tone-${metric.tone}`)} key={metric.label}>
          <span>{metric.label}</span>
          <b>{metric.value}</b>
          {metric.detail ? <em>{metric.detail}</em> : null}
        </div>
      ))}
    </section>
  );
}
