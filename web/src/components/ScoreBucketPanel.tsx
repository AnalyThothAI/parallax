import type { ScoreBucketItem } from "../api/types";
import { formatPercentShare, formatSignedPercent } from "../lib/format";

type ScoreBucketPanelProps = {
  items: ScoreBucketItem[];
};

export function ScoreBucketPanel({ items }: ScoreBucketPanelProps) {
  return (
    <section className="score-bucket-panel ledger-box">
      <h3>Score Buckets</h3>
      <table className="score-bucket-table">
        <thead>
          <tr>
            <th>bucket</th>
            <th>samples</th>
            <th>abnormal</th>
            <th>hit</th>
            <th>settled</th>
          </tr>
        </thead>
        <tbody>
          {items.map((item) => (
            <tr className="score-bucket-row" key={item.bucket}>
              <td>{item.bucket}</td>
              <td>{item.sample_count}</td>
              <td>
                <span className="score-bucket-bar">
                  <i className={item.avg_abnormal_return >= 0 ? "positive" : "negative"} style={{ width: `${bucketWidth(item.avg_abnormal_return)}%` }} />
                </span>
                <b className={item.avg_abnormal_return >= 0 ? "positive" : "negative"}>{formatSignedPercent(item.avg_abnormal_return)}</b>
              </td>
              <td>{formatPercentShare(item.hit_rate)}</td>
              <td>
                {item.settled_count}/{item.settled_count + item.pending_count}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {items.length === 0 ? <div className="empty-state">score bucket read model not available</div> : null}
    </section>
  );
}

function bucketWidth(value: number): number {
  return Math.max(4, Math.min(100, Math.round(Math.abs(value) * 3000)));
}
