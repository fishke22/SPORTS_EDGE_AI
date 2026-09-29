# Data Contract

Foundation schema 已覆蓋 canonical event、market、odds snapshot、provider/license registry、model registry、
prediction、backtest、paper trade、settlement、risk assessment 與 data quality。

所有時間欄位必須 timezone-aware。Odds snapshot 不覆寫；`observed_at` 是 point-in-time 回測硬限制。
任何 feature/prediction 的輸入都不得出現 `max_input_observed_at > decision_as_of`。

Raw/bronze reference 只保存 PROJECT_ROOT 相對路徑，不保存磁碟代號或使用者絕對路徑。實際 provider
payload、付費資料與 production DuckDB 不進公開 Git。

## Bronze / Ingest Provenance

`raw_objects` 以 `payload_sha256` 去重 raw bytes；`ingest_runs` 記錄 provider、`observed_at`、`ingested_at`、schema version、row count 與 manifest relative path。Bronze object 與 manifest 都是 immutable；重複 ingest 相同觀測應保持冪等。

## Silver / As-Of

Synthetic moneyline normalization 目前輸出 `data/silver/events`、`markets`、`odds` Parquet。Odds dataframe 必須通過 Pandera contract。查詢任何決策時點時同時限制 `observed_at <= decision_as_of`，若 provider timestamp 存在亦要求 `provider_timestamp <= decision_as_of`；再於每個 selection/bookmaker/source 取當時最新一筆。未來 snapshot 不得回填。

## Provider / License / Entity Mapping

Migration `0003` 新增 `canonical_entities` 與 `provider_entity_mapping`，並加入 synthetic provider/license seed。Synthetic mapping confidence 為 1.0 只因 fixture 由專案自行定義；真實 provider 不得照抄此信心值。Provider 與 license metadata 必須能獨立演進，且 production eligibility 與 redistribution 權限不可由程式 license 推導。

## Gold Market Baseline

`data/gold/market_baseline/` 每列保存 event、market group、selection、bookmaker/source、listed decimal odds、raw implied probability、multiplicative de-vig fair probability、fair odds、`gross_ev_baseline`、`decision_as_of`、`max_input_observed_at` 與 payload hash。

Gold builder 的必要條件：

`max_input_observed_at <= decision_as_of`

若 provider timestamp 存在，也必須小於等於 decision time。任何違反都 hard fail，不允許以 warning 繼續。

## Payout / Cost Rule

Migration `0004` 建立版本化 `payout_cost_rules`。每個 rule 至少含 rule version、jurisdiction、market scope、effective window、payout factor、stake cost rate、fixed cost per unit stake、source reference、verified time 與 production eligibility。Rule 解析必須使用 `decision_as_of`，不允許用今天的規則回填歷史決策。

初始 `synthetic-zero-cost-v1` 僅供 synthetic test，`production_allowed=false`。本專案目前沒有來源支持任何真實台灣運彩 payout/tax 數值，因此沒有把此類數值寫入 production rule。

## Market Analysis Record

共用 analysis output 保存 market fair probability、model probability、model fair odds、edge、gross EV、net EV、uncertainty、data quality、recommendation、risk blockers、model validation flag、payout/cost rule version、`decision_as_of` 與 `max_input_observed_at`。API/MCP/Web 未來只序列化此 service 結果，不另行計算。


## NBA V1 Point-in-Time Feature / Training Sample

`NBAMoneylineFeatureRecord` 是第一個 sport-specific feature contract，欄位只包含 event id、feature version、`decision_as_of`、`max_input_observed_at`、home/away rating、home/away rest days 與 neutral-site flag。Contract 強制：

`max_input_observed_at <= decision_as_of`

`NBAMoneylineTrainingSample` 將 label/market evaluation metadata 與 feature 分離，保存 home result、decision-time home/away odds、`odds_observed_at`、closing odds / `closing_observed_at`、`result_observed_at` 與 decision-time de-vig market home probability。必要時間關係：

- `odds_observed_at <= decision_as_of`
- `decision_as_of <= closing_observed_at <= result_observed_at`

Closing odds 與結果不得成為 decision-time feature；只可用於 CLV、settlement 與 OOS evaluation。

## NBA Walk-Forward Evaluation Record

`WalkForwardEvaluationRecord` 保存 model/feature version、實際 test window、fold/sample/bet counts、model Brier/LogLoss/ECE、market Brier/LogLoss/ECE、ROI、Yield、CLV、Max Drawdown、bootstrap CI、risk of ruin，以及 model validation/recommendation 狀態。Synthetic evaluator 一律 `is_model_validated=false`。

## Calibration / Model Artifact / Validation Gate

`CalibrationRecord` 保存 calibration/model/feature versions、base-training end、calibration window、`fitted_at`、sample count 與 Platt intercept/slope。任何 decision 早於 `fitted_at` 不得使用該 calibrator。

NBA model artifact 為 canonical JSON，內容包含 model coefficients 與 calibration record；檔名即 SHA-256，保存於 PROJECT_ROOT-relative `models/<model_id>/<model_version>/<sha256>.json`。讀取時必須重新計算 checksum。

完整 backtest report 為 deterministic JSON，保存 artifact metadata、calibration、walk-forward evaluation 與 validation gate，路徑為 PROJECT_ROOT-relative `reports/backtests/<backtest_id>.json`。DuckDB `model_registry` / `backtest_runs` 保存核心索引欄位。

