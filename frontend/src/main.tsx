// React application entry point mounting root component.

import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App.tsx";
import "~/styles/globals.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>
);
