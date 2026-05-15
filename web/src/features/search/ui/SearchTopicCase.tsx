import { compactNumber } from "@lib/format";
import type { SearchInspectData, SearchTopicResult } from "@lib/types";
import { useMemo } from "react";

import { buildSearchCaseView } from "../model/searchCase";

import { SearchAgentBrief } from "./SearchAgentBrief";
import { SearchDossier } from "./SearchDossier";
import { SearchMetricStrip } from "./SearchMetricStrip";
import { SearchTopicTimeline } from "./SearchTopicTimeline";
import { SearchTwitterResults } from "./SearchTwitterResults";

export function SearchTopicCase({
  data,
  result,
}: {
  data: SearchInspectData;
  result: SearchTopicResult;
}) {
  const searchCase = useMemo(() => buildSearchCaseView(data), [data]);

  return (
    <div className="search-content">
      <SearchDossier view={searchCase} />

      <SearchMetricStrip
        metrics={[
          { label: "result", value: "topic", detail: "no unique target" },
          {
            label: `${data.query.window} posts`,
            value: compactNumber(result.summary.posts),
            detail: "search hits",
          },
          {
            label: "authors",
            value: compactNumber(result.summary.authors),
            detail: "unique handles",
          },
          {
            label: "resolver",
            value: `${Math.round(data.resolver.confidence * 100)}%`,
            detail: "topic confidence",
          },
        ]}
      />

      <div className="search-result-grid">
        <div className="search-result-primary">
          <SearchTopicTimeline items={result.items} />
          <SearchTwitterResults title="Topic Evidence" items={result.items} />
        </div>
        <div className="search-result-insights">
          <SearchAgentBrief brief={result.agent_brief} />
        </div>
      </div>
    </div>
  );
}
