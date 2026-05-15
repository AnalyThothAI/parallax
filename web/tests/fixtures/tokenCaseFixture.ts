import type { TokenCaseDossier, TokenPostsData } from "@lib/types";

const BASE_MS = 1_777_746_300_000;

export function tokenCaseFixture(): TokenCaseDossier {
  return {
    target: {
      target_type: "Asset",
      target_id: "asset:solana:token:FhoxjfsuStvRQKRXSuB9ZDB7WRGjqhUPxa3NztWspump",
      symbol: "HANSA",
      chain_id: "solana",
      address: "FhoxjfsuStvRQKRXSuB9ZDB7WRGjqhUPxa3NztWspump",
      status: "resolved",
      source: "registry_assets",
      reason: "TARGET_ID",
    },
    profile: {
      status: "ready",
      provider: "gmgn",
      observed_at_ms: BASE_MS - 60_000,
      identity: {
        symbol: "HANSA",
        name: "Hansa Network",
        logo_url: "https://example.test/hansa.png",
        description: "Socially discovered Solana token with fast scanner pickup.",
      },
      links: {
        website_url: "https://hansa.example",
        twitter_username: "hansa_sol",
        gmgn_url: "https://gmgn.ai/sol/token/FhoxjfsuStvRQKRXSuB9ZDB7WRGjqhUPxa3NztWspump",
      },
      source: {
        provider: "gmgn",
        raw_available: true,
      },
    },
    timeline: {
      query: {
        target_type: "Asset",
        target_id: "asset:solana:token:FhoxjfsuStvRQKRXSuB9ZDB7WRGjqhUPxa3NztWspump",
        window: "1h",
        scope: "all",
        bucket: "5m",
      },
      summary: {
        posts: 18,
        authors: 9,
        effective_authors: 7,
        first_seen_ms: BASE_MS - 42 * 60_000,
        latest_seen_ms: BASE_MS - 90_000,
        watched_posts: 4,
        phase: "expansion",
        top_author_share: 0.24,
        duplicate_text_share: 0.08,
        peak_posts_per_bucket: 6,
        peak_new_authors_per_bucket: 4,
        reproduction_rate: 1.7,
      },
      market_overlay: {
        target_type: "Asset",
        target_id: "asset:solana:token:FhoxjfsuStvRQKRXSuB9ZDB7WRGjqhUPxa3NztWspump",
        chain_id: "solana",
        address: "FhoxjfsuStvRQKRXSuB9ZDB7WRGjqhUPxa3NztWspump",
        symbol: "HANSA",
        provider: "gmgn",
      },
      stages: [
        stage("stage-seed", "seed", BASE_MS - 42 * 60_000, 3, 2, 1),
        stage("stage-ignition", "ignition", BASE_MS - 24 * 60_000, 7, 4, 2),
        stage("stage-expansion", "expansion", BASE_MS - 9 * 60_000, 8, 5, 1),
      ],
      buckets: [],
      authors: [
        {
          handle: "earlyape",
          first_seen_ms: BASE_MS - 42 * 60_000,
          latest_seen_ms: BASE_MS - 30 * 60_000,
          posts: 3,
          followers: 42_000,
          role: "seed",
          quality_score: 78,
        },
      ],
      posts: [],
      cascade: {
        edges: [],
        unresolved_parents: [],
      },
      returned_count: 3,
      has_more: false,
    },
    posts: tokenCasePostsFixture(),
    agent_brief: {
      schema_version: "search_agent_brief_v1",
      generated_by: "deterministic",
      project_summary: {
        one_liner: "HANSA is moving from scanner discovery into broader Solana timeline chatter.",
        summary_zh:
          "HANSA 在观察名单账号和独立扫描账号之间同步扩散，当前更像早期传播案例而不是成熟共识。",
        current_state: "expansion",
        data_gaps: ["live market snapshot missing", "official liquidity route not confirmed"],
        evidence_event_ids: ["event-hansa-1", "event-hansa-2"],
      },
      propagation: {
        summary_zh: "先由早期账号发现，随后 scanner 和二级账号开始复述，传播结构已脱离单点。",
        phases: [
          {
            phase: "seed",
            window_label: "T-42m",
            tweets: 3,
            authors: 2,
            lead_accounts: ["earlyape"],
            read_zh: "种子账号先给出合约线索。",
            evidence_event_ids: ["event-hansa-1"],
          },
          {
            phase: "ignition",
            window_label: "T-24m",
            tweets: 7,
            authors: 4,
            lead_accounts: ["scannerjoe"],
            read_zh: "scanner 账号开始把 HANSA 推给更宽受众。",
            evidence_event_ids: ["event-hansa-2"],
          },
          {
            phase: "expansion",
            window_label: "T-9m",
            tweets: 8,
            authors: 5,
            lead_accounts: ["solwatch"],
            read_zh: "独立作者加入，重复文本占比仍低。",
            evidence_event_ids: ["event-hansa-3"],
          },
        ],
        key_accounts: [
          { handle: "earlyape", role: "seed lead", posts: 3, first_seen_ms: BASE_MS - 42 * 60_000 },
          {
            handle: "scannerjoe",
            role: "ignition lead",
            posts: 2,
            first_seen_ms: BASE_MS - 24 * 60_000,
          },
          {
            handle: "solwatch",
            role: "expansion lead",
            posts: 2,
            first_seen_ms: BASE_MS - 9 * 60_000,
          },
        ],
      },
      bull_bear: {
        stance: "watch",
        bull: {
          thesis_zh:
            "传播来自多个独立账号且 watched 账号参与，若市场数据补齐，可能进入更高质量 watch。",
          evidence_event_ids: ["event-hansa-1", "event-hansa-3"],
          triggers_zh: [
            "market cap and liquidity become ready",
            "watched account follow-up appears",
          ],
        },
        bear: {
          thesis_zh: "当前缺少可靠实时市场与官方路由，传播仍可能只是 scanner 噪声。",
          evidence_event_ids: ["event-hansa-2"],
          invalidations_zh: [
            "liquidity remains missing",
            "follow-up authors collapse to one cluster",
          ],
        },
      },
    },
    market_live: {
      status: "missing",
      target_type: "Asset",
      target_id: "asset:solana:token:FhoxjfsuStvRQKRXSuB9ZDB7WRGjqhUPxa3NztWspump",
      provider: null,
      price_usd: null,
      market_cap_usd: null,
      liquidity_usd: null,
      holders: null,
      observed_at_ms: null,
      error: "live snapshot unavailable in fixture",
    },
  };
}

