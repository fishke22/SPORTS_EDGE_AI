export type SystemHealth = {
  status: string;
  database_ready: boolean;
  schema_version: string | null;
};

export type BaselineRecord = {
  event_id: string;
  market_id: string;
  selection: string;
  decimal_odds: number;
  market_probability_fair: number;
  fair_odds: number;
  gross_ev_baseline: number;
  decision_as_of: string;
  max_input_observed_at: string;
};

export type AnalysisRecord = {
  event_id: string;
  market_id: string;
  selection: string;
  decimal_odds: number;
  market_probability_fair: number;
  model_probability: number;
  model_fair_odds: number;
  edge: number;
  gross_ev: number;
  net_ev: number;
  uncertainty: number;
  data_quality: string;
  recommendation: string;
  risk_blockers: string[];
  is_model_validated: boolean;
};

export type MarketBaselineResponse = {
  event_id: string;
  as_of: string;
  records: BaselineRecord[];
};

export type MarketAnalysisResponse = {
  event_id: string;
  as_of: string;
  records: AnalysisRecord[];
};

async function requestJson<T>(input: RequestInfo | URL, init?: RequestInit): Promise<T> {
  const response = await fetch(input, init);
  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as { detail?: string } | null;
    throw new Error(body?.detail ?? `HTTP ${response.status}`);
  }
  return (await response.json()) as T;
}

export function fetchHealth(): Promise<SystemHealth> {
  return requestJson<SystemHealth>("/api/v1/health");
}

export function fetchMarketBaseline(
  eventId: string,
  asOf: string,
): Promise<MarketBaselineResponse> {
  const query = new URLSearchParams({ as_of: asOf });
  return requestJson<MarketBaselineResponse>(
    `/api/v1/events/${encodeURIComponent(eventId)}/market-baseline?${query.toString()}`,
  );
}

export function fetchMarketAnalysis(
  eventId: string,
  asOf: string,
  homeProbability: number,
  awayProbability: number,
): Promise<MarketAnalysisResponse> {
  return requestJson<MarketAnalysisResponse>(
    `/api/v1/events/${encodeURIComponent(eventId)}/analysis`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        as_of: asOf,
        model_probabilities: {
          HOME: homeProbability,
          AWAY: awayProbability,
        },
        payout_cost_rule_version: "synthetic-zero-cost-v1",
        uncertainty: 0.1,
        data_quality: "GREEN",
        is_model_validated: false,
        data_conflict: false,
      }),
    },
  );
}


export type ProviderUsageSnapshot = {
  provider_id: string;
  observed_at: string;
  requests_remaining: number;
  requests_used: number;
  requests_last: number;
  local_monthly_budget: number;
  endpoint_kind: string;
};

export type ProviderUsageResponse = {
  found: boolean;
  usage: ProviderUsageSnapshot | null;
};

export type MappingSummary = {
  provider_id: string;
  entity_kind: string;
  proposal_count: number;
  pending_count: number;
  approved_count: number;
  rejected_count: number;
  approved_mapping_count: number;
  review_completion_rate: number;
};

export type ForwardCollectionRun = {
  status: string;
  started_at: string;
  finished_at: string;
  credits_spent: number | null;
  events_count: number;
  odds_count: number;
  results_count: number;
  unresolved_count: number;
};

export type ForwardCollectionStatus = {
  provider_id: string;
  checked_at: string;
  current_min_interval_minutes: number;
  scores_min_interval_minutes: number;
  current_due: boolean;
  scores_due: boolean;
  last_current_at: string | null;
  last_scores_at: string | null;
  latest_run: ForwardCollectionRun | null;
  requests_used: number | null;
  requests_remaining: number | null;
  live_event_count: number;
  odds_snapshot_count: number;
  completed_result_count: number;
  past_event_without_result_count: number;
  next_event_start: string | null;
};

export type ResearchReadinessAssessment = {
  readiness_status: string;
  usable_sample_count: number;
  evaluation_min_usable_samples: number;
  validation_min_evaluation_samples: number;
  validation_min_usable_samples: number;
  remaining_to_evaluation: number;
  remaining_to_validation_samples: number;
  decision_odds_coverage_rate: number | null;
  closing_odds_coverage_rate: number | null;
  fold_count_capacity: number;
  ready_for_evaluation: boolean;
  validation_sample_ready: boolean;
  blockers: string[];
};

export type ResearchCycleRun = {
  status: string;
  evaluation_sample_count: number | null;
  validation_passed: boolean | null;
  report_relative_path: string | null;
  model_promotion_performed: boolean;
};

export type ResearchReadinessStatus = {
  assessment: ResearchReadinessAssessment;
  latest_run: ResearchCycleRun | null;
};

export type OperationalStatus = {
  severity: string;
  checked_at: string;
  collection_run_status: string | null;
  collection_age_minutes: number | null;
  research_run_status: string | null;
  research_age_minutes: number | null;
  requests_used: number | null;
  requests_remaining: number | null;
  local_monthly_budget: number | null;
  budget_usage_ratio: number | null;
  odds_snapshot_delta: number | null;
  completed_result_delta: number | null;
  usable_sample_delta: number | null;
  alerts: string[];
};

export type PaperPortfolio = {
  open_count: number;
  settled_count: number;
  void_count: number;
  total_stake: number;
  realized_pnl: number;
  trades: unknown[];
  settlements: unknown[];
};

export function fetchProviderUsage(
  providerId: string,
): Promise<ProviderUsageResponse> {
  return requestJson<ProviderUsageResponse>(
    `/api/v1/providers/${encodeURIComponent(providerId)}/usage`,
  );
}

export function fetchMappingSummary(
  providerId: string,
  entityKind: string,
): Promise<MappingSummary> {
  return requestJson<MappingSummary>(
    `/api/v1/providers/${encodeURIComponent(providerId)}/mapping-summary/${encodeURIComponent(entityKind)}`,
  );
}

export function fetchForwardCollectionStatus(
  providerId: string,
): Promise<ForwardCollectionStatus> {
  return requestJson<ForwardCollectionStatus>(
    `/api/v1/providers/${encodeURIComponent(providerId)}/collection-status`,
  );
}

export function fetchResearchReadiness(): Promise<ResearchReadinessStatus> {
  return requestJson<ResearchReadinessStatus>("/api/v1/research/nba/readiness");
}

export function fetchOperationalStatus(): Promise<OperationalStatus> {
  return requestJson<OperationalStatus>("/api/v1/operations/status");
}

export function fetchPaperPortfolio(): Promise<PaperPortfolio> {
  return requestJson<PaperPortfolio>("/api/v1/paper/portfolio");
}
