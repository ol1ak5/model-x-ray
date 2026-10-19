import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import App from "./App";
import "./styles/tokens.css";
import "./styles/base.css";
import { THEME, VARIANT } from "./theme";

document.documentElement.dataset.theme = THEME;
document.documentElement.dataset.variant = VARIANT;

createRoot(document.getElementById("root") as HTMLElement).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
