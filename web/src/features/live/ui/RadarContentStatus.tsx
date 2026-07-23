import { useEffect, useState } from "react";

import {
  deriveRadarStatus,
  formatRadarContentAge,
  type RadarHealth,
  type RadarStatusInput,
} from "../model/radarContentStatus";

export function RadarContentStatus({ status }: { status: RadarStatusInput }) {
  const nowMs = useSecondClock();
  const view = deriveRadarStatus(status, nowMs);
  const visibleLabel = statusLabel(view.health, view.ageSeconds);

  return (
    <>
      <div
        aria-label={visibleLabel}
        className="radar-content-status"
        data-health={view.health}
        data-testid="radar-content-status"
      >
        <span aria-hidden="true" className="radar-content-status-dot" />
        <span>{visibleLabel}</span>
      </div>
      <span aria-atomic="true" aria-live="polite" className="sr-only" role="status">
        {healthAnnouncement(view.health)}
      </span>
    </>
  );
}

function useSecondClock(): number {
  const [nowMs, setNowMs] = useState(() => Date.now());

  useEffect(() => {
    setNowMs(Date.now());
    const timer = window.setInterval(() => setNowMs(Date.now()), 1_000);
    return () => window.clearInterval(timer);
  }, []);

  return nowMs;
}

function statusLabel(health: RadarHealth, ageSeconds: number | null): string {
  if (health === "loading") {
    return "正在读取";
  }
  if (health === "unavailable") {
    return "Radar 不可用";
  }
  if (health === "delayed") {
    return ageSeconds === null
      ? "刷新延迟 · 暂无内容"
      : `刷新延迟 · 内容 ${formatRadarContentAge(ageSeconds)}`;
  }
  return ageSeconds === null
    ? "Radar 正常 · 暂无内容"
    : `最新内容 ${formatRadarContentAge(ageSeconds)}`;
}

function healthAnnouncement(health: RadarHealth): string {
  if (health === "healthy") {
    return "Radar 更新正常";
  }
  if (health === "delayed") {
    return "Radar 刷新延迟";
  }
  if (health === "unavailable") {
    return "Radar 不可用";
  }
  return "Radar 正在读取";
}
