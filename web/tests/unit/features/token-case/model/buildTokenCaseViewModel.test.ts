import { buildTokenCaseViewModel } from "@features/token-case/model/buildTokenCaseViewModel";
import { tokenCaseFixture } from "@tests/fixtures/tokenCaseFixture";
import { describe, expect, it } from "vitest";

describe("buildTokenCaseViewModel", () => {
  it("maps a token-case dossier into the narrative view model", () => {
    const dossier = tokenCaseFixture();

    const vm = buildTokenCaseViewModel({
      dossier,
      route: { window: "1h", scope: "all", postSort: "recent" },
      posts: dossier.posts,
      isLoadingPosts: false,
      isFetchingNextPage: false,
    });

    expect(vm.hero.title).toContain("$HANSA");
    expect(vm.metrics.map((metric) => metric.key)).toEqual([
      "mentions",
      "phase",
      "watched",
      "readiness",
    ]);
    expect(vm.propagation.stages).toHaveLength(3);
    expect(vm.timeline.items[0].quality.scoreLabel).toMatch(/PQ/);
    expect(vm.market.status).toBe("missing");
    expect(vm.bullBear.bull.title).toBe("Bull · 多头");
    expect(vm.bullBear.bear.title).toBe("Bear · 空头");
    expect(vm.dataGaps.length).toBeGreaterThan(0);
  });

  it("filters watched timeline items on the client", () => {
    const dossier = tokenCaseFixture();

    const vm = buildTokenCaseViewModel({
      dossier,
      route: { window: "1h", scope: "all", postSort: "watched" },
      posts: dossier.posts,
      isLoadingPosts: false,
      isFetchingNextPage: false,
    });

    expect(vm.timeline.items.every((item) => item.isWatched)).toBe(true);
  });
});
