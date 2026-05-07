export function gmgnTokenUrl(chain?: string | null, address?: string | null): string | null {
  const normalizedChain = chain?.trim().toLowerCase();
  const normalizedAddress = address?.trim();
  if (!normalizedChain || !normalizedAddress || normalizedChain === "evm_unknown" || normalizedChain === "evm") {
    return null;
  }
  const chainSlug =
    normalizedChain === "solana"
      ? "sol"
      : normalizedChain === "eip155:1"
        ? "eth"
        : normalizedChain === "eip155:56"
          ? "bsc"
          : normalizedChain === "eip155:8453"
            ? "base"
            : normalizedChain;
  return `https://gmgn.ai/${chainSlug}/token/${normalizedAddress}`;
}
