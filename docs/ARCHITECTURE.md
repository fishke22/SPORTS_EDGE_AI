# Architecture

SPORTS_EDGE_AI 採 single-core / multi-interface：`domain` 定義契約，`application` 實作 pricing、risk、
backtest/model services，`infrastructure` 負責 DuckDB/Parquet 與 provider I/O，CLI/API/MCP/Web 僅是 adapter。

Portable profile 以 Python + uv + DuckDB + Parquet + Polars 為必要基礎。PostgreSQL、TimescaleDB、Prefect、
MLflow 與容器化屬 optional server profile，不得成為 standalone 啟動前置條件。

資料層固定 `bronze -> silver -> gold`。Bronze 優先 immutable；Silver 是 canonical normalized data；Gold
只存 feature/model-ready/prediction/backtest 產物。任何決策資料必須攜帶 as-of/provenance。

Phase 3 的 sport-model 路徑維持同一 application layer：NBA feature contract → interpretable logistic baseline → walk-forward evaluator；single-event model probability 透過 `analyze_nba_market` 交給既有 Market Analysis Service，再統一處理 fair odds / edge / gross/net EV / data quality / risk。Model code 不直接產生最終推薦。

Walk-forward evaluator 與 live/single-event analysis 分離：前者允許使用 closing odds 與 settled result 做事後評估，但 training eligibility 必須以 `result_observed_at` 控制；後者只能使用 `decision_as_of` 可見資料。後續 calibration、artifact registry、API/MCP/Web 都應依此邊界擴充。

Phase 3B 新增 calibration / artifact / registry lifecycle。Model 與 calibrator 仍屬 application/domain 研究核心；artifact bytes 與 DuckDB persistence 屬 infrastructure。完整 backtest report 保存為 portable JSON，避免為了新增 metrics 回改既有 migration。

Validation gate 與 Market Analysis recommendation 分離：前者驗證 model/version，後者才針對單一 market odds 產生 `NO_BET / WATCH / EDGE / NO_VALIDATED_EDGE`。API/MCP/Web 之後都必須維持這個邊界。

Phase 4 完成 interface vertical slice。`application/interface_service.py` 是 FastAPI/MCP 的共用 read/query facade；REST 與 MCP 只處理 transport/schema/error mapping，Web 只消費 REST JSON。Adapter 層不得重新實作 pricing/model/risk。

Read-only interface path 使用 DuckDB read-only connections。FastAPI 可在 `frontend/dist` 存在時同源掛載 built React UI；development Vite 以 `/api` proxy 指向本機 FastAPI。MCP 使用官方 Python SDK v2 `MCPServer`，目前只暴露 structured read-only tools。
