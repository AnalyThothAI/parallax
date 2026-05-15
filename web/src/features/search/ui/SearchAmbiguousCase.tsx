import { shortAddress } from "@lib/format";
import type { SearchAmbiguousResult, SearchInspectData, SearchTargetCandidate } from "@lib/types";
import { useMemo } from "react";

import { buildSearchCaseView } from "../model/searchCase";

import { SearchAgentBrief } from "./SearchAgentBrief";
import { SearchDossier } from "./SearchDossier";
import { SearchTopicTimeline } from "./SearchTopicTimeline";
import { SearchTwitterResults } from "./SearchTwitterResults";

export function SearchAmbiguousCase({
  data,
  result,
}: {
  data: SearchInspectData;
  result: SearchAmbiguousResult;
}) {
  const searchCase = useMemo(() => buildSearchCaseView(data), [data]);

  return (
    <div className="search-content">
      <SearchDossier view={searchCase} />

      <section className="search-panel search-candidate-compare">
        <header>
          <h3>Candidate Compare</h3>
          <span>Ambiguous query</span>
        </header>
        <div className="search-candidate-grid">
          {result.candidates.map((candidate) => (
            <article key={candidateKey(candidate)}>
              <b>{candidate.symbol ? `$${candidate.symbol}` : shortTarget(candidate.target_id)}</b>
              <span>{candidate.target_type}</span>
              <code>{candidate.status}</code>
              <small>{candidate.reason}</small>
              <p>{identityLine(candidate, {})}</p>
            </article>
          ))}
        </div>
      </section>

      <div className="search-result-grid">
        <div className="search-result-primary">
          <SearchTopicTimeline items={result.items} />
          <SearchTwitterResults title="Ambiguous Evidence" items={result.items} />
        </div>
        <div className="search-result-insights">
          <SearchAgentBrief brief={result.agent_brief} />
        </div>
      </div>
    </div>
  );
}

function identityLine(candidate: SearchTargetCandidate, marketOverlay: Record<string, unknown>) {
  const chain = candidate.chain_id ?? stringValue(marketOverlay.chain_id);
  const address = candidate.address ?? stringValue(marketOverlay.address);
  const nativeMarket = stringValue(marketOverlay.native_market_id);
  if (candidate.target_type === "CexToken" && nativeMarket !== "-") {
    return `${nativeMarket} · ${candidate.target_id}`;
  }
  if (address && address !== "-") {
    return `${chain || "chain"} · ${shortAddress(address)}`;
  }
  return candidate.target_id;
}

function shortTarget(value: string) {
  return value.length > 28 ? `${value.slice(0, 14)}...${value.slice(-8)}` : value;
}

function candidateKey(candidate: SearchTargetCandidate | null) {
  if (!candidate) return "";
  return `${candidate.target_type}:${candidate.target_id}`;
}

function stringValue(value: unknown): string {
  if (typeof value === "string" && value.trim()) return value;
  if (typeof value === "number" && Number.isFinite(value)) return String(value);
  return "-";
}
