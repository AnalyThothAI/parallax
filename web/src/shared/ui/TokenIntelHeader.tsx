import type { TokenProfileBlock } from "@lib/types";
import clsx from "clsx";
import type { ReactNode } from "react";

import { TokenProfileCard } from "./TokenProfileCard";
import {
  ObsidianCase,
  ObsidianCaseHeader,
  ObsidianFieldGrid,
  type ObsidianTone,
} from "./case-file";
import type { ObsidianSource } from "./obsidianLanguage";

export type TokenIntelField = {
  detail?: ReactNode;
  label: ReactNode;
  source?: ObsidianSource;
  tone?: ObsidianTone;
  value: ReactNode;
};

type TokenIntelHeaderProps = {
  actions?: ReactNode;
  ariaLabel: string;
  badge?: ReactNode;
  className?: string;
  eyebrow?: ReactNode;
  fields: TokenIntelField[];
  mark?: ReactNode;
  meta?: ReactNode;
  profile?: TokenProfileBlock | null;
  profileLabel: string;
  subtitle?: ReactNode;
  title: ReactNode;
};

export function TokenIntelHeader({
  actions,
  ariaLabel,
  badge,
  className,
  eyebrow,
  fields,
  mark,
  meta,
  profile,
  profileLabel,
  subtitle,
  title,
}: TokenIntelHeaderProps) {
  return (
    <ObsidianCase aria-label={ariaLabel} className={clsx("token-intel-case", className)}>
      <ObsidianCaseHeader
        actions={actions}
        badge={badge}
        eyebrow={eyebrow}
        lead={
          <div role="region" aria-label={profileLabel}>
            <TokenProfileCard profile={profile} />
          </div>
        }
        mark={mark}
        meta={meta}
        subtitle={subtitle}
        title={title}
      />
      <ObsidianFieldGrid fields={fields} />
    </ObsidianCase>
  );
}
