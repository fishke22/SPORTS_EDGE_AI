import { afterEach, describe, expect, it, vi } from "vitest";

import {
  fetchForwardCollectionStatus,
  fetchMappingSummary,
  fetchOperationalStatus,
  fetchMarketAnalysis,
  fetchPaperPortfolio,
  fetchProviderUsage,
  fetchResearchReadiness,
} from "./api";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("API client", () => {
  it("sends model probabilities to the shared analysis endpoint", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          event_id: "SYNTH_NBA_001",
          as_of: "2026-10-01T08:30:00Z",
          records: [],
        }),
        {
          status: 200,
          headers: { "Content-Type": "application/json" },
        },
      ),
    );
    vi.stubGlobal("fetch", fetchMock);

    await fetchMarketAnalysis(
      "SYNTH_NBA_001",
      "2026-10-01T08:30:00Z",
      0.6,
      0.4,
    );

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/api/v1/events/SYNTH_NBA_001/analysis");
    expect(init.method).toBe("POST");
    expect(JSON.parse(String(init.body))).toMatchObject({
      model_probabilities: { HOME: 0.6, AWAY: 0.4 },
      is_model_validated: false,
      data_conflict: false,
    });
  });

  it("reads provider, mapping, and paper operational endpoints", async () => {
    const fetchMock = vi.fn().mockImplementation(async () =>
      new Response("{}", {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await fetchProviderUsage("provider_the_odds_api");
    await fetchMappingSummary("provider_the_odds_api", "TEAM");
    await fetchForwardCollectionStatus("provider_the_odds_api");
    await fetchResearchReadiness();
    await fetchOperationalStatus();
    await fetchPaperPortfolio();

    expect(fetchMock.mock.calls.map((call) => call[0])).toEqual([
      "/api/v1/providers/provider_the_odds_api/usage",
      "/api/v1/providers/provider_the_odds_api/mapping-summary/TEAM",
      "/api/v1/providers/provider_the_odds_api/collection-status",
      "/api/v1/research/nba/readiness",
      "/api/v1/operations/status",
      "/api/v1/paper/portfolio",
    ]);
  });
});
