import { Link } from "react-router-dom";

import type { AssetMarketGroup } from "../../model/macroAssetOverviewModel";
import { MacroTableFrame } from "../tables/MacroTableFrame";

import "./macroAssetOverview.css";

export function AssetMarketDashboard({ groups }: { groups: AssetMarketGroup[] }) {
  if (groups.length === 0) {
    return null;
  }
  return (
    <div className="macro-assets-market-board">
      <nav aria-label="资产类别" className="macro-assets-group-rail">
        {groups.map((group) => (
          <a href={`#macro-assets-${group.key}`} key={group.key}>
            <span>{group.title}</span>
            <b>{group.rows.length}</b>
          </a>
        ))}
      </nav>
      {groups.map((group) => (
        <article className="macro-assets-group" id={`macro-assets-${group.key}`} key={group.key}>
          <div className="macro-assets-group-head">
            <div>
              <h4>{group.title}</h4>
              <span>{group.rows.length} 项</span>
            </div>
            <Link to={group.route}>{group.title}详情</Link>
          </div>
          <MacroTableFrame caption={group.title} hint={null} minWidth={340} stickyFirstColumn>
            <table aria-label={group.title} className="macro-assets-market-table">
              <caption>{group.title}</caption>
              <thead>
                <tr>
                  <th scope="col">代码</th>
                  <th scope="col">名称</th>
                  <th scope="col">最新</th>
                  <th scope="col">20日变化</th>
                  <th scope="col">日期</th>
                </tr>
              </thead>
              <tbody>
                {group.rows.map((row) => (
                  <tr key={row.id}>
                    <th scope="row">{row.symbol}</th>
                    <td className="macro-assets-market-name">
                      <span>{row.name}</span>
                      {row.quality ? (
                        <span className="macro-assets-row-quality">{row.quality}</span>
                      ) : null}
                    </td>
                    <td>{row.latest}</td>
                    <td data-tone={row.deltaTone}>{row.delta}</td>
                    <td className="macro-assets-date-cell">{row.asOf}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </MacroTableFrame>
        </article>
      ))}
    </div>
  );
}
