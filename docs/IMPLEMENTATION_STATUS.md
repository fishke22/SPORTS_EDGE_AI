# Implementation Status

更新日期：2026-09-29

## 總體狀態

SPORTS_EDGE_AI 第一個 NBA pregame moneyline portable vertical slice 已完成到
research / paper-only operational level。CLI、FastAPI、Web UI、MCP 共用同一套 domain/application
services；沒有自動下注功能。

真實 provider free operational path 已完成 live validation；historical paid entitlement probe 回 HTTP 401，
且仍沒有足夠真實 point-in-time completed-result OOS/calibration evidence，因此
provider production_allowed=false，模型不得宣稱 validated edge。

## 最終驗證

- pytest：103 passed。
- Phase 10 persisted-readiness regression：snapshot 存在時 shared API/MCP/Web read facade 不重建 training dataset；無 snapshot 時 fallback live assessment；snapshot sample/status/remaining/blockers 與 ledger 一致。
- Ruff：all checks passed。
- mypy strict：60 source files，0 issues。
- frontend Vitest：2 passed。
- TypeScript / Vite production build：passed。
- npm audit：0 vulnerabilities。
- scripts/bootstrap.ps1：passed；DuckDB current_version=0009。
- scripts/verify_portability.ps1：passed。
- Phase 10 live smoke：research-readiness=NOT_READY，0 usable / 180 first evaluation / 360 validation sample capacity；model_registry/backtest_runs 維持 0。
- API/MCP contract tests確認 read-only structured interface。
- publication audit（Phase 11 staged tree）：0 blockers / 0 warnings，ready_for_user_review=true；163 tracked files。
- `sports-edge doctor`：DEGRADED / ready_for_research=true；credential 已配置，僅 provider production gate 為 WARN。
- deterministic release bundle：builder / manifest / hash / raw-exclusion smoke 已通過；runtime ZIP 不進 Git，依 staged source 可重建。
- public push：未執行。

## Phase 0 — Portable Foundation

狀態：完成。

已具備 PROJECT_ROOT resolver、uv/pyproject/lockfile、DuckDB migration checksum runner、
Bronze/Silver/Gold/state/models/reports/logs/backups、Pydantic/Pandera contracts、pricing/risk primitives、
README/AGENTS/security/license/publication docs。

## Phase 1 — Canonical Data Vertical Slice

狀態：完成。

Synthetic raw → content-addressed immutable Bronze → canonical normalization → Silver Parquet →
Pandera → DuckDB → as-of query。Migration 0003 建立 provider/license/entity mapping contract；
Gold market baseline 保存 decision_as_of / max_input_observed_at point-in-time evidence。

## Phase 2 — Market Analysis / Net EV / Risk

狀態：完成。

共用 Market Analysis Service 統一 de-vig、fair odds、edge、Gross/Net EV、版本化 payout/cost rule、
uncertainty、Data Quality 與 Risk Gate。NO_BET / WATCH / EDGE / NO_VALIDATED_EDGE /
DATA_CONFLICT 皆有測試。未 validated model 的正 EV 仍為 NO_VALIDATED_EDGE。

## Phase 3 — NBA Baseline / Walk-Forward / Calibration

狀態：研究工程完成；model production validation 未解除。

已有可解釋 NBA logistic baseline、rating/rest/home-court feature contract、time-separated Platt calibration、
expanding walk-forward、model-vs-market Brier/LogLoss/ECE、ROI/Yield/CLV/Max Drawdown、
bootstrap CI、risk of ruin、artifact checksum、registry/backtest/report 與 validation policy。

Synthetic evidence 永遠 fail closed；HISTORICAL_POINT_IN_TIME 仍需真實可重現資料量與 gate evidence。

## Phase 4 — CLI / API / Web / MCP

狀態：完成。

- CLI：health/init-db、synthetic/provider ingestion、mapping review、as-of/baseline/analysis、local NBA research、research readiness/cycle、operational monitor/status、prediction、paper workflow、provider usage、forward collect/status、backup/restore、doctor、build-release。
- FastAPI：health、odds、baseline、analysis、model/backtest、entity mapping reads、provider usage、forward collection status、NBA research readiness、operational status、event result、paper portfolio。
- MCP：15 個 read-only/idempotent structured-output tools；無 ingestion/mutation/betting/model promotion。
- Web：market analysis + provider quota + mapping review + forward collection freshness + NBA research readiness + operational health + paper portfolio read dashboard；不在 frontend 重算 domain logic。

