import { Link } from "react-router-dom";

import type { AssetMarketGroup } from "../../model/macroAssetOverviewModel";
import { MacroTableFrame } from "../tables/MacroTableFrame";

import "./macroAssetOverview.css";

export function AssetMarketDashboard({ groups }: { groups: AssetMarketGroup[] }) {
  if (groups.length === 0) {
    return <p className="macro-table-source-note">大类资产快照暂无可展示行。</p>;
  }
  return (
    <div className="macro-assets-market-board">
      {groups.map((group) => (
        <article className="macro-assets-group" key={group.key}>
          <div className="macro-assets-group-head">
            <h4>{group.title}</h4>
            <Link to={group.route}>查看{group.title}详情</Link>
          </div>
          <MacroTableFrame caption={group.title} minWidth={340} stickyFirstColumn>
            <table aria-label={group.title} className="macro-assets-market-table">
              <caption>{group.title}</caption>
              <thead>
                <tr>
                  <th scope="col">代码</th>
                  <th scope="col">名称</th>
                  <th scope="col">最新</th>
                  <th scope="col">20日变化</th>
                  <th scope="col">质量</th>
                </tr>
              </thead>
              <tbody>
                {group.rows.length > 0 ? (
                  group.rows.map((row) => (
                    <tr key={row.id}>
                      <th scope="row">{row.symbol}</th>
                      <td className="macro-assets-market-name">
                        <span>{row.name}</span>
                        <span className="macro-assets-row-quality">{row.quality}</span>
                      </td>
                      <td>{row.latest}</td>
                      <td data-tone={row.deltaTone}>{row.delta}</td>
                      <td className="macro-assets-quality-cell">{row.quality}</td>
                    </tr>
                  ))
                ) : (
                  <tr>
                    <td className="macro-assets-market-empty" colSpan={5}>
                      暂无{group.title}快照
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </MacroTableFrame>
        </article>
      ))}
    </div>
  );
}
