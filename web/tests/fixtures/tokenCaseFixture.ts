import type { TokenCaseDossier, TokenPostsData } from "@lib/types";

const BASE_MS = 1_777_746_300_000;
const HANSA_TOKEN_IMAGE_URL = "/api/token-images/hansa-local";

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
        logo_url: HANSA_TOKEN_IMAGE_URL,
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
      market_candles: {
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
    discussion_digest: {
      schema_version: "token_discussion_digest_v1",
      status: "ready",
      generated_at_ms: BASE_MS - 30_000,
      currentness: {
        display_status: "current",
        reason: "fingerprint_match",
        ready_source_event_count: 18,
        current_source_event_count: 18,
        delta_source_event_count: 0,
        delta_independent_author_count: 0,
        last_ready_computed_at_ms: BASE_MS - 30_000,
        epoch_policy_version: "token-narrative-epoch-v1",
      },
      dominant_narrative: {
        title: "Contract-confirmed Solana rotation",
        summary_zh: "HANSA 的核心叙事是 CA 证据帖被 scanner 与观察账号同步复述。",
        propagation_state: "expansion",
        trade_stance: "bullish",
        attention_valence: "informational",
        evidence_refs: [{ ref_type: "event", event_id: "event-hansa-1" }],
      },
      coverage: {
        semantic_coverage: 0.84,
        labeled_mentions: 15,
        source_mentions: 18,
        independent_authors: 7,
      },
      stance_mix: { bullish: 0.58, skeptical: 0.24, neutral: 0.18 },
      attention_valence_mix: { informational: 0.65, mixed: 0.35 },
      propagation: {
        state: "expansion",
        summary_zh: "语义扩散从 CA 证据帖进入 scanner 复述。",
        evidence_refs: [{ ref_type: "event", event_id: "event-hansa-2" }],
      },
      bull_bear: {
        stance: "watch",
        bull: {
          thesis_zh: "多个独立账号围绕 CA 证据复述，说明讨论已经脱离单一喊单源。",
          bullets_zh: [
            "market cap and liquidity become ready",
            "watched account follow-up appears",
          ],
          evidence_refs: [
            { ref_type: "event", event_id: "event-hansa-1" },
            { ref_type: "event", event_id: "event-hansa-3" },
          ],
        },
        bear: {
          thesis_zh: "市场快照和官方流动性路由仍缺失，scanner 复述可能高估了真实需求。",
          bullets_zh: ["liquidity remains missing", "follow-up authors collapse to one cluster"],
          evidence_refs: [{ ref_type: "event", event_id: "event-hansa-2" }],
        },
      },
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
      data_gaps: ["live market snapshot missing", "official liquidity route not confirmed"],
      evidence_refs: [{ ref_type: "event", event_id: "event-hansa-3" }],
    },
    narrative_clusters: [
      {
        cluster_key: "ca-proof",
        title: "CA proof",
        summary_zh: "种子账号先给出合约线索。",
        propagation_state: "seed",
        trade_stance: "bullish",
        attention_valence: "informational",
        mention_count: 3,
        author_count: 2,
        lead_accounts: [{ handle: "earlyape", role: "seed lead", posts: 3 }],
        evidence_refs: [{ ref_type: "event", event_id: "event-hansa-1" }],
      },
      {
        cluster_key: "scanner-pickup",
        title: "Scanner pickup",
        summary_zh: "scanner 账号开始把 HANSA 推给更宽受众。",
        propagation_state: "ignition",
        trade_stance: "neutral",
        attention_valence: "informational",
        mention_count: 7,
        author_count: 4,
        lead_accounts: [{ handle: "scannerjoe", role: "ignition lead", posts: 2 }],
        evidence_refs: [{ ref_type: "event", event_id: "event-hansa-2" }],
      },
      {
        cluster_key: "independent-follow-through",
        title: "Independent follow-through",
        summary_zh: "独立作者加入，重复文本占比仍低。",
        propagation_state: "expansion",
        trade_stance: "bullish",
        attention_valence: "mixed",
        mention_count: 8,
        author_count: 5,
        lead_accounts: [{ handle: "solwatch", role: "expansion lead", posts: 2 }],
        evidence_refs: [{ ref_type: "event", event_id: "event-hansa-3" }],
      },
    ],
    pulse_overlay: null,
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
    symbol: "HANSA",
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
    semantic: semanticForPost(eventId),
  };
}

function semanticForPost(eventId: string) {
  const isExpansion = eventId.endsWith("3");
  const isIgnition = eventId.endsWith("2");
  return {
    status: "ready",
    trade_stance: isIgnition ? "neutral" : "bullish",
    attention_valence: isExpansion ? "mixed" : "informational",
    narrative_cluster_key: isExpansion
      ? "independent-follow-through"
      : isIgnition
        ? "scanner-pickup"
        : "ca-proof",
    narrative_cluster_title: isExpansion
      ? "Independent follow-through"
      : isIgnition
        ? "Scanner pickup"
        : "CA proof",
    claim_type: isIgnition ? "scanner-repeat" : "contract-evidence",
    evidence_type: "post_text",
    semantic_confidence: 0.84,
    evidence_refs: [{ ref_type: "event", event_id: eventId }],
  };
}