## Phase 5A — Historical Provider Connector

狀態：connector contract 完成；free endpoints live validated；historical paid entitlement 未通過（HTTP 401）。

The Odds API historical NBA h2h client 已有 secret-only credential、immutable Bronze、
timestamp hard gates、mapping fail-closed、Data Quality、Silver/DuckDB persistence與 synthetic
provider-schema tests。沒有 credential 時不 fallback scraping。

## Phase 5B — Free Provider Operations / Mapping Review

狀態：完成。

Migration 0006 新增 provider usage snapshots、entity proposals、event results、prediction odds provenance
與 paper settlement linkage。Current NBA h2h、participants、scores clients 使用 local monthly credit budget；
人工 mapping proposal/approve/reject workflow 完成，MCP/API 只讀。

正式 NBA mapping candidate 使用 NBA_ prefix 排除 synthetic TEAM。Current odds mapping 不完整時
保留 Bronze/Data Quality evidence但不寫 canonical odds。

2026-09-28 live validation：32 participant proposals 完成 30 approved / 2 rejected / 0 pending；current h2h 取得 41 events / 212 odds、Data Quality GREEN、mapping_rate=1.0；scores 近 3 日目前為 0 results；historical entitlement probe=HTTP 401。

## Phase 6 — Local Real-Data Research Bridge

狀態：完成到 research gate。

Canonical events + completed results + point-in-time odds 可直接重建 local NBA Elo/rest features 與
training samples。Elo/rest 只使用 decision time 前已觀測 completed result；取消/延期/未完成 event
不會污染 rest history。Decision-time odds 與 closing odds 分離，prediction 保存
bookmaker/source/odds_snapshot_id provenance。

local-nba-research 在資料不足時回 INSUFFICIENT_DATA；資料足夠才進 walk-forward + validation gate。

## Phase 7 — Paper Settlement / Operations / Release Safety

狀態：完成。

Paper trade 開立要求 VALIDATED + EDGE + GREEN + positive Net EV + as-of odds provenance；
live odds 不允許自動開立。Settlement rule version 未知時 fail closed；目前僅 full-game moneyline
paper research rule。

Portable backup v1 只備份 state/models/reports/config，不含 raw data；restore 驗 checksum/path 且需 force。
Publication audit 已實作 secret/runtime/raw/large-file/path/governance/dependency-license gate。

## Phase 8 — CI / Self-Diagnostics / Reproducible Release

狀態：完成。

新增跨 Windows/Linux、Python 3.11/3.14 的 GitHub Actions quality gate；frontend 使用 Node 24。
所有 external GitHub Actions 均 pin 到完整 40-character commit SHA，publication audit 會阻擋 floating
tag/branch。CI 同時執行 migration smoke、Ruff、mypy、pytest、Windows portability、frontend
test/build/audit、publication audit 與 release bundle smoke。

`sports-edge doctor` 離線檢查 root/lockfiles、schema、frontend build、credential 與 provider production
gate；外部 credential 尚未配置時可回 DEGRADED 但 ready_for_research=true。Deterministic release bundle
只包含 Git tracked source/governance files 與 frontend production assets，使用固定 ZIP metadata 與
per-file SHA-256 manifest，且不得輸出 PROJECT_ROOT 外或夾帶 runtime/raw state。

## Phase 9 — Forward Point-in-Time Collection

狀態：完成；本機 hourly Windows scheduler 已註冊並驗證。

Migration 0007 新增 forward_collection_runs ledger。One-shot collector 會先依 endpoint freshness、local credit budget 與資料缺口判斷 due；預設 current odds 最短 180 分鐘、scores 最短 720 分鐘。Scores 除 cadence 外，還必須存在 scheduled_start 已過但尚無 completed result 的 canonical event 才會呼叫，因此 off-period 不會固定消耗 scores credits。

每次 run 保存 trigger、開始/完成時間、SUCCESS/DEGRADED/SKIPPED/PARTIAL/FAILED、attempted endpoints、event/odds/result/unresolved counts、Data Quality、mapping rate、credit delta、remaining quota 與已去 secret 的 error summary。實機 non-force smoke 已驗證 fresh 狀態會 SKIPPED、兩個 endpoint 均未 attempted、credits_spent=0、quota 維持 496。

