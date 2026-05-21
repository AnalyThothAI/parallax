import { MacroPage } from "@features/macro";

export function MacroRoute({ token }: { token: string }) {
  return <MacroPage token={token} />;
}
