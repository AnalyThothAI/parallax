import clsx from "clsx";
import type { HTMLAttributes, ReactNode } from "react";
import { useId } from "react";

import type { ObsidianSource, ObsidianTone } from "./obsidianLanguage";
import "./obsidian.css";

export type {
  ObsidianSource,
  ObsidianStringEvidence,
  ObsidianStringField,
  ObsidianTone,
} from "./obsidianLanguage";

export type ObsidianFieldItem = {
  detail?: ReactNode;
  label: ReactNode;
  source?: ObsidianSource;
  tone?: ObsidianTone;
  value: ReactNode;
};

export type ObsidianEvidenceItem = {
  body: ReactNode;
  href?: string;
  id: string;
  meta?: ReactNode;
  title?: ReactNode;
  tone?: ObsidianTone;
};

type BaseProps = {
  children: ReactNode;
  className?: string;
};

const SOURCE_LABELS: Record<ObsidianSource, string> = {
  agent: "agent",
  deterministic: "deterministic",
  market: "market",
  official: "official",
  social: "social",
};

type ObsidianCaseProps = HTMLAttributes<HTMLElement> & {
  children: ReactNode;
};

type ObsidianCaseHeaderProps = {
  actions?: ReactNode;
  badge?: ReactNode;
  children?: ReactNode;
  eyebrow?: ReactNode;
  lead?: ReactNode;
  mark?: ReactNode;
  meta?: ReactNode;
  subtitle?: ReactNode;
  title: ReactNode;
};

type ObsidianSectionProps = {
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
  subtitle?: ReactNode;
  title: ReactNode;
};

type ObsidianFieldGridProps = {
  children?: ReactNode;
  fields?: ObsidianFieldItem[];
};

type ObsidianActionBarProps = {
  children: ReactNode;
  className?: string;
};

type ObsidianEvidenceListProps = {
  emptyLabel?: ReactNode;
  items: ObsidianEvidenceItem[];
};

export function ObsidianPill({
  children,
  className,
  tone = "neutral",
}: BaseProps & { tone?: ObsidianTone }) {
  return (
    <span className={clsx("ods-pill", tone !== "neutral" && tone, className)}>{children}</span>
  );
}

export function ObsidianTokenMark({
  label,
  tone = "opportunity",
}: {
  label: string;
  tone?: ObsidianTone;
}) {
  return <span className={clsx("ods-token-mark", tone)}>{label.slice(0, 1).toUpperCase()}</span>;
}

export function ObsidianMetric({
  label,
  value,
  tone = "neutral",
}: {
  label: string;
  value: ReactNode;
  tone?: ObsidianTone;
}) {
  return (
    <div className={clsx("ods-metric", tone !== "neutral" && tone)}>
      <b>{value}</b>
      <span>{label}</span>
    </div>
  );
}

export function ObsidianCase({
  children,
  className,
  "aria-label": ariaLabel = "obsidian case",
  ...props
}: ObsidianCaseProps) {
  return (
    <section aria-label={ariaLabel} className={clsx("ods-case", className)} {...props}>
      {children}
    </section>
  );
}

export function ObsidianCaseHeader({
  actions,
  badge,
  children,
  eyebrow,
  lead,
  mark,
  meta,
  subtitle,
  title,
}: ObsidianCaseHeaderProps) {
  return (
    <header className={clsx("ods-case-head", mark && "has-mark")}>
      {mark ? <div className="ods-case-mark">{mark}</div> : null}
      <div className="ods-case-copy">
        <div className="ods-case-meta">
          {eyebrow ? <span className="ods-kicker">{eyebrow}</span> : null}
          {badge}
          {meta}
        </div>
        <h2>{title}</h2>
        {subtitle ? <p>{subtitle}</p> : null}
        {lead ? <div className="ods-case-lead">{lead}</div> : null}
        {children}
      </div>
      {actions ? <div className="ods-case-actions-slot">{actions}</div> : null}
    </header>
  );
}

