import { useQuery } from "@tanstack/react-query";
import type { createHealthReader } from "./health";

export function App({
  readHealth,
}: {
  readHealth: ReturnType<typeof createHealthReader>;
}) {
  const health = useQuery({
    queryKey: ["api", "health"],
    queryFn: ({ signal }) => readHealth(signal),
    retry: false,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
  });
  return (
    <main>
      <header>
        <span className="brand">EdgeEagle</span>
        <span>Foundation / Local development</span>
      </header>
      <section aria-labelledby="title">
        <p className="eyebrow">Sports-market research</p>
        <h1 id="title">Price, not picks.</h1>
        <p>
          Understand probability. Compare market prices. Test before taking
          risk.
        </p>
      </section>
      <section className="panel" aria-labelledby="connection">
        <h2 id="connection">API connection</h2>
        <p role="status" aria-live="polite">
          {health.isFetching
            ? "Checking API…"
            : health.isError
              ? "API unavailable. Start the local API and try again."
              : health.isSuccess
                ? "API process is responding."
                : "Waiting for a connection."}
        </p>
        <button
          disabled={health.isFetching}
          onClick={() => void health.refetch()}
        >
          {health.isError ? "Retry connection" : "Check again"}
        </button>
        <p className="muted">
          Liveness only. This does not verify database, provider, or model
          readiness.
        </p>
      </section>
      <footer>
        Foundation shell — market research, paper trading, and execution are not
        available yet.
      </footer>
    </main>
  );
}
