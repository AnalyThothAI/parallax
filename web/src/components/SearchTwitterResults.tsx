import type { SearchItem, TokenTimelinePost } from "../api/types";

type SearchTwitterResultsProps = {
  title?: string;
  posts?: TokenTimelinePost[];
  items?: SearchItem[];
};

export function SearchTwitterResults({
  title = "24h Twitter Results",
  posts = [],
  items = [],
}: SearchTwitterResultsProps) {
  const rows = posts.length ? posts.map(rowFromPost) : items.map(rowFromSearchItem);
  return (
    <section className="search-panel search-twitter-results">
      <header>
        <h3>{title}</h3>
        <span>{rows.length} rows</span>
      </header>
      {rows.length ? (
        <table>
          <thead>
            <tr>
              <th>time</th>
              <th>phase</th>
              <th>account</th>
              <th>content</th>
              <th>anchor</th>
              <th>id</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.id}>
                <td>{formatTime(row.receivedAtMs)}</td>
                <td>{row.phase}</td>
                <td>{row.handle ? `@${row.handle}` : "-"}</td>
                <td>{row.text}</td>
                <td>{row.anchor}</td>
                <td>
                  <code>{row.id}</code>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <div className="empty-state">暂无 24h Twitter 结果</div>
      )}
    </section>
  );
}

function rowFromPost(post: TokenTimelinePost) {
  const price = post.price as { price_usd?: number | null; status?: string | null } | undefined;
  return {
    id: post.event_id,
    receivedAtMs: post.received_at_ms,
    phase: post.stage_phase ?? "post",
    handle: post.handle ?? post.author_handle,
    text: post.text ?? "",
    anchor:
      price?.price_usd !== undefined && price?.price_usd !== null
        ? `$${price.price_usd}`
        : (price?.status ?? "-"),
  };
}

function rowFromSearchItem(item: SearchItem) {
  return {
    id: item.event.event_id,
    receivedAtMs: item.event.received_at_ms,
    phase: item.match_type,
    handle: item.event.author_handle,
    text: item.event.text_clean ?? "",
    anchor: "-",
  };
}

function formatTime(value?: number | null): string {
  if (!value) return "-";
  return new Date(value).toISOString().slice(11, 16);
}
