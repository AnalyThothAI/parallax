import { RemoteState } from "@shared/ui/RemoteState";

import type { SearchRadarSummary } from "../model/searchRadar";

export function SearchRadarPanel({ summary }: { summary: SearchRadarSummary }) {
  return (
    <section className="search-panel search-radar-panel" id="score">
      <header>
        <h3>Score / Data Health</h3>
        <span>{summary.radarStatusLabel}</span>
      </header>
      {summary.radarStatusLabel === "radar row" ? (
        <>
          <div className="search-score-summary">
            {summary.scoreSummary.map((item) => (
              <div key={item.label}>
                <span>{item.label}</span>
                <b>{item.value}</b>
              </div>
            ))}
          </div>
          {summary.familyScores.length ? (
            <div className="search-score-families">
              {summary.familyScores.map((item) => (
                <div key={item.label}>
                  <span>{item.label}</span>
                  <b>{item.value}</b>
                </div>
              ))}
            </div>
          ) : null}
          <div className="search-data-health">
            {summary.dataHealthEntries.map((item) => (
              <code key={item.label}>
                {item.label}: {item.value}
              </code>
            ))}
          </div>
        </>
      ) : (
        <RemoteState.Empty
          title="当前 window/scope 下没有匹配 radar row。"
          hint="证据和 agent brief 仍然可读。"
        />
      )}
    </section>
  );
}
