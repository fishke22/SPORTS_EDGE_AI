import { FormEvent, lazy, Suspense, useEffect, useState } from "react";

import {
  fetchHealth,
  fetchForwardCollectionStatus,
  fetchMappingSummary,
  fetchMarketAnalysis,
  fetchMarketBaseline,
  fetchOperationalStatus,
  fetchPaperPortfolio,
  fetchProviderUsage,
  fetchResearchReadiness,
  type MappingSummary,
  type ForwardCollectionStatus,
  type MarketAnalysisResponse,
  type MarketBaselineResponse,
  type OperationalStatus,
  type PaperPortfolio,
  type ProviderUsageResponse,
  type ResearchReadinessStatus,
  type SystemHealth,
} from "./api";

const ProbabilityChart = lazy(() =>
  import("./ProbabilityChart").then((module) => ({ default: module.ProbabilityChart })),
);

const DEFAULT_EVENT = "SYNTH_NBA_001";
const DEFAULT_AS_OF = "2026-10-01T08:30:00Z";

function pct(value: number) {
  return `${(value * 100).toFixed(1)}%`;
}

function signed(value: number) {
  return `${value >= 0 ? "+" : ""}${(value * 100).toFixed(2)}%`;
}

export default function App() {
  const [health, setHealth] = useState<SystemHealth | null>(null);
  const [eventId, setEventId] = useState(DEFAULT_EVENT);
  const [asOf, setAsOf] = useState(DEFAULT_AS_OF);
  const [homeProbability, setHomeProbability] = useState(0.6);
  const [awayProbability, setAwayProbability] = useState(0.4);
  const [baseline, setBaseline] = useState<MarketBaselineResponse | null>(null);
  const [analysis, setAnalysis] = useState<MarketAnalysisResponse | null>(null);
  const [providerUsage, setProviderUsage] = useState<ProviderUsageResponse | null>(null);
  const [mappingSummary, setMappingSummary] = useState<MappingSummary | null>(null);
  const [paperPortfolio, setPaperPortfolio] = useState<PaperPortfolio | null>(null);
  const [collectionStatus, setCollectionStatus] = useState<ForwardCollectionStatus | null>(null);
  const [researchReadiness, setResearchReadiness] = useState<ResearchReadinessStatus | null>(null);
  const [operationalStatus, setOperationalStatus] = useState<OperationalStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    fetchHealth()
      .then(async (nextHealth) => {
        setHealth(nextHealth);
        if (!nextHealth.database_ready) {
          return;
        }
        const [usage, mapping, paper, collection, readiness, operations] = await Promise.all([
          fetchProviderUsage("provider_the_odds_api"),
          fetchMappingSummary("provider_the_odds_api", "TEAM"),
          fetchPaperPortfolio(),
          fetchForwardCollectionStatus("provider_the_odds_api"),
          fetchResearchReadiness(),
          fetchOperationalStatus(),
        ]);
        setProviderUsage(usage);
        setMappingSummary(mapping);
        setPaperPortfolio(paper);
        setCollectionStatus(collection);
        setResearchReadiness(readiness);
        setOperationalStatus(operations);
      })
      .catch((err: unknown) => {
        setError(err instanceof Error ? err.message : "Health check failed");
      });
  }, []);

  async function runAnalysis(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const [nextBaseline, nextAnalysis] = await Promise.all([
        fetchMarketBaseline(eventId, asOf),
        fetchMarketAnalysis(eventId, asOf, homeProbability, awayProbability),
      ]);
      setBaseline(nextBaseline);
      setAnalysis(nextAnalysis);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Analysis failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main>
      <header className="hero">
        <div>
          <p className="eyebrow">Portable quantitative research</p>
          <h1>SPORTS_EDGE_AI</h1>
          <p className="lede">
            Point-in-time 市場基準、模型機率、EV 與風控的同一條研究流程。
          </p>
        </div>
        <div className="health">
          <span className={health?.database_ready ? "dot ok" : "dot"} />
          <div>
            <strong>{health?.status ?? "checking"}</strong>
            <small>schema {health?.schema_version ?? "—"}</small>
          </div>
        </div>
      </header>

      <section className="operations-grid" aria-label="營運狀態">
        <article className="metric-card operation-card">
          <p className="eyebrow">Provider usage</p>
          <h2>The Odds API</h2>
          <strong className="operation-value">
            {providerUsage?.found && providerUsage.usage
              ? `${providerUsage.usage.requests_used} used`
              : "No live usage"}
          </strong>
          <small>
            {providerUsage?.found && providerUsage.usage
              ? `${providerUsage.usage.requests_remaining} provider credits remaining · local budget ${providerUsage.usage.local_monthly_budget}`
              : "Credential/live calls not required for synthetic research"}
          </small>
        </article>
        <article className="metric-card operation-card">
          <p className="eyebrow">Entity mapping</p>
          <h2>NBA teams</h2>
          <strong className="operation-value">
            {mappingSummary ? `${mappingSummary.approved_mapping_count} approved` : "—"}
          </strong>
          <small>
            {mappingSummary
              ? `${mappingSummary.pending_count} pending · ${mappingSummary.rejected_count} rejected`
              : "Review state unavailable"}
          </small>
        </article>
        <article className="metric-card operation-card">
          <p className="eyebrow">Forward collection</p>
          <h2>Point-in-time</h2>
          <strong className="operation-value">
            {collectionStatus ? `${collectionStatus.odds_snapshot_count} odds` : "—"}
          </strong>
          <small>
            {collectionStatus
              ? `${collectionStatus.current_due ? "current due" : "current fresh"} · ${collectionStatus.scores_due ? "scores due" : "scores fresh"} · ${collectionStatus.completed_result_count} results`
              : "Collection status unavailable"}
          </small>
        </article>
        <article className="metric-card operation-card">
          <p className="eyebrow">Research readiness</p>
          <h2>NBA validation gate</h2>
          <strong className="operation-value">
            {researchReadiness
              ? `${researchReadiness.assessment.usable_sample_count}/${researchReadiness.assessment.evaluation_min_usable_samples}`
              : "—"}
          </strong>
          <small>
            {researchReadiness
              ? `${researchReadiness.assessment.readiness_status} · decision coverage ${researchReadiness.assessment.decision_odds_coverage_rate === null ? "—" : pct(researchReadiness.assessment.decision_odds_coverage_rate)} · closing coverage ${researchReadiness.assessment.closing_odds_coverage_rate === null ? "—" : pct(researchReadiness.assessment.closing_odds_coverage_rate)}`
              : "Readiness unavailable"}
          </small>
        </article>
        <article className="metric-card operation-card">
          <p className="eyebrow">Operations</p>
          <h2>Pipeline health</h2>
          <strong className="operation-value">
            {operationalStatus?.severity ?? "—"}
          </strong>
          <small>
            {operationalStatus
              ? `${operationalStatus.alerts.length} alerts · odds Δ ${operationalStatus.odds_snapshot_delta ?? "—"} · results Δ ${operationalStatus.completed_result_delta ?? "—"} · samples Δ ${operationalStatus.usable_sample_delta ?? "—"}`
              : "Operational monitor unavailable"}
          </small>
        </article>
        <article className="metric-card operation-card">
          <p className="eyebrow">Paper only</p>
          <h2>Portfolio</h2>
          <strong className="operation-value">
            {paperPortfolio ? `${paperPortfolio.open_count} open` : "—"}
          </strong>
          <small>
            {paperPortfolio
              ? `${paperPortfolio.settled_count} settled · PnL ${paperPortfolio.realized_pnl.toFixed(2)}`
              : "No paper portfolio state"}
          </small>
        </article>
      </section>

      <section className="panel">
        <form className="controls" onSubmit={runAnalysis}>
          <label>
            Event ID
            <input value={eventId} onChange={(e) => setEventId(e.target.value)} />
          </label>
          <label>
            Decision as-of
            <input value={asOf} onChange={(e) => setAsOf(e.target.value)} />
          </label>
          <label>
            HOME model probability
            <input
              type="number"
              min="0.01"
              max="0.99"
              step="0.01"
              value={homeProbability}
              onChange={(e) => setHomeProbability(Number(e.target.value))}
            />
          </label>
          <label>
            AWAY model probability
            <input
              type="number"
              min="0.01"
              max="0.99"
              step="0.01"
              value={awayProbability}
              onChange={(e) => setAwayProbability(Number(e.target.value))}
            />
          </label>
          <button disabled={busy} type="submit">
            {busy ? "分析中…" : "執行分析"}
          </button>
        </form>
        <p className="notice">
          Synthetic model 尚未通過 validation gate；正 EV 也應維持 NO_VALIDATED_EDGE。
        </p>
        {error ? <p className="error">{error}</p> : null}
      </section>

      {analysis ? (
        <>
          <section className="grid">
            {analysis.records.map((record) => (
              <article className="metric-card" key={record.market_id}>
                <div className="card-heading">
                  <h2>{record.selection}</h2>
                  <span className={`badge ${record.recommendation.toLowerCase()}`}>
                    {record.recommendation}
                  </span>
                </div>
                <dl>
                  <div><dt>Listed odds</dt><dd>{record.decimal_odds.toFixed(2)}</dd></div>
                  <div><dt>Market fair</dt><dd>{pct(record.market_probability_fair)}</dd></div>
                  <div><dt>Model</dt><dd>{pct(record.model_probability)}</dd></div>
                  <div><dt>Edge</dt><dd>{signed(record.edge)}</dd></div>
                  <div><dt>Net EV</dt><dd>{signed(record.net_ev)}</dd></div>
                  <div><dt>Fair odds</dt><dd>{record.model_fair_odds.toFixed(2)}</dd></div>
                </dl>
              </article>
            ))}
          </section>
          <section className="panel chart-panel">
            <h2>Market vs model probability</h2>
            <Suspense fallback={<div className="chart chart-loading">載入圖表…</div>}>
              <ProbabilityChart records={analysis.records} />
            </Suspense>
          </section>
        </>
      ) : null}

      {baseline ? (
        <section className="panel provenance">
          <h2>Point-in-time provenance</h2>
          <p>Decision as-of: {baseline.as_of}</p>
          <p>
            Max input observed:{" "}
            {baseline.records.length
              ? baseline.records[0].max_input_observed_at
              : "no visible odds"}
          </p>
        </section>
      ) : null}
    </main>
  );
}