`ModelValidationPolicy` 為版本化 contract；`ModelValidationDecision` 只包含 policy/evidence tier、validated flag 與 blockers，不包含單場 recommendation。


## Free Provider Operations / Mapping Review

Migration 0006 新增 provider_usage_snapshots、provider_entity_proposals、event_results，並為 settlements
加入 paper_trade_id。Provider usage 保存 remaining/used/last request cost、local monthly budget 與 endpoint kind。

Entity proposal 狀態至少包含 PENDING / APPROVED / REJECTED。Proposal 本身不是正式 mapping；
只有人工 approve 才可寫 provider_entity_mapping。Reject 必須保存 reviewed_at/review_note。

## Event Result Record

EventResultRecord 保存 provider event identity、可選 canonical event id、home/away score、result outcome、
completed flag、observed_at、provider timestamp、PROJECT_ROOT-relative raw source ref 與 payload hash。

Local NBA feature history 只能使用 completed=true 且 result.observed_at <= decision_as_of 的 NBA events。
Scheduled time 已過但未有當時可見 completed result，不得視為已打完。

## Prediction Provenance

PredictionRecord 除 model/calibration/probability/EV/risk 欄位外，另保存 bookmaker、source 與
odds_snapshot_id。Paper trade 必須引用同一 event/market 的 point-in-time odds snapshot；snapshot
observed/provider timestamp 不得晚於 prediction as-of。

## Paper Trade / Settlement

PaperTradeRecord 保存 prediction id、event/market、decision_at、odds_snapshot_id、listed odds、stake、
status、model version 與 settlement rule version。SettlementRecord 可連回 paper_trade_id，保存 market result、
void reason、payout/tax rule version、gross/net payout、PnL 與 settled_at。

目前 paper settlement 只支援 full-game moneyline research rule；未知 settlement rule version hard fail。
此 contract 不代表任何實際台灣運彩派彩或稅務規則。

## Portable Backup Contract

Research backup v1 只允許 state、models、reports、config 四個 root。Manifest 每列保存 relative path、
SHA-256 與 bytes；archive 宣告 includes_raw_data=false。Restore 前必須驗 schema version、allowed root、
path traversal 與 checksum，且呼叫端必須顯式 force。

## Forward Collection Run Ledger

Migration 0007 新增 forward_collection_runs。每個 one-shot collection run 保存 provider、trigger_kind、
started_at/finished_at、status、current/scores due 與 attempted flags、events/odds/results/unresolved counts、
Data Quality、mapping rate、requests used before/after、credits_spent、remaining quota 與 sanitized error summary。

SKIPPED run 也是一級 evidence：它表示 scheduler/人工呼叫有發生，但 cadence/data-gap gate 判定不應送 provider request，
因此 credits_spent=0。FAILED/PARTIAL 的 error_summary 不得保存 API key；collector 會以 [REDACTED] 取代目前 secret。

ForwardCollectionStatusRecord 另外提供 latest endpoint timestamps、due flags、latest run、quota、live event/odds counts、
completed result count、past event without result count 與 next_event_start。Scores due 需要同時滿足時間 cadence 與
past_event_without_result_count > 0。

## Research Readiness / Automatic Evaluation Ledger

Migration 0008 新增 `research_readiness_runs`。每次 cycle 保存 research/readiness/validation policy versions、trigger/checked_at/status、完整 dataset fingerprint、可選 evaluation fingerprint、candidate/decisive/usable counts、decision/closing odds coverage counts、feature/missing-odds skips、180/360 derived thresholds、fold/OOS capacity、blockers、evaluation sample count、validation result與 report path。

`dataset_fingerprint` 對當下全部 usable samples 做 canonical hash；`evaluation_fingerprint` 只包含完整 non-overlap folds 實際會消耗的 sample prefix與 readiness policy，因此尚不足下一個完整 test fold的新尾端樣本不會造成無意義重跑。相同 evaluation fingerprint 已有 evaluated evidence 時 cycle 記 `SKIPPED_UNCHANGED`。

Research report 路徑為 `reports/backtests/readiness/<sha256>.json`，內容包含 readiness snapshot、walk-forward evaluation、validation gate與 `model_promotion_performed=false`。它不是 `model_registry` artifact，也不寫 `backtest_runs`；model lifecycle promotion 保持獨立且顯式。

Readiness status adapters可讀 latest persisted cycle snapshot，避免每次 Web/API/MCP query 都重建全量 training dataset；CLI `research-readiness` 仍可做即時計算。

## Operational Monitoring Snapshot

Migration 0009 新增 operational_monitor_snapshots。每筆 snapshot 保存 policy/trigger/checked_at/severity、
collection/research heartbeat 與 age、provider quota/local budget、event/odds/result counts、readiness/sample
coverage、相鄰 snapshot 的 odds/result/usable-sample deltas，以及 alerts JSON。

OperationalSeverity 僅描述系統營運健康：OK / WARN / FAIL。Research NOT_READY 不等同故障；只有 heartbeat
缺失或 stale、run failure/degraded、quota/budget 風險、scores result gap、odds coverage gap、material research
preflight blocker，以及 append-only counters 倒退才產生 alerts。counter regression 為 FAIL，避免資料被覆寫或回退
時靜默繼續研究。
