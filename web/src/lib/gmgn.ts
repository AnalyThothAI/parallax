export function gmgnTokenUrl(chain?: string | null, address?: string | null): string | null {
  const normalizedChain = chain?.trim().toLowerCase();
  const normalizedAddress = address?.trim();
  if (!normalizedChain || !normalizedAddress || normalizedChain === "evm_unknown" || normalizedChain === "evm") {
    return null;
  }
  const chainSlug = normalizedChain === "solana" ? "sol" : normalizedChain;
  return `https://gmgn.ai/${chainSlug}/token/${normalizedAddress}`;
}
