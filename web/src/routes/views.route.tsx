import { MacroViewsPage } from "@features/views";

export function ViewsRoute({ token }: { token: string }) {
  return <MacroViewsPage token={token} />;
}
