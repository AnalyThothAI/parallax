import type { IChartApi } from "lightweight-charts";

export function observeChartHost(
  container: HTMLDivElement,
  chart: IChartApi,
  height: number,
): ResizeObserver | null {
  if (typeof ResizeObserver === "undefined") {
    return null;
  }
  const resizeObserver = new ResizeObserver((entries) => {
    const entry = entries[0];
    const width = Math.round(entry?.contentRect.width ?? container.clientWidth);
    if (width > 0) {
      chart.resize(width, height);
    }
  });
  resizeObserver.observe(container);
  return resizeObserver;
}