CLI 可執行 collect-forward / collection-status；FastAPI/MCP/Web 只讀 collection status。Portable PowerShell runner 與 Windows Task Scheduler register/unregister helpers 已建立；task 設定 IgnoreNew / StartWhenAvailable / 10 分鐘 execution limit。本機 `SPORTS_EDGE_AI Forward Collection` 以 60 分鐘 wake cadence 註冊，Run As fishk / Interactive-only；runner 現在在 collection 成功或 SKIPPED 後接續執行 research-cycle SCHEDULED。

## Phase 10 — Research Readiness / Automatic Validation Trigger

狀態：完成核心施工與實機 fail-closed smoke；不包含自動 model promotion。

Migration 0008 新增 research_readiness_runs。nba-readiness-v1 直接引用既有 6 小時 decision horizon、160 train、20 test、20 calibration 與 nba-research-gate-v1。180 usable samples 才能形成第一個 160+20 walk-forward fold；validation policy 需要至少 200 OOS samples，因此以 20-sample non-overlap folds 計算，需要 360 usable samples 才具備 sample-count capacity。360 不是 validated 判定，仍必須通過 bet_count、Brier/LogLoss/ECE、Yield、CLV、drawdown、bootstrap CI、risk-of-ruin 與 evidence-tier gates。

Readiness 同時保存 decisive completed events、decision-time odds coverage、closing odds coverage、feature errors、temporal settled-label preflight，以及 base-training / calibration outcome-class preflight。資料不足或 temporal/calibration preflight 不通過時 fail closed 為 NOT_READY。

research-cycle 對完整可用 dataset 與實際被 complete folds 消耗的 sample prefix 分別做 fingerprint。相同 evaluation fingerprint 已評估時回 SKIPPED_UNCHANGED，不重跑昂貴 evaluation。新 evidence 只寫 deterministic reports/backtests/readiness/<sha>.json 與 readiness ledger，不寫 model_registry；即使 research validation gate pass，record 仍固定 model_promotion_performed=false。

實機目前為 0 usable / 180 remaining-to-evaluation / 360 remaining-to-validation-samples。MANUAL 與 SCHEDULED smoke 都只寫 NOT_READY；model_registry=0、backtest_runs=0、readiness report=0。Hourly runner 已串接 collection -> research-cycle -> ops-monitor；目前 live state 44 events / 642 odds / 0 completed results，quota 493 remaining / 7 used。
## Phase 11 — Operational Monitoring

狀態：完成並已接入 hourly scheduler。

Migration 0009 新增 operational_monitor_snapshots。operational-monitor-v1 監看 collection/research heartbeat、provider quota/local budget、past-event result gap、decision/closing odds coverage、research preflight blockers，以及 odds/results/usable-sample counters 的 monotonic drift。NOT_READY 本身不是 operational failure；資料量不足時可維持 OK。

預設 heartbeat stale threshold 為 150 分鐘，local monthly credit budget 使用率 80% 為 WARN、100% 或 provider remaining=0 為 FAIL。collection FAILED/PARTIAL、research FAILED 與 append-only counter regression 會升級 FAIL；DEGRADED、coverage gap、scores due 與 stale heartbeat 為 WARN。

CLI 提供 ops-monitor / ops-status；FastAPI/MCP/Web 只讀 latest persisted operational snapshot。Scheduler runner 現為 collection -> research-cycle -> ops-monitor，monitor 一定在最後嘗試執行且不覆蓋前一階段 failure exit code。實機 SCHEDULED smoke 為 severity=OK / 0 alerts / odds-result-sample delta=0，Task Scheduler Last Result=0，quota 未增加。

## 外部 Gate / 非程式缺口

1. Historical paid entitlement：live probe 已回 HTTP 401；目前帳號不可使用 historical endpoints。
2. Model validation：current odds 已 live validated，但 usable completed-result samples 目前為 0；180 才能首個 research fold、360 才具備 200 OOS sample capacity，之後仍須通過完整 validation metrics gate 才可人工進入 model lifecycle。
3. Live provider mapping：30 個正式 NBA franchise 已 review approved，2 個非正式 provider participants rejected；目前 mapping completion=1.0。
4. Git 首次 commit：repository-local identity 已設定為 `fishke22 <fishke22@gmail.com>`；尚未建立首次 commit。
5. Public GitHub：必須在 audit 後由使用者確認 repo name、visibility、tracked files 與 license。
6. 台灣運彩 adapter / 真實 payout-tax rule：需合法官方資料與版本化規則來源後另行施工；目前不猜值。
