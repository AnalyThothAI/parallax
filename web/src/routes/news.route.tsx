import { NewsPage } from "@features/news";
import { useParams } from "react-router-dom";

export const NewsRoute = ({ token }: { token: string }) => {
  const { newsItemId } = useParams();
  return <NewsPage newsItemId={newsItemId ?? null} token={token} />;
};
