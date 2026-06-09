import type { MacroAssetCorrelationData } from "@lib/types";

import { assetLabel, signedCorrelationLabel } from "../../model/macroCorrelationModel";

type CorrelationPair = MacroAssetCorrelationData["pairs"][number];

export function CorrelationRead({
  data,
  negativePair,
  positivePair,
  titleByKey,
}: {
  data: MacroAssetCorrelationData;
  negativePair: CorrelationPair | null;
  positivePair: CorrelationPair | null;
  titleByKey: Record<string, string>;
}) {
  return (
    <div className="macro-correlation-read">
      <p>
        {data.window} 滚动收益相关性覆盖 {data.assets.length} 个资产，
        {data.data_gaps.length > 0 ? "仍有样本缺口需要在诊断区确认。" : "当前覆盖完整。"}
      </p>
      <dl className="macro-correlation-read-facts" aria-label="相关性摘要">
        <ReadFact label="窗口" value={data.window} />
        <ReadFact label="资产数" value={String(data.assets.length)} />
        <ReadFact label="最强同向" value={pairLabel(positivePair, titleByKey)} />
        <ReadFact label="最强对冲" value={pairLabel(negativePair, titleByKey)} />
      </dl>
    </div>
  );
}

function ReadFact({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt>{label}</dt>
      <dd>{value}</dd>
    </div>
  );
}

function pairLabel(pair: CorrelationPair | null, titleByKey: Record<string, string>): string {
  if (!pair) return "暂无";
  return `${assetLabel(pair.left, titleByKey)} / ${assetLabel(pair.right, titleByKey)} ${signedCorrelationLabel(
    pair.correlation,
  )}`;
}
