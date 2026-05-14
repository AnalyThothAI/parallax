import type { DetailDensity, PulseDetailViewModel } from "../../model/pulseDetail";

import styles from "./PulseTimeline.module.css";

type Props = {
  timeline: PulseDetailViewModel["timeline"];
  density: DetailDensity;
};

export function PulseTimeline({ density, timeline }: Props) {
  return (
    <section className={styles.timeline} data-density={density} aria-label="pulse timeline">
      {timeline.nodes.map((node) => (
        <article key={node.kind} data-tone={node.tone}>
          <span aria-hidden />
          <div>
            <h2>{node.title}</h2>
            <time>{node.timestampLabel}</time>
            <p>{node.meta}</p>
            <small>{node.relativeAgeLabel}</small>
          </div>
        </article>
      ))}
    </section>
  );
}
