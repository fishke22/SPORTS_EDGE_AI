# Operations Runbook

更新日期：2026-09-28

本文件描述 portable standalone profile 的可執行流程。所有路徑由 PROJECT_ROOT resolver 決定；
不得假設專案位於固定磁碟或使用者目錄。

## 1. Bootstrap / health

~~~powershell
.\scripts\bootstrap.ps1
uv run sports-edge health
uv run sports-edge init-db
~~~

Bootstrap 會同步 Python dependencies、migration、Ruff、mypy、pytest、frontend npm ci、
Vitest 與 production build。任何一步失敗都視為施工/發布 gate 未通過。

## 2. The Odds API credential

Credential 不接受 CLI argument。建議使用隱藏輸入命令寫入 resolved PROJECT_ROOT 的本機 .env：

~~~powershell
uv run sports-edge configure-odds-api-key
~~~

也可使用 process environment SPORTS_EDGE_THE_ODDS_API_KEY；process environment 優先於 PROJECT_ROOT/.env。
Settings 永遠從 resolved PROJECT_ROOT/.env 載入，不從其他工作目錄的 .env 借用 secret，避免多個 portable copy 互相污染。
.env 不得提交 Git；.env.example 只提供空值與 non-secret defaults。

Local quota guard：

- SPORTS_EDGE_THE_ODDS_API_MONTHLY_CREDIT_BUDGET：預設 450。
- SPORTS_EDGE_THE_ODDS_API_REGION：預設 us。
- Provider header usage 會寫入 provider_usage_snapshots。
- 超出 local monthly budget 時 client fail closed。

## 3. Entity mapping review

先取得 NBA participants 並建立 proposal：

~~~powershell
uv run sports-edge odds-api-propose-nba-mappings
uv run sports-edge entity-proposals
~~~

Proposal 不會自動寫成正式 mapping。人工審核：

~~~powershell
uv run sports-edge approve-entity-mapping "Boston Celtics" NBA_BOS --review-note "official NBA team"
uv run sports-edge reject-entity-mapping "Ambiguous Name" "manual review rejected"
~~~

Mapping candidate 可由 read-only API/MCP 查詢；approve/reject mutation 不暴露給 MCP。

## 4. Free-plan current odds / scores ingestion

Mapping 完整後可執行 current NBA h2h：

~~~powershell
uv run sports-edge ingest-the-odds-api-current
~~~

取得近期 results：

~~~powershell
uv run sports-edge ingest-the-odds-api-scores --days-from 3
~~~

Raw response 先進 immutable Bronze，public export 固定 false。Team mapping 不完整時，
current odds canonicalization fail closed；scores 若 provider event 尚無 canonical event mapping，
會保存 provider result provenance並回報 unresolved event。

## 5. Historical connector

若帳號具合法 historical entitlement：

~~~powershell
uv run sports-edge ingest-the-odds-api-historical 2026-09-20T12:00:00Z
~~~

Historical envelope / bookmaker timestamps 晚於 requested time 時 hard fail。未配置 credential
或 entitlement 時不得以 scraping 繞過 provider 官方存取方式。

## 6. Local NBA research dataset

Local dataset 由 canonical events + completed results + point-in-time odds 建立：

~~~powershell
uv run sports-edge local-nba-research
~~~

Elo/rest features 只使用 decision time 前已觀測到 completed result 的 NBA games。取消、
未完成或當時尚未知結果的賽事不計入 rating/rest history。Decision-time odds 與 closing odds
分離保存；closing odds 只供 CLV/事後評估。

資料不足時正確狀態是 INSUFFICIENT_DATA。通過 walk-forward evaluator 仍必須通過 validation
policy；沒有真實 OOS/calibration evidence 時不得宣稱模型已 validated。

## 7. Prediction

Prediction 必須使用 model registry 中已存在且 checksum 可驗證的 model artifact：

~~~powershell
uv run sports-edge predict-nba <EVENT_ID> <AS_OF> <MODEL_ID> <MODEL_VERSION>
~~~

每筆 prediction 保存 bookmaker/source/odds_snapshot_id provenance。Recommendation 仍由共用
Market Analysis Service + Risk Gate 決定；model registry 未標記 VALIDATED 時正 EV 仍是
NO_VALIDATED_EDGE。

## 8. Paper-only workflow

系統不實作自動下注。Paper trade 開立要求：

- prediction recommendation = EDGE
- Data Quality = GREEN
- Net EV > 0
- model registry status = VALIDATED
- odds snapshot 在 prediction as-of 時已可見
- live odds 不允許自動開 paper trade

~~~powershell
uv run sports-edge paper-open <PREDICTION_ID> --stake 1
uv run sports-edge paper-ready-events
uv run sports-edge paper-settle <EVENT_ID> <SETTLED_AT>
~~~

Settlement 目前只支援 full-game moneyline paper-moneyline-v1。未知 settlement rule version
fail closed；tie 依目前 paper research rule void，不代表任何實際運彩派彩規則。

## 9. API / Web / MCP

~~~powershell
uv run sports-edge-api
uv run sports-edge-mcp
npm --prefix frontend run dev
~~~

Web UI 顯示 provider quota、mapping review、paper portfolio、market baseline 與 analysis；
不提供 mapping mutation、paper-open、settlement 或自動下注按鈕。

MCP 全部 read-only。任何 ingestion、mapping approval、backup restore、paper trade mutation 均不在 MCP。

## 10. Backup / restore

建立 portable research backup：

~~~powershell
uv run sports-edge backup-state
~~~

Backup v1 只包含 state、models、reports、config；不包含 Bronze/Silver/Gold、logs、.env、
provider raw payload。Restore 會驗 manifest、relative path 與 SHA-256，且必須顯式 --force：

