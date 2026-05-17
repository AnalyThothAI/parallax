type TokenImageProxyRule = {
  host: string;
  pathPrefixes: string[];
  suffixes?: string[];
};

const TOKEN_IMAGE_PROXY_RULES: TokenImageProxyRule[] = [
  { host: "bin.bnbstatic.com", pathPrefixes: ["/"] },
  { host: "gmgn.ai", pathPrefixes: ["/external-res/"], suffixes: [".gif"] },
];

export function tokenImageUrl(value?: string | null): string | null {
  const rawUrl = value?.trim();
  if (!rawUrl) {
    return null;
  }

  try {
    const url = new URL(rawUrl);
    if (shouldProxyTokenImage(url)) {
      return `/api/token-image?url=${encodeURIComponent(url.toString())}`;
    }
  } catch {
    return rawUrl;
  }

  return rawUrl;
}

function shouldProxyTokenImage(url: URL): boolean {
  if (url.protocol !== "https:") {
    return false;
  }
  const host = url.hostname.toLowerCase();
  const path = url.pathname.toLowerCase();
  return TOKEN_IMAGE_PROXY_RULES.some((rule) => {
    if (rule.host !== host || !rule.pathPrefixes.some((prefix) => path.startsWith(prefix))) {
      return false;
    }
    return rule.suffixes ? rule.suffixes.some((suffix) => path.endsWith(suffix)) : true;
  });
}
