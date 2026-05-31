import type { SignalPulseItem, SourceEventDetail } from "@lib/types";
import { useMemo, type ReactNode } from "react";

import {
  buildPulseDetailView,
  type DetailDensity,
  type PulseDetailViewModel,
} from "../../model/pulseDetail";

import { PulseAgentRail } from "./PulseAgentRail";
import styles from "./PulseDetailView.module.css";
import { PulseEvidenceList } from "./PulseEvidenceList";
import { PulseFactorFamilies } from "./PulseFactorFamilies";
import { PulseHero } from "./PulseHero";
import { PulseMarketContext } from "./PulseMarketContext";
import { PulseTimeline } from "./PulseTimeline";

type Props = {
  item: SignalPulseItem;
  sourceEvents: SourceEventDetail[];
  density?: DetailDensity;
  actions?: ReactNode;
  now?: number;
};

export function PulseDetailView({
  actions,
  density = "full",
  item,
  now = Date.now(),
  sourceEvents,
}: Props) {
  const view = useMemo(
    () => buildPulseDetailView({ item, sourceEvents, now }),
    [item, now, sourceEvents],
  );
  return <PulseDetailFrame actions={actions} density={density} view={view} />;
}

function PulseDetailFrame({
  actions,
  density,
  view,
}: {
  actions?: ReactNode;
  density: DetailDensity;
  view: PulseDetailViewModel;
}) {
  return (
    <article className={styles.detail} data-density={density}>
      <PulseHero actions={actions} density={density} hero={view.hero} />
      <main className={styles.body}>
        <div className={styles.main}>
          <PulseTimeline density={density} timeline={view.timeline} />
          <PulseFactorFamilies families={view.families} />
          <PulseMarketContext market={view.market} />
          <PulseEvidenceList evidence={view.evidence} />
        </div>
        <PulseAgentRail agent={view.agent} />
      </main>
    </article>
  );
}