export function ObsidianSection({
  actions,
  children,
  className,
  subtitle,
  title,
}: ObsidianSectionProps) {
  const titleId = useId();

  return (
    <section aria-labelledby={titleId} className={clsx("ods-section", className)}>
      <div className="ods-section-head">
        <div>
          <h3 id={titleId}>{title}</h3>
          {subtitle ? <p>{subtitle}</p> : null}
        </div>
        {actions ? <div className="ods-section-actions">{actions}</div> : null}
      </div>
      {children}
    </section>
  );
}

export function ObsidianFieldGrid({ children, fields }: ObsidianFieldGridProps) {
  return (
    <div className="ods-field-grid">
      {fields?.map((field, index) => (
        <ObsidianField
          detail={field.detail}
          key={`${String(field.label)}-${index}`}
          label={field.label}
          source={field.source}
          tone={field.tone}
          value={field.value}
        />
      ))}
      {children}
    </div>
  );
}

export function ObsidianField({
  detail,
  label,
  source,
  tone = "neutral",
  value,
}: ObsidianFieldItem) {
  return (
    <div className={clsx("ods-field", tone !== "neutral" && tone)}>
      <div className="ods-field-label">
        <span>{label}</span>
        {source ? <span className="ods-source">{SOURCE_LABELS[source]}</span> : null}
      </div>
      <div className="ods-field-value">{value}</div>
      {detail ? <div className="ods-field-detail">{detail}</div> : null}
    </div>
  );
}

export function ObsidianActionBar({ children, className }: ObsidianActionBarProps) {
  return <div className={clsx("ods-action-bar", className)}>{children}</div>;
}

export function ObsidianEvidenceList({
  emptyLabel = "No evidence yet.",
  items,
}: ObsidianEvidenceListProps) {
  if (items.length === 0) {
    return <div className="ods-empty-evidence">{emptyLabel}</div>;
  }

  return (
    <ul className="ods-evidence-list">
      {items.map((item) => (
        <li className={clsx("ods-evidence", item.tone ?? "neutral")} key={item.id}>
          <div className="ods-evidence-line">
            {item.href ? <a href={item.href}>{item.title ?? item.href}</a> : <b>{item.title}</b>}
            {item.meta ? <span>{item.meta}</span> : null}
          </div>
          <p>{item.body}</p>
        </li>
      ))}
    </ul>
  );
}

export function ObsidianMetricGrid({ children, className }: BaseProps) {
  return <div className={clsx("ods-metric-grid", className)}>{children}</div>;
}

export function ObsidianDetailCard({ children, className, title }: BaseProps & { title: string }) {
  return (
    <section className={clsx("ods-detail-card", className)}>
      <h4>{title}</h4>
      {children}
    </section>
  );
}

export function ObsidianRecord({
  action,
  avatar,
  meta,
  title,
}: {
  action?: ReactNode;
  avatar: string;
  meta: ReactNode;
  title: ReactNode;
}) {
  return (
    <article className="ods-record">
      <span className="ods-avatar">{avatar.slice(0, 1).toUpperCase()}</span>
      <span className="ods-record-main">
        <b>{title}</b>
        <span>{meta}</span>
      </span>
      {action}
    </article>
  );
}

export function ObsidianMiniPage({
  aside,
  children,
  eyebrow,
  meta,
  subtitle,
  title,
}: BaseProps & {
  aside?: ReactNode;
  eyebrow?: string;
  meta?: ReactNode;
  subtitle?: ReactNode;
  title: ReactNode;
}) {
  return (
    <section className="ods-mini-page">
      <header className="ods-mini-page-head">
        <div>
          {eyebrow ? <span className="ods-kicker">{eyebrow}</span> : null}
          <h3>{title}</h3>
          {subtitle ? <p>{subtitle}</p> : null}
        </div>
        {meta}
      </header>
      <div className={clsx("ods-mini-page-body", aside && "with-aside")}>
        <div>{children}</div>
        {aside ? <aside>{aside}</aside> : null}
      </div>
    </section>
  );
}
