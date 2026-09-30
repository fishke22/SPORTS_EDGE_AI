# SPORTS_EDGE_AI

SPORTS_EDGE_AI 是一套 portable-first 的運動市場量化研究平台。核心目標是把 point-in-time 資料、
市場去水後機率、模型校準後機率、公平賠率、Edge、Gross/Net EV、不確定性、資料品質與風控放在
同一個可重現流程中，而不是產生「必中」或「保證獲利」的投注宣稱。

## 目前階段

**核心 portable vertical slice 已完成到 research/paper-only operational level；真實 provider 與模型 production gate 仍維持 fail-closed。**目前已具備 synthetic + The Odds API free live connector、人工 entity mapping review、immutable Bronze / canonical Silver / Gold baseline、forward point-in-time collector/run ledger、research readiness/automatic evaluation cycle、operational monitoring snapshot、local NBA feature/training dataset、walk-forward/calibration/validation gate、prediction provenance、paper-only settlement、FastAPI/Web/MCP read interfaces、portable backup/restore、system doctor、deterministic release bundle、cross-platform CI 與 publication audit。Free endpoints 已完成 live validation；historical paid entitlement probe 為 HTTP 401，因此 `production_allowed=false`。沒有真實 OOS/calibration 證據前，模型不得宣稱 validated edge。

## 只給 Repository URL 的 AI / Cloud Smoke

只要 AI 本身具備可執行程式的環境（Git、Python 3.11+、uv 與 GitHub 網路存取），公開 repo 可直接 clone 後跑不含 credential、完全離線的 shared-domain smoke：

~~~bash
git clone https://github.com/fishke22/SPORTS_EDGE_AI.git
cd SPORTS_EDGE_AI
uv sync --frozen
uv run sports-edge repo-smoke
~~~

這個 smoke 使用隔離暫存 PROJECT_ROOT、tracked synthetic fixtures 與正式 Market Analysis Service，驗證 migration、as-of future-leakage gate 與 NO_VALIDATED_EDGE fail-closed 行為；不會讀寫 clone 本身的 operational state。**Repo URL 本身不包含真實 point-in-time history、API key 或 validated model evidence**，因此真實 live/continuous analysis 仍需要遠端 persistent runtime + durable storage + secret injection。詳見 docs/CLOUD_RUNTIME.md。

## 永不付費 Runtime Policy

本專案目前採 hard fail-closed 的 zero-cost policy：`paid_services_allowed=false`、`automatic_billing_allowed=false`。沒有經驗證的**免費、私有、durable** state backend 時，`remote_live_collection_ready` 固定為 false；不得自動升級付費、不得把 public Git 或 GitHub Actions artifact 當 operational database，也不得為了免費額度刪除 point-in-time evidence。

~~~powershell
uv run sports-edge zero-cost-status
uv run sports-edge build-operational-checkpoint
uv run sports-edge verify-operational-checkpoint backups\operational-checkpoints\<file>.zip
~~~

Operational checkpoint 是未來跨機器/免費 backend 的 state-transfer contract：包含 `data/bronze`、`data/silver`、`data/gold`、`state`、`models`、`reports`，但**不包含 `.env`/API key**；archive manifest 固定 `public_export_allowed=false`。Restore 只允許空 runtime，避免 silent overwrite。真正「個人電腦關機仍持續 live collection」仍需另外找到符合 zero-cost policy 的 private durable backend；找不到時系統維持 blocked，不做品質較差的替代方案。詳見 `docs/CLOUD_RUNTIME.md`。

## Portable-first

程式不得依賴目前磁碟位置。根目錄解析順序：`SPORTS_EDGE_ROOT` → `.sports-edge-root` / repository
marker 向上搜尋 → package 位置向上搜尋。資料、state、models、reports、logs、backups 皆以解析出的
PROJECT_ROOT 為基準。

```powershell
.\scripts\bootstrap.ps1
uv run sports-edge health
uv run sports-edge repo-smoke
uv run sports-edge zero-cost-status
uv run sports-edge init-db
uv run sports-edge doctor
uv run sports-edge collection-status
uv run sports-edge collect-forward
uv run sports-edge research-readiness
uv run sports-edge research-cycle --trigger-kind MANUAL
uv run sports-edge ops-status
uv run sports-edge ops-monitor --trigger-kind MANUAL
uv run sports-edge-api
# 另一個終端可執行 read-only MCP stdio server：
uv run sports-edge-mcp
# Frontend dev server（API 需在 127.0.0.1:8000）：
npm --prefix frontend run dev
```

完整工程契約請先閱讀 `SPORTS_EDGE_AI_PROJECT_SOURCES/SPORTS_EDGE_AI_PROJECT_SOURCES.md`；日常 ingestion、mapping review、research、prediction、paper settlement、backup/restore 與 publication gate 請依 `docs/OPERATIONS.md` 執行。
