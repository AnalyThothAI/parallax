import type { TokenFactorFamilyKey, TokenFactorSnapshot } from "../api/types";

const TOKEN_FACTOR_SNAPSHOT_SCHEMA = "token_factor_snapshot_v2_alpha_gated";
const TOP_LEVEL_KEYS = new Set([
  "schema_version",
  "subject",
  "gates",
  "data_health",
  "families",
  "normalization",
  "composite",
  "provenance",
]);
const ALPHA_FAMILIES: TokenFactorFamilyKey[] = [
  "attention_heat",
  "diffusion_quality",
  "semantic_quality",
  "timing_response",
];
const FAMILY_KEYS = new Set(["raw_score", "score", "weight", "data_health", "facts", "factors"]);
const PROVENANCE_KEYS = new Set(["source_event_ids", "computed_at_ms"]);

export function requireTokenFactorSnapshotV2(
  value: unknown,
  fieldName = "factor_snapshot",
): TokenFactorSnapshot {
  if (!isRecord(value)) {
    throw new Error(`token_factor_snapshot_contract:${fieldName}`);
  }
  if (value.schema_version !== TOKEN_FACTOR_SNAPSHOT_SCHEMA) {
    throw new Error(`token_factor_snapshot_contract:${fieldName}.schema_version`);
  }
  if ("hard_gates" in value) {
    throw new Error(`token_factor_snapshot_contract:${fieldName}.hard_gates`);
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

  const families = value.families as Record<string, unknown>;
  const familyKeys = Object.keys(families);
  const missingFamily = ALPHA_FAMILIES.find((family) => !familyKeys.includes(family));
  if (missingFamily) {
    throw new Error(`token_factor_snapshot_contract:${fieldName}.families.${missingFamily}`);
  }
  const extraFamily = familyKeys.find(
    (family) => !ALPHA_FAMILIES.includes(family as TokenFactorFamilyKey),
  );
  if (extraFamily) {
    throw new Error(`token_factor_snapshot_contract:${fieldName}.families.${extraFamily}`);
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
