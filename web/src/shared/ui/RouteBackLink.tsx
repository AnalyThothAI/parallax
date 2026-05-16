import { ArrowLeft } from "lucide-react";

import styles from "./RouteBackLink.module.css";

export function RouteBackLink({
  ariaLabel,
  label,
  to,
}: {
  ariaLabel: string;
  label: string;
  to: string;
}) {
  return (
    <a aria-label={ariaLabel} className={styles.link} href={to}>
      <ArrowLeft aria-hidden />
      <span>{label}</span>
    </a>
  );
}
