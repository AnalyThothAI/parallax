import { tokenImageUrl } from "@shared/model/tokenImageUrl";
import { describe, expect, it } from "vitest";

describe("tokenImageUrl", () => {
  it("routes Binance token images through the same-origin image proxy", () => {
    const sourceUrl = "https://bin.bnbstatic.com/image/admin_mgs_image_upload/btc.png";

    expect(tokenImageUrl(sourceUrl)).toBe(`/api/token-image?url=${encodeURIComponent(sourceUrl)}`);
  });

  it("routes GMGN external GIFs through the same-origin image proxy", () => {
    const sourceUrl = "https://gmgn.ai/external-res/75864d15bdf7017b16529090ea5960d9.gif";

    expect(tokenImageUrl(sourceUrl)).toBe(`/api/token-image?url=${encodeURIComponent(sourceUrl)}`);
  });

  it("leaves other token image hosts untouched", () => {
    expect(tokenImageUrl("https://gmgn.ai/external-res/token.webp")).toBe(
      "https://gmgn.ai/external-res/token.webp",
    );
    expect(tokenImageUrl(" https://cdn.example.test/token.png ")).toBe(
      "https://cdn.example.test/token.png",
    );
  });

  it("returns null for empty values", () => {
    expect(tokenImageUrl(null)).toBeNull();
    expect(tokenImageUrl("   ")).toBeNull();
  });
});
