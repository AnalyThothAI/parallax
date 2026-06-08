import { fetchNewsItem, fetchNewsRows } from "@lib/api/client";
import { server } from "@tests/msw/server";
import { HttpResponse, http } from "msw";
import { describe, expect, it } from "vitest";

describe("news API client normalization", () => {
  it("sends hard-cut news filters without retired token presence filtering", async () => {
    const observedParams: Record<string, string | null> = {};
    let observedKeys: string[] = [];
    server.use(
      http.get(/.*\/api\/news$/, ({ request }) => {
        const searchParams = new URL(request.url).searchParams;
        observedKeys = [...searchParams.keys()].sort();
        ["cursor", "limit", "min_score", "q", "signal"].forEach((key) => {
          observedParams[key] = searchParams.get(key);
        });
        return HttpResponse.json({
          ok: true,
          data: {
            items: [
              {
                row_id: "row-classified",
                news_item_id: "news-classified",
                lifecycle_status: "attention",
                headline: "SEC reviews tokenized stocks",
                source_domain: "sec.gov",
                signal: newsSignalEnvelope({
                  source: "provider",
                  provider: "opennews",
                  status: "ready",
                  direction: "bullish",
                  label_zh: "利好",
                  score: 82,
                  grade: "A",
                }),
                token_lanes: {
                  bad: "shape",
                },
                token_impacts: [
                  {
                    symbol: "BTC",
                    provider_signal: "long",
                    provider_score: 82,
                    provider_grade: "A",
                    market_type: "cex",
                  },
                ],
                fact_lanes: [
                  {
                    event_type: "regulation",
                    status: "accepted",
                  },
                ],
                market_scope: {
                  scope: ["us_equity", "crypto"],
                  primary: "us_equity",
                  status: "classified",
                  reason: "market_scope_classified",
                  basis: { subject: "tokenized_stocks" },
                  version: "news_market_scope_v1",
                },
                agent_admission_status: "eligible",
                agent_admission_reason: "provider_score_high",
                agent_admission: {
                  eligible: true,
                  status: "eligible",
                  reason: "provider_score_high",
                  representative_news_item_id: "news-classified",
                  basis: { provider_score: 82 },
                  version: "news_item_agent_admission_market_v1",
                },
                agent_representative_news_item_id: "news-classified",
                source: {
                  provider_type: "opennews",
                  source_role: "aggregator",
                  trust_tier: "standard",
                  coverage_tags: ["opennews", "6551news"],
                  source_quality_status: "healthy",
                },
              },
            ],
            next_cursor: null,
          },
        });
      }),
    );

    const rows = await fetchNewsRows({
      cursor: "cursor-1",
      has_token: true,
      limit: 25,
      min_score: 70,
      q: "tokenized",
      signal: "bullish",
      token: "test-token",
    } as Parameters<typeof fetchNewsRows>[0] & { has_token: boolean });

    expect(observedParams.cursor).toBe("cursor-1");
    expect(observedParams.limit).toBe("25");
    expect(observedParams.min_score).toBe("70");
    expect(observedParams.q).toBe("tokenized");
    expect(observedParams.signal).toBe("bullish");
    expect(observedKeys).toEqual(["cursor", "limit", "min_score", "q", "signal"].sort());
    expect(rows.items[0].signal.display_signal.label_zh).toBe("利好");
    expect(rows.items[0].signal.display_signal.score).toBe(82);
    expect(rows.items[0].token_lanes).toEqual([]);
    expect(rows.items[0].token_impacts).toEqual([]);
    expect(rows.items[0].signal).not.toHaveProperty("provider_signal");
    expect(rows.items[0].signal.alert_eligibility).not.toHaveProperty("provider_score");
    expect(rows.items[0].source?.provider_type).toBe("opennews");
    expect(rows.items[0].provider_type).toBe("opennews");
    expect(rows.items[0].market_scope?.primary).toBe("us_equity");
    expect(rows.items[0].agent_admission?.status).toBe("eligible");
    expect(rows.items[0].agent_representative_news_item_id).toBe("news-classified");
    expect(rows.items[0].signal.alert_eligibility.market_scope?.primary).toBe("us_equity");
    expect(rows.items[0].signal.alert_eligibility.agent_admission_status).toBe("eligible");
    expect(rows.items[0].signal.alert_eligibility.agent_admission_reason).toBe(
      "provider_score_high",
    );
  });

  it("keeps agent brief optional when the hard-cut row omits it", async () => {
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
                signal: newsSignalEnvelope({
                  source: "agent",
                  status: "ready",
                  direction: "bearish",
                  label_zh: "利空",
                  method: "news_item_brief",
                }),
                agent_brief: {
                  status: "ready",
                  direction: "bearish",
                  decision_class: "watch",
                  summary_zh: "后端摘要",
                  market_read_zh: "后端解读",
                  agent_run_id: "run-retired",
                  artifact_version_hash: "artifact-hash",
                  input_hash: "input-hash",
                  output_hash: "output-hash",
                  prompt_version: "prompt-retired",
                  schema_version: "schema-retired",
                  confirmation_state: "single_source",
                  novelty_status: "new",
                  source_consensus_zh: "retired consensus",
                  retrieval_notes_zh: "retired notes",
                  used_tool_call_ids: ["retired-call"],
                  impact_zh: "retired impact",
                  watch_items_zh: "retired watch",
                  confidence: 0.91,
                  brief_json: {
                    summary_zh: "兼容摘要不应被读取",
                    market_read_zh: "兼容解读不应被读取",
                    confirmation_state: "single_source",
                    novelty_status: "new",
                  },
                  bull_view: { strength: "absent", thesis_zh: "", evidence_refs: [] },
                  bear_view: {
                    strength: "strong",
                    thesis_zh: "空头",
                    evidence_refs: ["item:summary"],
                  },
                  data_gaps: [{ kind: "identity", severity: "medium" }],
                  evidence_refs: ["item:summary"],
                },
              },
              {
                row_id: "row-missing",
                news_item_id: "news-missing",
                lifecycle_status: "processed",
                headline: "Missing brief",
                signal: newsSignalEnvelope({
                  source: "partial",
                  status: "partial",
                  direction: "neutral",
                  label_zh: "中性",
                }),
              },
            ],
            next_cursor: null,
          },
        }),
      ),
    );

    const rows = await fetchNewsRows({ limit: 3, token: "test-token" });

    expect(rows.items[0].agent_brief?.summary_zh).toBe("后端摘要");
    expect(rows.items[0].agent_brief?.bear_strength).toBe("strong");
    expect(rows.items[0].agent_brief?.data_gaps).toEqual([
      { description_zh: "identity", severity: "medium" },
    ]);
    const brief = rows.items[0].agent_brief as Record<string, unknown>;
    expect(brief).not.toHaveProperty("confirmation_state");
    expect(brief).not.toHaveProperty("novelty_status");
    expect(brief).not.toHaveProperty("source_consensus_zh");
    expect(brief).not.toHaveProperty("retrieval_notes_zh");
    expect(brief).not.toHaveProperty("used_tool_call_ids");
    expect(brief).not.toHaveProperty("impact_zh");
    expect(brief).not.toHaveProperty("watch_items_zh");
    expect(brief).not.toHaveProperty("confidence");
    expect(brief).not.toHaveProperty("agent_run_id");
    expect(brief).not.toHaveProperty("artifact_version_hash");
    expect(brief).not.toHaveProperty("input_hash");
    expect(brief).not.toHaveProperty("output_hash");
    expect(brief).not.toHaveProperty("prompt_version");
    expect(brief).not.toHaveProperty("schema_version");
    expect(brief).not.toHaveProperty("brief_json");
    expect(rows.items[1].agent_brief).toBeUndefined();
  });

  it("does not normalize retired news row aliases after the hard cut", async () => {
    server.use(
      http.get(/.*\/api\/news$/, () =>
        HttpResponse.json({
          ok: true,
          data: {
            items: [
              {
                row_id: "row-legacy",
                news_item_id: "news-legacy",
                lifecycle_status: "processed",
                title: "Legacy title",
                url: "https://legacy.example/news",
                published_at_ms: 1_700_000_000_000,
                source_json: {
                  provider_type: "opennews",
                  coverage_tags_json: ["legacy"],
                },
                content_tags_json: ["legacy_tag"],
                token_mentions: [{ display_symbol: "OLD", resolution_status: "resolved" }],
                fact_candidates: [{ event_type: "legacy", validation_status: "accepted" }],
              },
            ],
            next_cursor: null,
          },
        }),
      ),
    );

    const rows = await fetchNewsRows({ limit: 1, token: "test-token" });

    expect(rows.items[0].headline).toBe("Untitled news item");
    expect(rows.items[0].canonical_url).toBeNull();
    expect(rows.items[0].latest_at_ms).toBeNull();
    expect(rows.items[0].source).toBeNull();
    expect(rows.items[0].content_tags).toEqual([]);
    expect(rows.items[0].token_lanes).toEqual([]);
    expect(rows.items[0].fact_lanes).toEqual([]);
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
              usage_json: { input_tokens: 12, output_tokens: 3 },
              request_json: { packet: { news_item_id: "news-failed" } },
              response_json: { summary_zh: "失败前输出" },
              validation_errors_json: [{ path: "summary_zh" }],
              trace_metadata_json: { sdk_trace_id: "trace-1" },
              research_plan: { legacy: true },
              tool_results: [{ tool_name: "legacy" }],
              research_execution: { legacy: true },
              research_hashes: { legacy: true },
              base_packet: { legacy: true },
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
    const run = item.agent_run as Record<string, unknown>;
    expect(run).not.toHaveProperty("run_id");
    expect(run).not.toHaveProperty("usage_json");
    expect(run).not.toHaveProperty("request_json");
    expect(run).not.toHaveProperty("response_json");
    expect(run).not.toHaveProperty("validation_errors_json");
    expect(run).not.toHaveProperty("trace_metadata_json");
    expect(run).not.toHaveProperty("research_plan");
    expect(run).not.toHaveProperty("tool_results");
    expect(run).not.toHaveProperty("research_execution");
    expect(run).not.toHaveProperty("research_hashes");
    expect(run).not.toHaveProperty("base_packet");
  });

  it("does not reconstruct detail lanes from retired token and fact aliases", async () => {
    server.use(
      http.get(/.*\/api\/news\/items\/news-legacy-detail$/, () =>
        HttpResponse.json({
          ok: true,
          data: {
            row_id: "row-legacy-detail",
            news_item_id: "news-legacy-detail",
            lifecycle_status: "processed",
            headline: "Legacy detail",
            token_mentions: [{ display_symbol: "OLD", resolution_status: "resolved" }],
            fact_candidates: [{ event_type: "legacy", validation_status: "accepted" }],
          },
        }),
      ),
    );

    const item = await fetchNewsItem({ newsItemId: "news-legacy-detail" });

    expect(item.token_lanes).toEqual([]);
    expect(item.fact_lanes).toEqual([]);
  });
});

function newsSignalEnvelope(displaySignal: Record<string, unknown>) {
  return {
    display_signal: displaySignal,
    agent_signal: { status: "pending" },
    alert_eligibility: {
      in_app_eligible: true,
      external_push_ready: false,
      agent_status: "pending",
    },
  };
}
