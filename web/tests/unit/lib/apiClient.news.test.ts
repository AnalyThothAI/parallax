import { fetchNewsItem, fetchNewsRows } from "@lib/api/client";
import { HttpResponse, http } from "msw";
import { describe, expect, it } from "vitest";

import { server } from "@tests/msw/server";

describe("news API client normalization", () => {
  it("normalizes flat, nested, and missing news agent briefs", async () => {
    server.use(
      http.get(/.*\/api\/news$/, () =>
        HttpResponse.json({
          ok: true,
          data: {
            items: [
              {
                row_id: "row-flat",
                news_item_id: "news-flat",
                lifecycle_status: "processed",
                headline: "Flat brief",
                agent_brief_json: {
                  status: "ready",
                  direction: "bullish",
                  decision_class: "driver",
                  summary_zh: "后端中文摘要",
                  market_read_zh: "后端市场解读",
                  bull_view: {
                    strength: "moderate",
                    thesis_zh: "多头来自后端",
                    evidence_refs: ["item:title"],
                  },
                  bear_view: {
                    strength: "weak",
                    thesis_zh: "空头来自后端",
                    evidence_refs: [{ ref: "fact:1", label: "Fact 1" }],
                  },
                  data_gaps: [
                    "缺少价格反应",
                    { description_zh: "缺少身份映射", severity: "high" },
                  ],
                  evidence_refs: ["item:title", { ref: "fact:1", label: "Fact 1" }],
                },
                agent_brief_computed_at_ms: "1765000000000",
              },
              {
                row_id: "row-nested",
                news_item_id: "news-nested",
                lifecycle_status: "processed",
                headline: "Nested brief",
                agent_brief: {
                  status: "ready",
                  brief_json: {
                    direction: "bearish",
                    decision_class: "watch",
                    summary_zh: "嵌套摘要",
                    market_read_zh: "嵌套解读",
                    bull_view: { strength: "absent", thesis_zh: "", evidence_refs: [] },
                    bear_view: {
                      strength: "strong",
                      thesis_zh: "嵌套空头",
                      evidence_refs: ["item:summary"],
                    },
                    data_gaps: [{ kind: "identity", severity: "medium" }],
                    evidence_refs: ["item:summary"],
                  },
                },
              },
              {
                row_id: "row-missing",
                news_item_id: "news-missing",
                lifecycle_status: "processed",
                headline: "Missing brief",
              },
            ],
            next_cursor: null,
          },
        }),
      ),
    );

    const rows = await fetchNewsRows({ limit: 3, token: "test-token" });

    expect(rows.items[0].agent_brief?.summary_zh).toBe("后端中文摘要");
    expect(rows.items[0].agent_brief?.bull_strength).toBe("moderate");
    expect(rows.items[0].agent_brief?.data_gaps).toEqual([
      "缺少价格反应",
      { description_zh: "缺少身份映射", severity: "high" },
    ]);
    expect(rows.items[0].agent_brief?.evidence_refs).toEqual([
      "item:title",
      { ref: "fact:1", label: "Fact 1" },
    ]);
    expect(rows.items[0].agent_brief?.computed_at_ms).toBe(1_765_000_000_000);
    expect(rows.items[1].agent_brief?.summary_zh).toBe("嵌套摘要");
    expect(rows.items[1].agent_brief?.bear_strength).toBe("strong");
    expect(rows.items[1].agent_brief?.data_gaps).toEqual([
      { description_zh: "identity", severity: "medium" },
    ]);
    expect(rows.items[2].agent_brief).toEqual({
      status: "pending",
      direction: null,
      decision_class: null,
      summary_zh: null,
      market_read_zh: null,
      bull_strength: null,
      bear_strength: null,
      data_gap_count: 0,
      computed_at_ms: null,
      agent_run_id: null,
      schema_version: null,
      prompt_version: null,
      artifact_version_hash: null,
      input_hash: null,
      output_hash: null,
      model: null,
      brief_json: null,
      bull_view: null,
      bear_view: null,
      data_gaps: [],
      watch_triggers: [],
      invalidation_conditions: [],
      evidence_refs: [],
    });
  });

  it("normalizes item detail agent run error aliases", async () => {
    server.use(
      http.get(/.*\/api\/news\/items\/news-failed$/, () =>
        HttpResponse.json({
          ok: true,
          data: {
            row_id: "row-failed",
            news_item_id: "news-failed",
            lifecycle_status: "processed",
            headline: "Failed brief",
            agent_brief: {
              status: "failed",
              data_gaps: [{ description_zh: "provider failed", severity: "high" }],
            },
            agent_run: {
              run_id: "run-failed",
              status: "failed",
              outcome: "provider_error",
              execution_started: true,
              error_class: "ProviderError",
              error: "provider timeout",
            },
          },
        }),
      ),
    );

    const item = await fetchNewsItem({ newsItemId: "news-failed" });

    expect(item.agent_brief?.status).toBe("failed");
    expect(item.agent_brief?.data_gaps).toEqual([
      { description_zh: "provider failed", severity: "high" },
    ]);
    expect(item.agent_run?.error_class).toBe("ProviderError");
    expect(item.agent_run?.error).toBe("provider timeout");
    expect(item.agent_run?.error_message).toBe("provider timeout");
  });
});