~~~powershell
uv run sports-edge restore-state backups\<file>.zip --force
~~~

Restore 是可覆寫操作；執行前應先保留目前 state backup。

## 11. Publication audit

第一次 public push 前：

~~~powershell
uv run python scripts\publication_audit.py --write-report
npm --prefix frontend audit
git diff --check
~~~

Publication audit 會檢查 tracked runtime/raw/database/model/report/backup、大檔、credential-like
pattern、機器絕對路徑、必要治理文件及 dependency license metadata。Dependency metadata
unknown/copyleft 以 warning 交人工複核；secret/raw/runtime tracking 為 blocker。

即使 audit 全綠，第一次真正 public push 仍必須先由使用者確認 repository name、visibility、
tracked files、license 與 audit 結果。


## 12. System doctor

Doctor 是 offline/read-only 自我診斷，不會呼叫 provider：

~~~powershell
uv run sports-edge doctor
~~~

它檢查 root marker、Python/Node lockfiles、DuckDB schema 是否等於最新 migration、frontend build、
credential 是否配置，以及 provider production gate。沒有 credential 或 provider 仍 research-only 時回
DEGRADED 但可保持 ready_for_research=true；schema/lockfile 缺失才視為 FAIL。

## 13. Deterministic release bundle / CI

建立 release bundle 前必須先完成 frontend production build 與 publication audit：

~~~powershell
npm --prefix frontend run build
uv run sports-edge build-release
~~~

Bundle 寫入 backups/releases/，使用固定 ZIP metadata、sorted paths 與 release-manifest.json。
只包含 Git tracked source/governance files與 frontend/dist built assets，不包含 runtime state、
provider raw data、.env、models/reports/backups。Output path 必須留在 PROJECT_ROOT 內。

GitHub Actions quality gate 位於 .github/workflows/ci.yml：Windows + Ubuntu、Python 3.11 + 3.14，
frontend test/build/audit、publication audit 與 release bundle smoke。所有外部 Actions 都必須 pin
到 40-character immutable commit SHA；publication audit 會阻擋 tag/branch pin。

## 14. Forward point-in-time collection

先看 freshness、quota 與 result coverage：

~~~powershell
uv run sports-edge collection-status
~~~

執行 one-shot collector：

~~~powershell
uv run sports-edge collect-forward --trigger-kind MANUAL
~~~

預設 cadence 由 PROJECT_ROOT settings 控制：

- SPORTS_EDGE_FORWARD_CURRENT_MIN_INTERVAL_MINUTES=180
- SPORTS_EDGE_FORWARD_SCORES_MIN_INTERVAL_MINUTES=720
- SPORTS_EDGE_FORWARD_SCORES_DAYS_FROM=3
- current odds 每次成功 response 的典型成本為 1 credit（1 region × 1 market）。
- scores 帶 daysFrom 時典型成本為 2 credits；除 cadence 外，只有存在已開賽但缺 completed result 的 canonical event 才會 due。
- 若兩個 endpoint 都不 due，run ledger 記 SKIPPED 且 credits_spent=0。
- local monthly budget 450 仍是 hard gate；provider response headers 是實際 quota source。

Windows 可每 60 分鐘喚醒 collector，但喚醒不等於呼叫 API：

~~~powershell
.\scripts\register_forward_collection_task.ps1 -WakeIntervalMinutes 60 -WhatIf
.\scripts\register_forward_collection_task.ps1 -WakeIntervalMinutes 60
~~~

Task 使用 10 年 repetition duration、IgnoreNew、StartWhenAvailable 與 10 分鐘 execution limit。取消：

預設註冊使用目前 Windows 使用者的 Interactive-only token，不儲存 Windows 密碼；因此使用者登出時 task 不執行。這是刻意的安全取捨，因為 S4U 類型不適合需要網路存取 provider 的 collector。重新登入後 StartWhenAvailable 可補啟動。

~~~powershell
.\scripts\unregister_forward_collection_task.ps1
~~~

實際 runner 是 scripts/collect_forward.ps1；它自動解析 PROJECT_ROOT，輸出寫入 ignored logs/forward_collection.log。任何 provider error 都必須經過 sanitized exception path，run ledger 另對目前 API key 做 [REDACTED] 替換。

API / MCP / Web 只讀 collection status，不提供啟動 collector 或 scheduler mutation。

## 15. Research readiness / automatic evaluation

即時檢查 readiness：

~~~powershell
uv run sports-edge research-readiness
uv run sports-edge research-cycle --trigger-kind MANUAL
~~~

nba-readiness-v1 直接引用既有 6 小時 decision horizon、160 train、20 test、20 calibration。
180 usable samples 才能形成第一個完整 walk-forward fold；360 usable samples只代表具備 200 個
OOS test samples 的容量，仍須通過完整 validation metrics gate。research-cycle 只寫 readiness ledger
與 deterministic research report，不寫 model_registry，也不自動 promotion。

## 16. Operational monitoring

讀取最新 persisted snapshot：

~~~powershell
uv run sports-edge ops-status
uv run sports-edge ops-monitor --trigger-kind MANUAL
~~~

operational-monitor-v1 預設 policy：collection/research heartbeat 超過 150 分鐘為 WARN；local monthly
credit budget 使用率達 80% 為 WARN、達 100% 或 provider remaining=0 為 FAIL。另監看 collection/research
FAILED/PARTIAL、scores result gap、decision/closing odds coverage、research preflight blockers，以及
odds/results/usable-sample counters 是否倒退。

NOT_READY 本身不是 operational failure；資料量不足時不應製造警報。scheduler runner 順序為
collection -> research-cycle -> ops-monitor，monitor 一定在最後執行。FastAPI/MCP/Web 只讀最新 snapshot；
monitor 不會自動修復、不會自動 promotion，也不會執行任何投注。
