import type { TokenFactorFamilyKey, TokenFactorSnapshot } from "@lib/types";

export const TOKEN_FACTOR_SNAPSHOT_SCHEMA = "token_factor_snapshot_v3_social_attention";
const TOP_LEVEL_KEYS = new Set([
  "schema_version",
  "subject",
  "market",
  "gates",
  "data_health",
  "families",
  "normalization",
  "composite",
  "provenance",
]);
const ALPHA_FAMILIES: TokenFactorFamilyKey[] = [
  "social_heat",
  "social_propagation",
  "semantic_catalyst",
  "timing_risk",
];
const FAMILY_KEYS = new Set(["raw_score", "score", "weight", "data_health", "facts", "factors"]);
const PROVENANCE_KEYS = new Set(["source_event_ids", "computed_at_ms"]);
const MARKET_KEYS = new Set(["event_anchor", "decision_latest", "readiness"]);
const MARKET_READINESS_KEYS = new Set([
  "anchor_status",
  "latest_status",
  "dex_floor_status",
  "missing_fields",
  "stale_fields",
]);
const LEGACY_GATE_KEY = ["hard", "gates"].join("_");

export function requireTokenFactorSnapshot(
  value: unknown,
  fieldName = "factor_snapshot",
): TokenFactorSnapshot {
  if (!isRecord(value)) {
    throw new Error(`token_factor_snapshot_contract:${fieldName}`);
  }
  if (value.schema_version !== TOKEN_FACTOR_SNAPSHOT_SCHEMA) {
    throw new Error(`token_factor_snapshot_contract:${fieldName}.schema_version`);
  }
  if (LEGACY_GATE_KEY in value) {
    throw new Error(`token_factor_snapshot_contract:${fieldName}.${LEGACY_GATE_KEY}`);
  }

  const keys = Object.keys(value);
  const missing = [...TOP_LEVEL_KEYS].find((key) => !keys.includes(key));
  if (missing) {
    throw new Error(`token_factor_snapshot_contract:${fieldName}.${missing}`);
  }
  const extra = keys.find((key) => !TOP_LEVEL_KEYS.has(key));
  if (extra) {
    throw new Error(`token_factor_snapshot_contract:${fieldName}.${extra}`);
  }

  for (const key of [
    "subject",
    "market",
    "gates",
    "data_health",
    "families",
    "normalization",
    "composite",
    "provenance",
  ] as const) {
    if (!isRecord(value[key])) {
      throw new Error(`token_factor_snapshot_contract:${fieldName}.${key}`);
    }
  }

  const market = value.market as Record<string, unknown>;
  requireExactKeys(market, MARKET_KEYS, `${fieldName}.market`);
  for (const key of ["event_anchor", "decision_latest"] as const) {
    if (market[key] !== null && !isRecord(market[key])) {
      throw new Error(`token_factor_snapshot_contract:${fieldName}.market.${key}`);
    }
  }
  if (!isRecord(market.readiness)) {
    throw new Error(`token_factor_snapshot_contract:${fieldName}.market.readiness`);
  }
  requireExactKeys(market.readiness, MARKET_READINESS_KEYS, `${fieldName}.market.readiness`);
  for (const key of ["missing_fields", "stale_fields"] as const) {
    if (!Array.isArray(market.readiness[key])) {
      throw new Error(`token_factor_snapshot_contract:${fieldName}.market.readiness.${key}`);
    }
  }

  const families = value.families as Record<string, unknown>;
  const familyKeys = Object.keys(families);
  const extraFamily = familyKeys.find(
    (family) => !ALPHA_FAMILIES.includes(family as TokenFactorFamilyKey),
  );
  if (extraFamily) {
    throw new Error(`token_factor_snapshot_contract:${fieldName}.families.${extraFamily}`);
  }
  const missingFamily = ALPHA_FAMILIES.find((family) => !familyKeys.includes(family));
  if (missingFamily) {
    throw new Error(`token_factor_snapshot_contract:${fieldName}.families.${missingFamily}`);
  }
  for (const family of ALPHA_FAMILIES) {
    const familyBlock = families[family];
    if (!isRecord(familyBlock)) {
      throw new Error(`token_factor_snapshot_contract:${fieldName}.families.${family}`);
    }
    requireExactKeys(familyBlock, FAMILY_KEYS, `${fieldName}.families.${family}`);
    for (const key of ["raw_score", "score", "weight"] as const) {
      if (typeof familyBlock[key] !== "number" || !Number.isFinite(familyBlock[key])) {
        throw new Error(`token_factor_snapshot_contract:${fieldName}.families.${family}.${key}`);
      }
    }
    if (typeof familyBlock.data_health !== "string" || !familyBlock.data_health) {
      throw new Error(`token_factor_snapshot_contract:${fieldName}.families.${family}.data_health`);
    }
    if (!isRecord(familyBlock.facts)) {
      throw new Error(`token_factor_snapshot_contract:${fieldName}.families.${family}.facts`);
    }
    if (!isRecord(familyBlock.factors)) {
      throw new Error(`token_factor_snapshot_contract:${fieldName}.families.${family}.factors`);
    }
  }

  const composite = value.composite as Record<string, unknown>;
  if (typeof composite.recommended_decision !== "string" || !composite.recommended_decision) {
    throw new Error(`token_factor_snapshot_contract:${fieldName}.composite.recommended_decision`);
  }
  const provenance = value.provenance as Record<string, unknown>;
  requireExactKeys(provenance, PROVENANCE_KEYS, `${fieldName}.provenance`);
  if (
    !Array.isArray(provenance.source_event_ids) ||
    provenance.source_event_ids.length === 0 ||
    provenance.source_event_ids.some((item) => typeof item !== "string" || !item)
  ) {
    throw new Error(`token_factor_snapshot_contract:${fieldName}.provenance.source_event_ids`);
  }
  if (
    typeof provenance.computed_at_ms !== "number" ||
    !Number.isFinite(provenance.computed_at_ms)
  ) {
    throw new Error(`token_factor_snapshot_contract:${fieldName}.provenance.computed_at_ms`);
  }

  return value as TokenFactorSnapshot;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function requireExactKeys(
  value: Record<string, unknown>,
  allowed: Set<string>,
  fieldName: string,
): void {
  const keys = Object.keys(value);
  const missing = [...allowed].find((key) => !keys.includes(key));
  if (missing) {
    throw new Error(`token_factor_snapshot_contract:${fieldName}.${missing}`);
  }
  const extra = keys.find((key) => !allowed.has(key));
  if (extra) {
    throw new Error(`token_factor_snapshot_contract:${fieldName}.${extra}`);
  }
}
