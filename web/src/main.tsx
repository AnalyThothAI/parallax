import ReactDOM from "react-dom/client";

import "./styles/tailwind.css";
import "./styles/tokens.css";
import "./styles/base.css";
import { AppRoot } from "./app/AppRoot";

ReactDOM.createRoot(document.getElementById("root")!).render(<AppRoot />);
