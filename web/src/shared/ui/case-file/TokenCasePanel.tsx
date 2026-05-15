import type {
  TokenCaseScope,
  TokenCaseSort,
  TokenCaseViewModel,
  TokenCaseWindow,
} from "@shared/model/tokenCaseViewModel";

import { TokenCaseAmplifiersRail } from "./TokenCaseAmplifiersRail";
import { TokenCaseBullBearRail } from "./TokenCaseBullBearRail";
import { TokenCaseDataGapsRail } from "./TokenCaseDataGapsRail";
import { TokenCaseHero } from "./TokenCaseHero";
import { TokenCaseMarketRail } from "./TokenCaseMarketRail";
import { TokenCaseMetricStrip } from "./TokenCaseMetricStrip";
import styles from "./TokenCasePanel.module.css";
import { TokenCasePropagationSummary } from "./TokenCasePropagationSummary";
import { TokenCaseTimeline } from "./TokenCaseTimeline";

export type TokenCasePanelProps = {
  vm: TokenCaseViewModel;
  onWindowChange: (window: TokenCaseWindow) => void;
  onScopeChange: (scope: TokenCaseScope) => void;
  onTimelineSortChange: (sort: TokenCaseSort) => void;
  onLoadMorePosts: () => void;
};

export function TokenCasePanel({
  vm,
  onWindowChange,
  onScopeChange,
  onTimelineSortChange,
  onLoadMorePosts,
}: TokenCasePanelProps) {
  return (
    <section className={styles.panel} aria-label="Token case">
      <TokenCaseHero
        hero={vm.hero}
        route={vm.route}
        target={vm.target}
        onScopeChange={onScopeChange}
        onWindowChange={onWindowChange}
      />
      <TokenCaseMetricStrip metrics={vm.metrics} />
      <TokenCasePropagationSummary propagation={vm.propagation} />
      <div className={styles.workspace}>
        <div className={styles.mainColumn}>
          <TokenCaseTimeline
            timeline={vm.timeline}
            onLoadMorePosts={onLoadMorePosts}
            onTimelineSortChange={onTimelineSortChange}
          />
        </div>
        <div className={styles.sideRail} aria-label="Token case side rail">
          <TokenCaseMarketRail market={vm.market} />
          <TokenCaseBullBearRail bullBear={vm.bullBear} />
          <TokenCaseAmplifiersRail amplifiers={vm.amplifiers} />
          <TokenCaseDataGapsRail dataGaps={vm.dataGaps} />
        </div>
      </div>
    </section>
  );
}
