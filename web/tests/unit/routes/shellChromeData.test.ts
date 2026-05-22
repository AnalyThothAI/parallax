import { shouldHandleLiveWindowHotkey } from "@routes/shellChromeData";
import { describe, expect, it } from "vitest";

describe("shellChromeData", () => {
  it("keeps live window hotkeys scoped to routes that own shell window controls", () => {
    expect(shouldHandleLiveWindowHotkey("/", "1")).toBe(true);
    expect(shouldHandleLiveWindowHotkey("/stocks", "4")).toBe(true);
    expect(shouldHandleLiveWindowHotkey("/stocks?scope=matched", "2")).toBe(true);

    expect(shouldHandleLiveWindowHotkey("/macro", "1")).toBe(false);
    expect(shouldHandleLiveWindowHotkey("/token/canonical/solana:abc", "3")).toBe(false);
    expect(shouldHandleLiveWindowHotkey("/search", "4")).toBe(false);
    expect(shouldHandleLiveWindowHotkey("/", "/")).toBe(false);
  });
});
