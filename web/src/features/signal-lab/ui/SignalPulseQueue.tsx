import type { SignalPulseItem } from "@lib/types";
import { signalPulseVenueActions } from "@lib/venue";
import * as PageState from "@shared/ui/PageState";
import { ExternalLink } from "lucide-react";

import { buildSignalPulseQueueItem } from "../model/signalPulseQueue";

import styles from "./SignalPulseQueue.module.css";

type Props = {
  compact?: boolean;
  isLoading?: boolean;
  items: SignalPulseItem[];
  selectedItemId?: string | null;
  onSelect: (item: SignalPulseItem) => void;
};

export function SignalPulseQueue({
  compact = false,
  isLoading,
  items,
  selectedItemId,
  onSelect,
}: Props) {
  if (isLoading) {
    return (
      <PageState.TableSkeleton
        compact={compact}
        rows={compact ? 4 : 5}
        label="loading signal pulse"
      />
    );
  }
  if (!items.length) {
    return <PageState.Empty title="No pulse candidates in this window" />;
  }
  return (
    <div className={styles.queue} data-density={compact ? "compact" : "full"}>
      {items.map((item) => {
        const view = buildSignalPulseQueueItem(item);
        const venueActions = signalPulseVenueActions(item);
        return (
          <article
            className={styles.caseCard}
            data-selected={selectedItemId === item.candidate_id ? "true" : "false"}
            data-tone={view.tone}
            key={view.key}
          >
            <div className={styles.main}>
              <div className={styles.idLine}>
                <strong>{view.symbol}</strong>
                {venueActions.length ? (
                  <nav className={styles.venueLinks} aria-label={`${view.symbol} 外部链接`}>
                    {venueActions.map((action) => (
                      <a
                        className={styles.venueLink}
                        href={action.url}
                        key={`${action.label}:${action.url}`}
                        rel="noreferrer"
                        target="_blank"
                        title={`在 ${action.label} 打开 ${view.symbol}`}
                      >
                        <ExternalLink aria-hidden />
                        <span>{action.label}</span>
                      </a>
                    ))}
                  </nav>
                ) : null}
                <span className={styles.meta}>{view.meta}</span>
              </div>
              <div className={styles.title}>{view.title}</div>
              <p className={styles.summary}>{view.summary}</p>
              <div className={styles.chips}>
                {view.chips.map((chip) => (
                  <span className={styles.chip} data-tone={chip.tone} key={chip.label}>
                    {chip.label}
                  </span>
                ))}
                <span className={styles.chip}>Agent：{view.verdict.label}</span>
              </div>
            </div>
            <div className={styles.side}>
              <div className={styles.score}>
                <b>{view.score.value}</b>
                <span>{view.score.caption}</span>
              </div>
              <time className={styles.time} dateTime={view.timeIso}>
                {view.timeLabel}
              </time>
              <div className={styles.verdict}>
                <span>{view.verdict.confidenceLabel}</span>
              </div>
              <button
                className={styles.openButton}
                type="button"
                aria-label={`查看 ${view.symbol} 详情`}
                onClick={() => onSelect(item)}
              >
                查看详情
              </button>
            </div>
          </article>
        );
      })}
    </div>
  );
}
