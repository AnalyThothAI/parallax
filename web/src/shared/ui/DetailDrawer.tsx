import clsx from "clsx";
import type { ReactNode } from "react";

type DetailDrawerShellProps = {
  children: ReactNode;
  className?: string;
};

type DetailDrawerHeaderProps = {
  eyebrow: string;
  title: ReactNode;
  subtitle?: ReactNode;
  badge?: ReactNode;
  metrics?: ReactNode;
  actions?: ReactNode;
  children?: ReactNode;
  className?: string;
};

type DetailDrawerMetricGridProps = {
  children: ReactNode;
  className?: string;
};

type DetailDrawerMetricProps = {
  label: string;
  value: ReactNode;
};

type DetailDrawerSectionProps = {
  children: ReactNode;
  title?: ReactNode;
  className?: string;
};

type DetailDrawerCardProps = {
  children: ReactNode;
  title?: ReactNode;
  tone?: "default" | "accent";
  className?: string;
};

type DetailDrawerFieldGridProps = {
  children: ReactNode;
  className?: string;
};

type DetailDrawerFieldProps = {
  label: string;
  value?: ReactNode;
};

type DetailDrawerTagStripProps = {
  items: ReactNode[];
  emptyLabel: ReactNode;
  featuredItem?: ReactNode;
  className?: string;
};

export function DetailDrawerShell({ children, className }: DetailDrawerShellProps) {
  return <aside className={clsx("detail-drawer", "drawer", className)}>{children}</aside>;
}

export function DetailDrawerHeader({
  eyebrow,
  title,
  subtitle,
  badge,
  metrics,
  actions,
  children,
  className,
}: DetailDrawerHeaderProps) {
  return (
    <header className={clsx("drawer-head", className)}>
      <div className="drawer-title">
        <div>
          <div className="eyebrow">{eyebrow}</div>
          <h2>{title}</h2>
          {subtitle ? <p>{subtitle}</p> : null}
          {actions}
        </div>
        {badge !== undefined && badge !== null ? (
          <div className="opportunity-score">{badge}</div>
        ) : null}
      </div>
      {metrics}
      {children}
    </header>
  );
}

export function DetailDrawerMetricGrid({ children, className }: DetailDrawerMetricGridProps) {
  return <div className={clsx("drawer-kv", className)}>{children}</div>;
}

export function DetailDrawerMetric({ label, value }: DetailDrawerMetricProps) {
  return (
    <div>
      <span>{label}</span>
      <b>{value}</b>
    </div>
  );
}

export function DetailDrawerSection({ children, title, className }: DetailDrawerSectionProps) {
  return (
    <section className={clsx("drawer-section", className)}>
      {title ? <div className="section-title">{title}</div> : null}
      {children}
    </section>
  );
}

export function DetailDrawerCard({
  children,
  title,
  tone = "default",
  className,
}: DetailDrawerCardProps) {
  return (
    <article className={clsx("detail-drawer-card", tone === "accent" && "is-accent", className)}>
      {title ? <h3>{title}</h3> : null}
      {children}
    </article>
  );
}

export function DetailDrawerFieldGrid({ children, className }: DetailDrawerFieldGridProps) {
  return <div className={clsx("detail-drawer-fields", className)}>{children}</div>;
}

export function DetailDrawerField({ label, value }: DetailDrawerFieldProps) {
  return (
    <div className="detail-drawer-field">
      <span>{label}</span>
      <b>{value === null || value === undefined || value === "" ? "-" : value}</b>
    </div>
  );
}

export function DetailDrawerTagStrip({
  items,
  emptyLabel,
  featuredItem,
  className,
}: DetailDrawerTagStripProps) {
  const renderedItems = items.length ? items : [emptyLabel];
  return (
    <div className={clsx("risk-strip", "detail-drawer-tag-strip", className)}>
      {featuredItem ? <span className="hot">{featuredItem}</span> : null}
      {renderedItems.map((item, index) => (
        <span key={typeof item === "string" ? `${index}:${item}` : index}>{item}</span>
      ))}
    </div>
  );
}
