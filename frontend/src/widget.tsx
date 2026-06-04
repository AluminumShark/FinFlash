// Embeddable widget entry. Host page usage:
//   <div id="finflash-widget" data-api-base="https://api.example.com"></div>
//   <script src="finflash-widget.iife.js"></script>
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { App } from "./App";
import "./index.css";

function mount() {
  const el = document.getElementById("finflash-widget");
  if (!el) return;
  const apiBase = el.getAttribute("data-api-base");
  if (apiBase) (window as { FINFLASH_API_BASE?: string }).FINFLASH_API_BASE = apiBase;
  createRoot(el).render(
    <StrictMode>
      <App embedded />
    </StrictMode>,
  );
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", mount);
} else {
  mount();
}
