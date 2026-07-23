import clsx from "clsx";
import type { HTMLAttributes, ReactNode } from "react";
import { useId } from "react";

import type { ResearchSource, ResearchTone } from "./researchLanguage";
import "./ResearchPrimitives.css";

export type ResearchFieldItem = {
  detail?: ReactNode;
  label: ReactNode;
  source?: ResearchSource;
  tone?: ResearchTone;
  value: ReactNode;
};

const SOURCE_LABELS: Record<ResearchSource, string> = {
  deterministic: "deterministic",
  market: "market",
  official: "official",
  social: "social",
};

export function ResearchTag({
  children,
  tone = "neutral",
}: {
  children: ReactNode;
  tone?: ResearchTone;
}) {
  return (
    <span className="research-tag" data-tone={tone}>
      {children}
    </span>
  );
}

export function ResearchMark({
  className,
  label,
  tone = "opportunity",
}: {
  className?: string;
  label: string;
  tone?: ResearchTone;
}) {
  return (
    <span className={clsx("research-mark", className)} data-tone={tone}>
      {label.slice(0, 1).toUpperCase()}
    </span>
  );
}

export function ResearchPanel({
  children,
  className,
  "aria-label": ariaLabel = "research panel",
  ...props
}: HTMLAttributes<HTMLElement>) {
  return (
    <section aria-label={ariaLabel} className={clsx("research-panel", className)} {...props}>
      {children}
    </section>
  );
}

export function ResearchHeader({
  badge,
  eyebrow,
  subtitle,
  title,
}: {
  badge?: ReactNode;
  eyebrow?: ReactNode;
  subtitle?: ReactNode;
  title: ReactNode;
}) {
  return (
    <header className="research-header">
      <div className="research-header-meta">
        {eyebrow ? <span>{eyebrow}</span> : null}
        {badge}
      </div>
      <h2>{title}</h2>
      {subtitle ? <p>{subtitle}</p> : null}
    </header>
  );
}

export function ResearchSection({
  children,
  subtitle,
  title,
}: {
  children: ReactNode;
  subtitle?: ReactNode;
  title: ReactNode;
}) {
  const titleId = useId();
  return (
    <section aria-labelledby={titleId} className="research-section">
      <header>
        <h3 id={titleId}>{title}</h3>
        {subtitle ? <p>{subtitle}</p> : null}
      </header>
      {children}
    </section>
  );
}

export function ResearchFieldGrid({ fields }: { fields: ResearchFieldItem[] }) {
  return (
    <dl className="research-field-grid">
      {fields.map((field, index) => (
        <div data-tone={field.tone ?? "neutral"} key={`${String(field.label)}:${index}`}>
          <dt>
            <span>{field.label}</span>
            {field.source ? <small>{SOURCE_LABELS[field.source]}</small> : null}
          </dt>
          <dd>{field.value}</dd>
          {field.detail ? <dd>{field.detail}</dd> : null}
        </div>
      ))}
    </dl>
  );
}
