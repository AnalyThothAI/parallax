import { SearchAgentBrief } from "@features/search/ui/SearchAgentBrief";
import type { SearchAgentBrief as SearchAgentBriefData } from "@lib/types";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

describe("SearchAgentBrief", () => {
  it("renders project summary, propagation, bull view, bear view, and evidence ids", () => {
    render(<SearchAgentBrief brief={brief} />);

    expect(screen.getByText("项目总结")).toBeInTheDocument();
    expect(screen.getByText("传播")).toBeInTheDocument();
    expect(screen.getByText("多头观点")).toBeInTheDocument();
    expect(screen.getByText("空头观点")).toBeInTheDocument();
    expect(screen.getAllByText(/ev_482/).length).toBeGreaterThan(0);
  });
});

const brief: SearchAgentBriefData = {
  schema_version: "search_agent_brief_v1",
  generated_by: "deterministic",
  project_summary: {
    one_liner: "$RKC 24h social propagation brief",
    summary_zh: "过去 24 小时，RKC 从 seed 进入 expansion。",
    current_state: "active_propagation",
    data_gaps: ["缺真实 OHLC/K 线"],
    evidence_event_ids: ["ev_401", "ev_482"],
  },
  propagation: {
    summary_zh: "seed -> ignition -> expansion",
    phases: [
      {
        phase: "expansion",
        window_label: "11:00-16:00",
        tweets: 31,
        authors: 14,
        lead_accounts: ["toly", "0xfoobar"],
        read_zh: "作者宽度变大。",
        evidence_event_ids: ["ev_482"],
      },
    ],
    key_accounts: [{ handle: "toly", role: "watched", posts: 2, first_seen_ms: 1_700_000_000_000 }],
  },
  bull_bear: {
    stance: "watch",
    bull: {
      thesis_zh: "作者扩散不是单点 pump。",
      evidence_event_ids: ["ev_482"],
      triggers_zh: ["2 个新的 watched authors"],
    },
    bear: {
      thesis_zh: "17:00 后内容开始 price-only。",
      evidence_event_ids: ["ev_556"],
      invalidations_zh: ["连续 2 个桶没有新作者"],
    },
  },
};
