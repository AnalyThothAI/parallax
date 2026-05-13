type AppEnv = {
  apiBaseUrl: string;
  wsUrl: string;
  mode: string;
};

function sameOrigin(): string {
  return window.location.origin;
}

function sameOriginWsUrl(): string {
  const url = new URL(sameOrigin());
  url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
  url.pathname = "/ws";
  url.search = "";
  url.hash = "";
  return url.toString();
}

export const env: AppEnv = {
  apiBaseUrl: import.meta.env.VITE_API_BASE_URL || sameOrigin(),
  wsUrl: import.meta.env.VITE_WS_URL || sameOriginWsUrl(),
  mode: import.meta.env.MODE,
};
