import ReactDOM from "react-dom/client";

import "./styles/tailwind.css";
import "./styles/tokens.css";
import "./styles/base.css";
import { AppRoot } from "./app/AppRoot";
import cockpitStyles from "./features/cockpit/ui/cockpit.module.css";
import liveStyles from "./features/live/ui/live.module.css";
import searchStyles from "./features/search/ui/search.module.css";
import signalLabStyles from "./features/signal-lab/ui/signalLab.module.css";
import stocksStyles from "./features/stocks/ui/stocks.module.css";
import tokenTargetStyles from "./features/token-target/ui/tokenTarget.module.css";
import watchlistStyles from "./features/watchlist/ui/watchlist.module.css";
import obsidianStyles from "./shared/ui/obsidian.module.css";
import sharedStyles from "./shared/ui/shared.module.css";

document.documentElement.classList.add(
  ...[
    sharedStyles.moduleKeep,
    obsidianStyles.moduleKeep,
    cockpitStyles.moduleKeep,
    liveStyles.moduleKeep,
    searchStyles.moduleKeep,
    signalLabStyles.moduleKeep,
    stocksStyles.moduleKeep,
    tokenTargetStyles.moduleKeep,
    watchlistStyles.moduleKeep,
  ].filter(Boolean),
);

ReactDOM.createRoot(document.getElementById("root")!).render(<AppRoot />);