export function tokenCasePostsFixture(): TokenPostsData {
  return {
    query: {
      target_type: "Asset",
      target_id: "asset:solana:token:FhoxjfsuStvRQKRXSuB9ZDB7WRGjqhUPxa3NztWspump",
      window: "1h",
      scope: "all",
      range: "current_window",
      sort: "recent",
    },
    score_window: { window: "1h" },
    total_count: 18,
    returned_count: 3,
    has_more: true,
    next_cursor: "cursor-hansa-3",
    items: [
      post(
        "event-hansa-3",
        "solwatch",
        "Expansion leg forming on $HANSA. CA still needs market confirmation.",
        82,
        true,
      ),
      post(
        "event-hansa-2",
        "scannerjoe",
        "$HANSA scanner pickup. Watching independent follow-through.",
        74,
        false,
      ),
      post("event-hansa-1", "earlyape", "First $HANSA mention with contract evidence.", 91, true),
    ],
  };
}

function stage(
  stageId: string,
  phase: string,
  startMs: number,
  posts: number,
  authors: number,
  watchedPosts: number,
) {
  return {
    stage_id: stageId,
    phase,
    start_ms: startMs,
    end_ms: startMs + 10 * 60_000,
    duration_ms: 10 * 60_000,
    trigger_reason: `${phase}_threshold`,
    confidence: 0.82,
    people: {
      posts,
      authors,
      new_authors: authors,
      watched_posts: watchedPosts,
      watched_authors: Math.min(watchedPosts, authors),
      top_author_share: 0.25,
    },
    representative_event_ids: [`event-hansa-${phase}`],
    price: {
      status: "missing",
      observation_ids: [],
    },
    risks: [],
  };
}

function post(eventId: string, handle: string, text: string, quality: number, watched: boolean) {
  return {
    event_id: eventId,
    tweet_id: eventId.replace("event-", "tweet-"),
    handle,
    text,
    url: `https://x.com/${handle}/status/${eventId}`,
    received_at_ms: BASE_MS - Number(eventId.slice(-1)) * 5 * 60_000,
    mention_source: "cashtag",
    target_type: "Asset",
    target_id: "asset:solana:token:FhoxjfsuStvRQKRXSuB9ZDB7WRGjqhUPxa3NztWspump",
    attribution_status: "ca_evidence",
    attribution_confidence: 0.91,
    attribution_weight: 1,
    is_watched: watched,
    event_type: "tweet",
    catalyst_score: quality - 8,
    stage_phase: eventId.endsWith("3") ? "expansion" : eventId.endsWith("2") ? "ignition" : "seed",
    author_role: watched ? "watched" : "scanner",
    is_stage_representative: true,
    post_quality: {
      score: quality,
      score_version: "pq_fixture_v1",
      reasons: ["ca_evidence", "specific thesis"],
      risks: [],
      contributions: [
        { feature: "ca_evidence", value: 0.34, reason: "contract address included" },
        { feature: "specificity", value: 0.28, reason: "non-generic token language" },
        { feature: "source_quality", value: 0.22, reason: "account has prior useful calls" },
      ],
      risk_caps: [],
    },
  };
}
