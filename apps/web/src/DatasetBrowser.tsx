import { useQuery } from "@tanstack/react-query";
import type { DatasetMetadata, DatasetReader } from "./datasets";

const queryPolicy = {
  retry: false,
  refetchOnWindowFocus: false,
  refetchOnReconnect: false,
  gcTime: 0,
} as const;

function Provenance({ metadata: m }: { metadata: DatasetMetadata }) {
  const capture = m.raw.capture;
  return (
    <details>
      <summary>Provenance and eligibility</summary>
      <dl className="facts">
        <dt>Source ID</dt>
        <dd>{capture.data_source_id.value}</dd>
        <dt>Resource</dt>
        <dd>{capture.resource}</dd>
        <dt>Raw SHA-256</dt>
        <dd>
          <code>{m.raw.sha256}</code>
        </dd>
        <dt>Raw size</dt>
        <dd>{m.raw.size_bytes} bytes</dd>
        <dt>Ingested at</dt>
        <dd>{capture.ingested_at}</dd>
        <dt>Available at</dt>
        <dd>
          {capture.available_at ?? "Unknown — not historically established"}
        </dd>
        <dt>Observed at</dt>
        <dd>{capture.observed_at ?? "Unknown"}</dd>
        <dt>Effective at</dt>
        <dd>{capture.effective_at ?? "Unknown"}</dd>
        <dt>Parser version</dt>
        <dd>{m.parser_version}</dd>
        <dt>Normalizer version</dt>
        <dd>{m.normalizer_version}</dd>
      </dl>
      <p>Backend exclusion reasons:</p>
      <ul>
        {m.ineligibility_reasons.map((reason) => (
          <li key={reason}>
            <code>{reason}</code>
          </li>
        ))}
      </ul>
    </details>
  );
}

function DatasetCard({
  metadata: m,
  reader,
  listingVersion,
}: {
  metadata: DatasetMetadata;
  reader: DatasetReader;
  listingVersion: number;
}) {
  const replay = useQuery({
    ...queryPolicy,
    queryKey: ["dataset-inspection", listingVersion, m.root_hash],
    queryFn: ({ signal }) => reader.inspect(m.root_hash, signal),
    enabled: false,
  });
  const result =
    !replay.isFetching && !replay.isError ? replay.data : undefined;
  return (
    <article className="dataset-card" aria-label={m.operator_label}>
      <h3>{m.operator_label}</h3>
      <p className="muted">
        Operator annotation, not a verified competition name.
      </p>
      <p className="root-hash">
        <span>Root SHA-256</span>
        <br />
        <code>{m.root_hash}</code>
      </p>
      <p>
        {m.declared_row_count} declared records · {m.page_count} pages
      </p>
      <p className="restriction">Replay-only · Not backtest-eligible</p>
      <p>
        Metadata listing: NOT_CHECKED — listing does not replay retained
        artifacts.
      </p>
      <Provenance metadata={m} />
      <div className="inspection">
        <button
          disabled={replay.isFetching}
          onClick={() => void replay.refetch()}
        >
          {replay.isFetching ? "Inspecting replay…" : "Inspect replay"}
        </button>
        <p role="status" aria-live="polite">
          {replay.isFetching
            ? "Reading retained artifacts. Previous results are not shown during this check."
            : replay.isError
              ? "Inspection failed or timed out. No current verification is available. Check local storage and try again."
              : result
                ? "Retained replay verified at the time below — not a durable guarantee."
                : "No replay inspection in this view. Inspect explicitly to check retained artifacts."}
        </p>
        {result && (
          <div className="replay-result">
            <h4>Backend replay observation: {result.replay_status}</h4>
            <dl className="facts">
              <dt>Completed at</dt>
              <dd>{result.replay_completed_at}</dd>
              <dt>Verified receipts</dt>
              <dd>{result.receipt_count}</dd>
              <dt>Participants</dt>
              <dd>{result.participant_count}</dd>
              <dt>Asserted kickoff range</dt>
              <dd>
                {result.asserted_starts_at_min} →{" "}
                {result.asserted_starts_at_max}
              </dd>
              <dt>Sport IDs</dt>
              <dd>{result.sport_ids.join(", ")}</dd>
              <dt>Competition IDs</dt>
              <dd>{result.competition_ids.join(", ")}</dd>
              <dt>Season IDs</dt>
              <dd>{result.season_ids.join(", ")}</dd>
              <dt>Context versions</dt>
              <dd>{result.context_versions.join(", ")}</dd>
            </dl>
            <p>
              Replay does not verify provider rights, database acceptance or
              kickoff accuracy. Historical availability remains unproven; this
              is not training or backtest approval.
            </p>
          </div>
        )}
      </div>
    </article>
  );
}

export function DatasetBrowser({ reader }: { reader: DatasetReader }) {
  const catalog = useQuery({
    ...queryPolicy,
    queryKey: ["dataset-catalog"],
    queryFn: ({ signal }) => reader.list(signal),
  });
  return (
    <section className="panel" aria-labelledby="datasets-title">
      <p className="eyebrow">Private local research</p>
      <h2 id="datasets-title">Retained datasets</h2>
      <p className="restriction">Replay-only. Not backtest-eligible.</p>
      <p>
        Discover explicitly retained roots and inspect reproducibility. This
        does not establish historical availability or authorize training,
        backtesting or trading.
      </p>
      <button
        disabled={catalog.isFetching}
        onClick={() => void catalog.refetch()}
      >
        Refresh catalog
      </button>
      {catalog.isFetching ? (
        <p role="status">Loading retained catalog…</p>
      ) : catalog.isError ? (
        <p role="alert">
          Catalog unavailable or invalid. Start the configured local dataset API
          and Floci, then refresh.
        </p>
      ) : catalog.data?.items.length === 0 ? (
        <p role="status">
          No dataset roots are selected. Configure the private catalog to begin.
        </p>
      ) : (
        catalog.data?.items.map((item) => (
          <DatasetCard
            key={item.metadata.root_hash}
            metadata={item.metadata}
            reader={reader}
            listingVersion={catalog.dataUpdatedAt}
          />
        ))
      )}
      <p className="muted">
        No automatic replay, polling or retries. Results are session-only.
        Refreshing the catalog clears displayed inspections. Keep this interface
        on localhost.
      </p>
    </section>
  );
}
