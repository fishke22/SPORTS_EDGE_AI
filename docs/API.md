# FastAPI REST API

更新日期：2026-09-28

FastAPI 提供 portable read/research API。Adapter 不重新計算 pricing、de-vig、EV、model 或 risk；
所有分析與狀態查詢皆呼叫共用 application/infrastructure services。

~~~powershell
uv run sports-edge-api
~~~

預設綁定 127.0.0.1:8000。若 frontend/dist 已存在，同一 app 會在 API routes 後掛載靜態 Web UI。

## V1 read/research endpoints

- GET /api/v1/health：schema/database health；未初始化時不建立 DuckDB。
- GET /api/v1/events/{event_id}/odds?as_of=...：point-in-time odds。
- GET /api/v1/events/{event_id}/market-baseline?as_of=...：de-vig market baseline；不寫 Gold。
- POST /api/v1/events/{event_id}/analysis：model probabilities 交給共用 Market Analysis Service。
- GET /api/v1/models/{model_id}/{model_version}：model registry read。
- GET /api/v1/backtests/{backtest_id}：backtest summary read。
- GET /api/v1/entities?entity_kind=TEAM&sport=NBA&entity_id_prefix=NBA_：manual mapping candidate read。
- GET /api/v1/providers/{provider_id}/entity-proposals：mapping proposal read。
- GET /api/v1/providers/{provider_id}/mapping-summary/{entity_kind}：mapping review summary。
- GET /api/v1/providers/{provider_id}/usage：latest provider usage/quota snapshot。
- GET /api/v1/providers/{provider_id}/collection-status：forward collection freshness、latest run、quota 與 result coverage。
- GET /api/v1/research/nba/readiness：latest NBA research readiness snapshot；優先讀 persisted hourly-cycle evidence，沒有 snapshot 才 fallback live 計算。
- GET /api/v1/operations/status：latest persisted operational health snapshot，含 heartbeat、quota、coverage/readiness drift 與 alerts。
- GET /api/v1/events/{event_id}/result：latest canonical provider-provenanced result。
- GET /api/v1/paper/portfolio：paper positions + settlements summary。

Analysis request 的 is_model_validated 是顯式 gate；沒有通過 validation 時，即使 Net EV 為正，
介面層也不能自行改成 EDGE。互斥 selection probabilities 必須與市場 selections 完全一致且總和為 1。

## Mutation boundary

API 不提供 provider ingestion、forward collection execution、operational monitor write、scheduler mutation、research evaluation execution、mapping approve/reject、migration、backup restore、paper-open、paper-settle 或自動下注。這些 mutation 維持 standalone CLI/scheduler workflow。

Domain ValueError 映射 HTTP 400；缺少本機資源為 HTTP 404；model/backtest missing 為 HTTP 404。
