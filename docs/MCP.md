# MCP

更新日期：2026-09-28

SPORTS_EDGE_AI MCP 預設 read-only，只薄封裝共用 application services。Dependency pin 為
mcp>=2,<3；目前 lockfile 使用官方 Python SDK v2 line。

~~~powershell
uv run sports-edge-mcp
~~~

所有 tools 使用 read-only / idempotent / open-world false annotations，並回傳 typed structured JSON。

## Read-only tools

- get_system_health_tool
- get_event_odds_tool
- get_market_baseline_tool
- get_market_analysis_tool
- get_model_tool
- get_backtest_tool
- get_canonical_entities_tool
- get_entity_proposals_tool
- get_mapping_review_summary_tool
- get_provider_usage_tool
- get_forward_collection_status_tool
- get_nba_research_readiness_tool
- get_operational_status_tool
- get_event_result_tool
- get_paper_portfolio_tool

Market baseline tool 使用 persist=false；read repositories 使用 DuckDB read-only connection。

MCP 不提供 ingestion、forward collection execution、operational monitor write、research evaluation execution、scheduler mutation、migration、mapping approval/rejection、artifact write、backup restore、paper trade open/settle、backtest execution或下注 mutation。若未來加入 run_backtest，必須另外設計
resource limits、authorization 與 read/write policy。
