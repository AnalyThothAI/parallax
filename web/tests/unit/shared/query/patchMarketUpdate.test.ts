import type {
  ApiResponse,
  AssetFlowData,
  AssetFlowRow,
  LiveMarketUpdatePayload,
  TokenCaseDossier,
} from "@lib/types";
import {
  patchAssetFlowData,
  patchTokenCaseLiveMarketUpdate,
  patchTokenRadarLiveMarketUpdate,
} from "@shared/query/patchMarketUpdate";
import { QueryClient } from "@tanstack/react-query";
import { tokenRadarFixture } from "@tests/fixtures/appRouteFixtures";
import { tokenCaseFixture } from "@tests/fixtures/tokenCaseFixture";
import { describe, expect, it } from "vitest";

describe("liveMarketUpdatePatch", () => {
  it("patches matching token radar target rows", () => {
    const row = assetFlowRow("Asset", "asset:solana:token:abc");
    const other = assetFlowRow("Asset", "asset:solana:token:other");
    const data = assetFlowData({ targets: [row], attention: [other] });
    const update = liveMarketUpdate("Asset", "asset:solana:token:abc", 42);

    const patched = patchAssetFlowData(data, update);

    expect(patched.targets[0].factor_snapshot.market.decision_latest?.price_usd).toBe(42);
    expect(patched.targets[0]).not.toBe(row);
    expect(patched.attention[0]).toBe(other);
  });

  it("keeps non-matching data referentially stable", () => {
    const data = assetFlowData({
      targets: [assetFlowRow("Asset", "asset:solana:token:abc")],
      attention: [],
    });

    const patched = patchAssetFlowData(
      data,
      liveMarketUpdate("Asset", "asset:solana:token:missing", 99),
    );

    expect(patched).toBe(data);
  });

  it("patches every cached token radar query with a matching target", () => {
    const queryClient = new QueryClient();
    const first = apiResponse(
      assetFlowData({ targets: [assetFlowRow("Asset", "asset:solana:token:abc")], attention: [] }),
    );
    const second = apiResponse(
      assetFlowData({ targets: [], attention: [assetFlowRow("Asset", "asset:solana:token:abc")] }),
    );
    const unrelated = apiResponse(
      assetFlowData({
        targets: [assetFlowRow("Asset", "asset:solana:token:other")],
        attention: [],
      }),
    );
    queryClient.setQueryData(["token-radar", "1h", "all"], first);
    queryClient.setQueryData(["token-radar", "5m", "all"], second);
    queryClient.setQueryData(["token-radar", "1h", "matched"], unrelated);

    patchTokenRadarLiveMarketUpdate(
      queryClient,
      liveMarketUpdate("Asset", "asset:solana:token:abc", 77),
    );

    expect(
      queryClient.getQueryData<ApiResponse<AssetFlowData>>(["token-radar", "1h", "all"])?.data
        .targets[0].factor_snapshot.market.decision_latest?.price_usd,
    ).toBe(77);
    expect(
      queryClient.getQueryData<ApiResponse<AssetFlowData>>(["token-radar", "5m", "all"])?.data
        .attention[0].factor_snapshot.market.decision_latest?.price_usd,
    ).toBe(77);
    expect(
      queryClient.getQueryData<ApiResponse<AssetFlowData>>(["token-radar", "1h", "matched"]),
    ).toBe(unrelated);
  });

  it("patches matching token-case dossier live market snapshots", () => {
    const queryClient = new QueryClient();
    const matching = apiResponse(tokenCaseFixture());
    const unrelated = apiResponse({
      ...tokenCaseFixture(),
      target: {
        ...tokenCaseFixture().target,
        target_id: "asset:solana:token:other",
      },
    });
    queryClient.setQueryData(
      ["token-case", "Asset:asset:solana:token:abc", "1h", "all", 24],
      matching,
    );
    queryClient.setQueryData(
      ["token-case", "Asset:asset:solana:token:other", "1h", "all", 24],
      unrelated,
    );

    patchTokenCaseLiveMarketUpdate(
      queryClient,
      liveMarketUpdate(
        "Asset",
        "asset:solana:token:FhoxjfsuStvRQKRXSuB9ZDB7WRGjqhUPxa3NztWspump",
        123,
      ),
    );

    expect(
      queryClient.getQueryData<ApiResponse<TokenCaseDossier>>([
        "token-case",
        "Asset:asset:solana:token:abc",
        "1h",
        "all",
        24,
      ])?.data.market_live?.price_usd,
    ).toBe(123);
    expect(
      queryClient.getQueryData<ApiResponse<TokenCaseDossier>>([
        "token-case",
        "Asset:asset:solana:token:abc",
        "1h",
        "all",
        24,
      ])?.data.market_live?.status,
    ).toBe("live");
    expect(
      queryClient.getQueryData<ApiResponse<TokenCaseDossier>>([
        "token-case",
        "Asset:asset:solana:token:other",
        "1h",
        "all",
        24,
      ]),
    ).toBe(unrelated);
  });
});

function apiResponse<T>(data: T): ApiResponse<T> {
  return { ok: true, data };
}

function assetFlowData({
  targets,
  attention,
}: {
  targets: AssetFlowRow[];
  attention: AssetFlowRow[];
}): AssetFlowData {
  return {
    ...tokenRadarFixture(),
    targets,
    attention,
  };
}

function assetFlowRow(targetType: string, targetId: string): AssetFlowRow {
  return {
    factor_snapshot: {
      subject: { target_type: targetType, target_id: targetId },
      market: {
        event_anchor: null,
        decision_latest: null,
        readiness: {
          anchor_status: "missing",
          latest_status: "missing",
          dex_floor_status: "not_applicable",
          missing_fields: [],
          stale_fields: [],
        },
      },
    },
  } as unknown as AssetFlowRow;
}

function liveMarketUpdate(
  targetType: string,
  targetId: string,
  price: number,
): LiveMarketUpdatePayload {
  return {
    type: "live_market_update",
    target_type: targetType,
    target_id: targetId,
    market: {
      decision_latest: {
        target_type: targetType,
        target_id: targetId,
        source: "decision_latest",
        price_usd: price,
        price_basis: "usd",
        observed_at_ms: 2,
        received_at_ms: 2,
        provider: "test",
      },
    },
  };
}
