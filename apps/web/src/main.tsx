import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { App } from "./App";
import { createHealthReader } from "./health";
import "./style.css";

const queryClient = new QueryClient();
const readHealth = createHealthReader(
  new URL("/api", window.location.origin).href,
);
const root = document.getElementById("root");
if (!root) throw new Error("Missing application root");
createRoot(root).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <App readHealth={readHealth} />
    </QueryClientProvider>
  </StrictMode>,
);
