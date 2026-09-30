# Architecture Decisions

## ADR-0001 — Portable profile 以 DuckDB + Parquet 為預設

日期：2026-09-28

較早研究報告曾以 PostgreSQL/Prefect/MLflow 作主要部署設計；較新的整併來源文件與目前 Project
Instruction 明確改為 portable-first：DuckDB + Parquet + Polars 為 standalone 必要層，PostgreSQL、Prefect、
MLflow 降為 optional server profile。施工採較新的合併契約與目前指示，避免搬機依賴外部服務。

## ADR-0002 — PROJECT_ROOT resolver

顯式 override 使用 `SPORTS_EDGE_ROOT`，其次向上搜尋 `.sports-edge-root` 或 `pyproject.toml + .git`，最後
從 package 路徑向上搜尋；無法解析時明確失敗，不猜測磁碟位置。所有 runtime 路徑保存為 root-relative。

## ADR-0003 — 初始風控保守輸出

Foundation risk gate 在模型尚未通過 OOS/calibration gate 時，即使 net EV 為正也回傳
`NO_VALIDATED_EDGE`。Data Quality RED、非正 Net EV 或 data conflict 可直接 veto，不為了產生推薦降低門檻。

## ADR-0004 — 第一個資料 vertical slice 使用 synthetic NBA moneyline

日期：2026-09-28

在尚未取得台灣運彩或其他 provider 的合法正式資料存取前，Phase 1 使用可公開的 synthetic NBA pregame
moneyline fixture 驗證 Bronze → Silver → point-in-time → market baseline 的完整工程路徑。這不是模型 edge
證據，也不應被當作真實市場回測結果；provider adapter 之後可替換資料來源而不改核心 application logic。

## ADR-0005 — Bronze 使用 content-addressed object + immutable ingest manifest

日期：2026-09-28

同一 raw payload 以 SHA-256 作 object identity，避免重複 bytes；每個觀測時點另以 provider + observed_at + payload hash 形成 deterministic `ingest_run_id` 與 manifest。DB 只保存 PROJECT_ROOT-relative path。Bronze object/manifest 已存在但內容不同時 hard fail，不以覆寫方式修補歷史。

## ADR-0006 — V1 canonical market row 採 selection-level market_id

日期：2026-09-28

Foundation `canonical_markets.market_id` 是單欄 primary key，且 contract 同時要求 `selection`。為避免修改已套用 `0001` migration，本階段把 base market id 展開為 `<base>:<SELECTION>`（例如 `...:HOME` / `...:AWAY`）。若後續要把 market 與 selection 拆成獨立實體，必須用新 migration 演進，不得回改已套用 migration checksum。

## ADR-0007 — Synthetic metadata seed 明確標示 non-production

日期：2026-09-28

Phase 1 以 migration `0003` 建立 synthetic provider/license/entity mapping。Synthetic provider 的 `production_allowed=false`，license 僅涵蓋本專案自製 fixture；不得因此推論真實 sportsbook/provider data 可公開或可自動抓取。

## ADR-0008 — Gold market baseline 必須攜帶 point-in-time 證據

日期：2026-09-28

Gold market-baseline 每列保存 `decision_as_of` 與 `max_input_observed_at`，builder 先從 as-of repository 取資料，再以 application hard gate 二次驗證 `max_input_observed_at <= decision_as_of`；若 provider timestamp 存在亦不得晚於 decision time。此 gate 屬 defense-in-depth，不可因上游 query 已篩選就移除。

## ADR-0009 — Market baseline gross EV 不視為模型 edge

日期：2026-09-28

`gross_ev_baseline` 使用去水後 market fair probability 與該 selection 當時 listed odds 計算，只描述市場基準價格結構，通常反映 overround 成本；它不是 sport model 的 edge 證據。任何正式推薦必須等待獨立 model probability、calibration、net EV 與 risk gate。

## ADR-0010 — Walk-forward scaffold 採 expanding temporal windows

日期：2026-09-28

第一版 walk-forward scaffold 要求 timezone-aware、strictly increasing timestamps，train window 必須完全早於 test window，禁止 random shuffle。尚未加入可驗證 sport-specific model 前，scaffold 的決策狀態固定為 `NO_VALIDATED_EDGE`。

## ADR-0011 — Payout/Cost 規則必須版本化且依 decision time 生效

日期：2026-09-28

Net EV 不直接硬編碼任何台灣運彩稅務或派彩常數。Migration `0004` 建立版本化 `payout_cost_rules`，以 `effective_from/effective_to` 控制適用時點；application 以明確 rule version + `decision_as_of` 解析。初始只提供 `synthetic-zero-cost-v1` 且 `production_allowed=false`，只供工程測試。

Net EV 以每 1 單位 stake 正規化：`p * decimal_odds * payout_factor - 1 - stake_cost_rate - fixed_cost_per_unit_stake`。未來真實 jurisdiction 若規則語意不同，應以新 rule schema/version 演進，不得偷偷改既有版本。

## ADR-0012 — Market Analysis Service 是所有介面的唯一 EV/Risk 決策核心

日期：2026-09-28

CLI/API/MCP/Web 不得自行重算 edge、gross/net EV 或 recommendation。共用 Market Analysis Service 接收 as-of market baseline、model probability、payout/cost rule、uncertainty、data quality 與 model validation 狀態，再統一呼叫 Risk Gate。正 EV 但模型未驗證仍輸出 `NO_VALIDATED_EDGE`；負/零 Net EV 或 RED data quality 可直接 `NO_BET`。


## ADR-0013 — NBA V1 feature contract 僅允許 decision-time 可重建資訊

日期：2026-09-28

NBA V1 research baseline 只使用 rating difference、rest difference 與 neutral-site/home-court indicator。Feature contract 強制 `max_input_observed_at <= decision_as_of`；training sample 另保存 `odds_observed_at`、`closing_observed_at` 與 `result_observed_at`。Closing odds 與賽果只能用於事後評估，不得進入 decision-time model feature。

## ADR-0014 — 第一個 NBA sport model 採可解釋 logistic baseline

日期：2026-09-28

第一個 NBA model 不使用複雜 ensemble 或外部 AutoML。採純 Python logistic baseline，明確暴露 intercept、rating-difference、rest-difference、home-court coefficients；rating difference 以 100 rating points 為一個 feature unit。其目的是建立可測試、可解釋、可 walk-forward 的 baseline，而不是宣稱已取得市場 edge。

## ADR-0015 — Walk-forward training eligibility 以 label availability 為準

日期：2026-09-28

Walk-forward 不只要求 train decision time 早於 test；training sample 還必須滿足 `result_observed_at <= fold test start`，避免使用當時尚未結束比賽的結果。Test windows 不允許 overlap，以免重複計分；payout/cost rule 必須覆蓋完整 test fold。任何違反都 hard fail。

## ADR-0016 — Phase 3 metrics 與 synthetic validation gate 定義

日期：2026-09-28

Walk-forward 同時輸出 model 與 de-vig market baseline 的 Brier、LogLoss、ECE。投注型指標以 unit-stake research simulation 計算：ROI = total PnL / starting bankroll；Yield = total PnL / total bet count；CLV = selected offered decimal odds / corresponding closing decimal odds - 1；Max Drawdown 為 bankroll peak-to-trough 比例；bootstrap CI 為 per-bet yield；risk of ruin 為相同有限 test horizon 的 bootstrap estimate。

Synthetic research sample 只能驗證工程與 metric path。即使 synthetic model 指標優於 market baseline，Phase 3 仍固定 `is_model_validated=false` / `NO_VALIDATED_EDGE`；正式 validation gate 必須在獨立 calibration 與真實 point-in-time OOS evidence 上建立。


## ADR-0017 — Calibration 採 time-separated Platt scaling

日期：2026-09-28

第一版 calibration 使用 Platt scaling，輸入為 base model raw probability 的 logit。Base-training outcomes 必須在 calibration window 開始前已可知；calibrator 的 `fitted_at` 為 calibration outcomes 全部可知的時間，任何早於 `fitted_at` 的 decision 不得使用該 calibrator。Walk-forward 若啟用 calibration，必須每 fold 以 settled history 切成 base-train → calibration → test，不可用全資料先校準再回測。

## ADR-0018 — Model artifact 為 canonical JSON + content-addressed SHA-256

日期：2026-09-28

NBA V1 artifact 保存 model identity/version/feature version、可解釋 coefficients 與 calibration record。序列化採 deterministic canonical JSON，SHA-256 同時作完整性驗證與 artifact filename。路徑只能位於 PROJECT_ROOT-relative `models/`；load 時重新計算 checksum。相同 checksum path 若 bytes 不同必須 hard fail。

## ADR-0019 — Registry / backtest 核心欄位入 DuckDB，完整 report 另存 portable JSON

日期：2026-09-28

沿用 foundation `model_registry` 與 `backtest_runs`，不回改已套用 migration checksum。既有 table 保存可查詢核心欄位；model-vs-market metrics、calibration、validation blockers、evidence tier 與 artifact metadata 另以 deterministic JSON 存到 PROJECT_ROOT-relative `reports/backtests/`。Registry/backtest persistence 要 idempotent；相同 identity 不同內容視為 provenance conflict。

## ADR-0020 — Model validation gate 與單場 EDGE recommendation 分離

日期：2026-09-28

Validation gate 只回答「此 model/version 是否符合指定 policy 的驗證條件」，不得直接輸出單場 `EDGE`。Policy 同時檢查 sample/bet count、Brier/LogLoss/ECE 相對 market baseline、Yield、CLV、Max Drawdown、bootstrap CI low、risk of ruin 與 evidence tier。第一版 research policy 僅接受 `HISTORICAL_POINT_IN_TIME`；`SYNTHETIC` 一律 fail closed。單場 `EDGE / NO_BET / WATCH` 仍只能由 Market Analysis Service 基於該場 odds、model probability、cost rule、data quality 與 risk gate 決定。

## ADR-0021 — API / MCP 共用 Interface Service，adapter 不得重算 domain 邏輯

日期：2026-09-28

Phase 4 新增 `application/interface_service.py` 作 read/query facade。FastAPI 與 MCP 只能負責 transport、schema serialization 與 error mapping；market de-vig、fair odds、edge、Gross/Net EV、data quality 與 risk decision 必須繼續由既有 application services 計算。Web UI 只呼叫 REST API，不自行計算投注判斷。

## ADR-0022 — MCP 採官方 Python SDK stable v2 且預設 read-only

日期：2026-09-28

施工時重新驗證官方 MCP Python SDK；stable line 為 v2，使用 `MCPServer` 與 `@mcp.tool()`。Project dependency pin 為 `mcp>=2,<3`，本輪 lockfile 解析 2.2.0。所有 Phase 4 tools 標記 `read_only_hint=true`、`idempotent_hint=true`、`open_world_hint=false` 且使用 typed return schema。MCP 不暴露 ingestion、migration、artifact write、backtest execution 或下注 mutation。

## ADR-0023 — Read interface 使用 DuckDB read-only connection

日期：2026-09-28

Odds、payout/cost rule、model registry、backtest lookup 與 system health 的 read path 使用 DuckDB `read_only=True` connection。Health check 在 database 尚不存在時直接回 `uninitialized`，不得為了讀取狀態而建立空 DuckDB。Market baseline 在 API/MCP path 固定 `persist=False`。

## ADR-0024 — Web UI 不持有模型/風控規則，built assets 可由 FastAPI 同源提供

日期：2026-09-28

React UI 僅保存表單輸入與 API response view models。Probability chart 使用 ECharts module import 並 lazy-load；不在 TypeScript 重算 market probability、fair odds、EV 或 recommendation。Production build 產物為可重建 `frontend/dist`，不納入 Git；若 dist 存在，FastAPI 在 API routes 後掛載為同源靜態 UI。

## ADR-0025 — Portable bootstrap 同時驗證 Python 與 frontend

日期：2026-09-28

Standalone profile 已包含 Web UI，因此 bootstrap 不得只驗證 Python。`scripts/bootstrap.ps1` 必須同時執行 uv sync、migration、Ruff、mypy、pytest、npm ci、Vitest 與 Vite production build；`node_modules`、`dist`、`.venv` 與 TypeScript build info 都視為可重建產物。

## ADR-0026 — 第一個真實 odds provider 採 The Odds API historical v4

日期：2026-09-28

Phase 5A 以官方 terms/docs review 後選擇 The Odds API 作第一個真實 provider connector。理由不是「資料一定最好」，而是其 API/terms 對 automated access、storage、analytical dashboard、derived values、ML use 與 historical snapshot semantics 有明確公開文件，且 historical endpoint 可回傳小於等於 requested timestamp 的 point-in-time snapshot。Provider registry 先 `enabled=true`、`production_allowed=false`；帳號 entitlement 未實機驗證前不得升級。

## ADR-0027 — The Odds API raw data 永不視為可公開再散布資料

日期：2026-09-28

2026-09-28 review 的 provider terms 允許應用/分析使用，但禁止 standalone raw-data resale/repackaging/redistribution。因此 migration `0005` 將 `redistribution_allowed=false`，Bronze manifest 與 raw_objects 一律 `public_export_allowed=false`。Git/public release 只能包含 connector code、schema、docs 與 project-authored synthetic contract fixtures，不得提交真實 provider payload。

## ADR-0028 — API credential 只從 secret setting 讀取，CLI 不接受 key argument

日期：2026-09-28

The Odds API key 使用 `SPORTS_EDGE_THE_ODDS_API_KEY`，由 Pydantic `SecretStr` 讀取。CLI 不提供 `--api-key`，避免 credential 進 shell history；HTTP transport 對 HTTP/URL errors 做 sanitized wrapping，不回傳含 query key 的 request URL。沒有 credential 時 connector 明確失敗，不 fallback 到 scraping。

## ADR-0029 — Provider team identity mapping fail closed

日期：2026-09-28

The Odds API event payload以 team name 作 entity identifier。SPORTS_EDGE_AI 不直接把 provider name 當 canonical ID，也不做未審核 fuzzy auto-mapping。若 TEAM mapping 缺失，只保存 Bronze 並寫 Data Quality RED / mapping_rate，不寫 canonical event/market/odds。Mapping 完整後才進 Silver/canonical layer。

## ADR-0030 — Historical odds observed_at 採 conservative visibility timestamp

日期：2026-09-28

Historical response envelope timestamp 必須 `<= requested_at`。Market/bookmaker `last_update` 若存在也必須 `<= requested_at`。單筆 canonical odds 的 `observed_at` 取 envelope snapshot timestamp 與 market/bookmaker update timestamp 的較晚者，避免 provider update 晚於 snapshot 標記時產生 look-ahead。Phase 5A 僅處理 pregame NBA h2h decimal odds。


## ADR-0031 — Free-plan provider operations 以 local quota budget fail closed

日期：2026-09-28

沒有 historical entitlement 時，不以 scraping 規避官方 API。改用 provider 官方 current odds、
participants、scores 路徑完成 operational research workflow。所有 request 共用 secret-only credential、
Bronze provenance、quota header parser 與 local monthly credit budget。預設 local budget 450，
超過本地 budget 時拒絕 request；provider usage snapshot 持久化供 API/Web/MCP read。

## ADR-0032 — Provider entity mapping 必須人工 approve/reject

日期：2026-09-28

Participants 只建立 deterministic PENDING proposal，不以 fuzzy string matching 直接建立高信心 mapping。
只有人工 approve 才能寫 provider_entity_mapping；reject 必須保存 review note，並移除可能存在的 mapping。
正式 NBA team review 以 NBA_ entity id prefix 排除 synthetic team entity。MCP 只讀 proposal/summary/candidate，
不提供 approve/reject mutation。

## ADR-0033 — Local NBA feature history 只使用當時已知 completed results

日期：2026-09-28

Elo 與 rest days 只能由 decision_as_of 前已觀測到 completed result 的 NBA games 推導。只因賽事排程時間
已過，不代表當時可確認已完成；取消、延期、未完成或 result 尚未觀測的 event 不得影響 rating/rest。
多場同一 decision time 合法，因此 feature/calibration/walk-forward sequence 採 nondecreasing time，
但仍維持 label availability 與 point-in-time hard gate。

## ADR-0034 — Paper trading 僅接受 validated EDGE，settlement rule 版本 fail closed

日期：2026-09-28

Paper trade 是研究層，不是自動下注。開立前必須同時滿足 model registry VALIDATED、prediction EDGE、
Data Quality GREEN、Net EV > 0、odds snapshot 與 prediction event/market 一致且在 as-of 已可見；
live odds 不允許自動開 paper trade。Settlement 目前只支援 full-game moneyline paper-moneyline-v1；
未知 rule version 或 future result timestamp hard fail。API/Web/MCP 只讀 portfolio/result，mutation 留 CLI。

## ADR-0035 — Portable backup 排除 raw data；restore 與 public push 都需顯式 gate

日期：2026-09-28

Research backup v1 只包含 state、models、reports、config；不包含 Bronze/Silver/Gold、logs、.env 或 provider raw。
Archive 內 manifest 保存 root-relative path、bytes、SHA-256；restore 先驗 path traversal/checksum，且必須
顯式 force 才能覆寫本機 state。Publication audit 掃 tracked secret/runtime/raw/DB/model/report/backup、
大檔、機器絕對路徑、必要治理文件與 dependency license metadata。即使 audit 無 blocker，第一次 public
push 仍需使用者確認 repo 名稱、visibility、tracked files 與 license。


## ADR-0036 — CI 使用跨平台 matrix 且 third-party Actions 必須 full-SHA pin

日期：2026-09-28

Public repository 的 quality gate 需覆蓋 Windows 與 Linux，以及最低支援 Python 3.11 與目前施工驗證的
Python 3.14。Frontend 固定使用 Node 24。External GitHub Actions 不使用 floating tag/branch；
actions/checkout v7.0.1、actions/setup-python v7.0.0、actions/setup-node v7.0.0 與
astral-sh/setup-uv v10.2.0 均 pin 到 40-character commit SHA。Publication audit 對未 pin external
Action 直接 BLOCKER，避免 supply-chain ref 漂移。

## ADR-0037 — Release bundle 是 deterministic source+Web artifact，不包含 operational state

日期：2026-09-28

Release bundle 由 Git tracked source/governance files 加上當次 frontend/dist production build 組成，
ZIP entry 使用固定 timestamp、排序路徑與 deterministic metadata，release-manifest.json 保存每個檔案
bytes/SHA-256。建立 bundle 前必須 publication audit 0 blockers/0 warnings；output 只能位於
PROJECT_ROOT 之下。Bundle 明確不包含 DuckDB、Bronze/Silver/Gold、provider raw、.env、models、
reports 或 backups 本身，因此它是可重建程式交付物，不是研究資料/模型快照。

## ADR-0038 — Secret dotenv 必須綁定 resolved PROJECT_ROOT

日期：2026-09-28

Settings 不再依 process current working directory 尋找 .env，而是固定讀取 resolved PROJECT_ROOT/.env；process environment 仍有較高優先權。原因是 portable folder 可同時存在多份，若以 CWD 載入 secret，測試或另一份專案可能誤讀別的 workspace credential。CLI 新增 configure-odds-api-key，以隱藏輸入與原子 replace 寫入本機 ignored .env；空字串不再被 doctor 或 provider helper 視為已配置 credential。

## ADR-0039 — Forward collector 是 one-shot service；scheduler 只負責喚醒

日期：2026-09-28

Point-in-time history 的累積不得綁死在 Windows Task Scheduler、cron 或 Web/MCP adapter。核心 application service
每次只執行一個 bounded collection run，先檢查 endpoint freshness、local monthly credit budget 與資料缺口，再決定
current odds / scores 是否 due。預設 current 最短 180 分鐘；scores 最短 720 分鐘，且只有 canonical event
scheduled_start 已過但仍缺 completed result 時才會 due。外部 scheduler 可每 60 分鐘喚醒，SKIPPED run 必須保存
ledger 且不得送 request。

Migration 0007 保存 run ledger，包含 quota delta、Data Quality/mapping evidence與 sanitized errors。CLI 是唯一 execution
surface；FastAPI/MCP/Web 只讀 status。Windows helper 使用 IgnoreNew 防止重疊，且提供 -WhatIf 與 unregister helper；
因此 scheduler 是可替換、可撤銷的 operational adapter，不是 domain dependency。

## ADR-0040 — Readiness capacity 與 model promotion 必須分離

日期：2026-09-29

nba-readiness-v1 不另創模型門檻，而是直接引用既有 walk-forward 與 nba-research-gate-v1。160 train + 20 test
表示 180 usable samples 才能首次評估；validation policy 需要至少 200 OOS samples，因此 20-sample non-overlap
folds 下需 360 usable samples 才具備 sample-count capacity。這些數字只代表是否能執行研究，不代表模型已驗證。

Research cycle 對 dataset / complete-fold sample prefix 做 fingerprint 與 dedup，只寫 research readiness ledger 與
reports/backtests/readiness 下 deterministic evidence。即使 validation gate pass，model_promotion_performed 仍固定 false，
且不寫 model_registry；正式 model lifecycle 維持顯式、人工可審核的 gate。

## ADR-0041 — Operational monitor 只觀測 pipeline health，不介入模型或投注

日期：2026-09-29

Migration 0009 的 operational monitor 把 collection/research heartbeat、quota/local budget、result gap、odds coverage、
readiness 與 append-only counter drift 統一成 versioned snapshot。NOT_READY 本身不是 warning；資料不足是正常 research
state。真正的 stale heartbeat、failed/partial run、quota/budget 風險、coverage/preflight gap 為 WARN/FAIL，counter
倒退直接 FAIL。

Scheduler 每次 collection/research chain 後寫 monitor snapshot；即使前一階段失敗，monitor 仍應嘗試執行並保留第一個
failure exit code。CLI 是 monitor write surface，FastAPI/MCP/Web 只讀 latest snapshot。Monitor 不自動修復、不自動 model
promotion、不產生下注動作。

## ADR-0042 — Portable bootstrap 的 native command 必須 fail-fast

日期：2026-09-29

PowerShell 的 `$ErrorActionPreference = "Stop"` 不會自動把所有 native executable 的非 0 exit code 轉成 terminating error；因此只依賴它可能讓 `uv` / `npm` 的失敗被後續成功命令覆蓋，造成 bootstrap 假綠。

`scripts/bootstrap.ps1` 對 `uv sync`、migration、Ruff、mypy、pytest、`npm ci`、Vitest、Vite build 與 doctor 的每個 native command 都必須立即檢查 `$LASTEXITCODE`，任一非 0 即停止。`.venv` 屬可重建 runtime；若因中斷安裝或殘留 project process 損壞，只能清除該 PROJECT_ROOT 的 `.venv` 並依 lockfile 重建，不得藉此刪除 state、data、models、reports 或 credentials。

## ADR-0043 — Repo URL-only 只保證 offline reproducibility；live cloud 必須有 durable state

日期：2026-09-29

Public GitHub URL 可作為 source distribution contract，但不可作為真實 point-in-time data store。新增 `sports-edge repo-smoke`，在 ephemeral PROJECT_ROOT 以 tracked migrations + synthetic fixtures 驗證 migration、as-of future-leakage hard gate 與 shared Market Analysis Service；它不讀 secret、不送 network request、不修改既有 operational state，且固定 model_validated=false，禁止產生 EDGE。

若 AI 具備 Git/Python/uv 執行環境，repo URL 足以 clone 後執行此 smoke；若 AI 只有網頁閱讀能力，URL 本身不構成 execution runtime。真實 live/continuous collection 要在個人電腦關機時仍運作，必須另有 remote compute、durable storage、secret injection、scheduler 與 writer/concurrency contract。GitHub Actions 保持 CI/manual ephemeral role，不以 Actions artifact/cache 傳遞 DuckDB/raw history 來冒充正式 operational state，避免 provenance、atomicity、授權與故障恢復退化。

## ADR-0044 — 永不付費是 hard runtime policy；完整 operational state 以 private checkpoint 搬移

日期：2026-09-30

使用者明確要求永不付費，因此此專案的 cloud-ready policy 固定 `paid_services_allowed=false` 與 `automatic_billing_allowed=false`。任何免費 backend 若要求付費升級、超額自動扣款、刪除 point-in-time evidence、把 raw/state 放 public Git，或把 GitHub Actions artifact 當唯一 state authority，都不是合法 fallback。無可驗證免費 durable backend 時，`LIVE_REMOTE_BLOCKED` 是正確狀態。

跨機器 operational state contract 採 private checkpoint，而不是 Git history。Checkpoint roots 固定為 Bronze/Silver/Gold、state、models、reports；排除 `.env`、logs、backups。建立時先要求 DuckDB current schema 等於 latest tracked migration，再掃描 configured provider secret 不得出現在 operational files，對每個檔案保存 SHA-256/bytes，temporary archive 完成後才 atomic rename。Manifest 明確標示 `includes_raw_data=true`、`public_export_allowed=false`、`secret_transport=false`。

Restore 只允許 empty runtime；archive path、manifest、hash、size 與 schema 全部先驗證。拷貝後再次執行 migration integrity check，若 checkout migration 與 restored DB 不一致或任何 post-copy check 失敗，必須刪除本次新增檔案。未來 free object-store adapter 必須實作 private durable storage、atomic/versioned publish、single-writer/CAS、quota fail-closed 與可攜 export；通過 round-trip regression 前不得解除 remote live blocker。

## ADR-0045 — Durable backend 先以 protocol + reference adapter 驗證，不直接綁免費供應商

日期：2026-09-30

Phase 14 不先選外部服務，而先定義 `zero-cost-checkpoint-backend-v1`。Backend 必須公開 capability facts，application evaluator 依 private/durable/no-auto-billing/atomic-or-versioned/single-writer/quota-fail-closed/secret-separation/portable-export/remote-access 判斷 blockers。這避免 adapter 自稱免費即可解除 live gate。

`local-filesystem-reference-v1` 只作 executable specification：content-addressed objects、atomic pointer、exclusive writer lock、expected-generation CAS、quota preflight、verified fetch。它固定 `remote_access=false`、`reference_only=true`，所以即使 contract smoke 完成也永遠不是 remote-live eligible。

未來任何免費 provider adapter 必須先通過同一批 round-trip、stale-CAS、second-writer、quota-preserves-history tests，再以真實服務 capability/evidence 接受 evaluator。沒有 provider-specific round-trip evidence 前，`LIVE_REMOTE_BLOCKED` 不變。

## ADR-0046 — Phase 15 僅 Backblaze B2 進入 conditional preflight；未驗證帳號前不實作 remote adapter

日期：2026-09-30

以官方公開文件比對零付費 hard policy 後，Backblaze B2 是唯一值得進下一輪實測的候選：10 GB free、可不提供 billing method 開始、private bucket、版本預設保留、bucket revision + `ifRevisionIs` CAS、non-paying account transaction cap，以及 scoped application keys 都符合架構方向。但官方同時說明未設定 data caps 時可累積費用，因此 B2 只能標 CONDITIONAL；未在真實帳號證明 no-payment-method + hard data caps 前，不得把 `automatic_billing_possible` 設為 false。

Supabase Free 只留 secondary/control-plane 可能性，因 1 GB storage 與 auto-pause；Cloudflare R2 因 subscription checkout/billable overage、Google Drive 因已公告 2026 年稍後超額計費、Dropbox Basic 因 over-quota 可能刪檔，不作 authoritative state backend。GitHub Actions public standard runners可作 ephemeral compute，仍禁止成為 state authority。

Phase 16 必須由使用者先建立免費 B2 account 並完成安全設定，再以 scoped key 做 provider-specific round-trip；未有 credential/evidence 前只維持文件候選，不先寫假 adapter。

## ADR-0047 — B2 Phase 16A 使用兩把最小權限 key；真實 cap evidence 不等於 remote-live approval

日期：2026-09-30

使用者實際 Caps & Alerts 畫面已證明 storage `$0.00 / 10 GB`、download `$0.00 / 1 GB`、B/C transaction 2,500/day，因此三個 cap evidence 可在 ignored local settings 標 true；畫面未證明 billing method absence，所以 no-payment evidence 仍 false，禁止推論。

Native API CAS 採 bucketInfo + bucket revision / `ifRevisionIs`。官方 capability contract 顯示 `writeBuckets` 不允許 bucket-restricted key，因此單一 bucket-scoped key 無法同時滿足 file access 與 bucket CAS。架構改成 data key（bucket+prefix scoped，最小 read/writeFiles + replication-read）以及 pointer key（account-wide 但只 listBuckets+writeBuckets）兩把 secret；pointer key 不具 delete、file、key-management capability。這個限制必須在 preflight 中顯式驗證，不能用 master key 取代。

Phase 16A adapter 允許在 round-trip gate 尚未通過前做受控 publish/fetch 測試，但 production `remote_live_ready` 必須等 provider round-trip evidence 為 true；403 cap、409 conflict、public bucket、replication、lifecycle deletion、過度權限或 checksum mismatch 任一發生皆 fail closed。

## ADR-0048 — B2 真實 round-trip 只能在空專用 bucket 執行，且不得自動啟用 scheduler

日期：2026-09-30

使用者明確確認 Backblaze 帳號沒有付款方式，因此 no-payment manual evidence 可與既有 `$0` caps 一起標 true；public repo 只記錄布林結論，不保存帳號或截圖。

`b2-live-roundtrip` 是 destructive-risk-minimized provider qualification，不是 production state migration。它必須先通過 billing/key/bucket storage preflight，並拒絕已有 current checkpoint pointer 的 bucket，避免 synthetic qualification state 覆蓋任何真實 operational pointer。Round-trip 只建立隔離 synthetic PROJECT_ROOT，依 migration 建立 tiny checkpoint，publish/fetch/verify/restore 後執行 stale revision CAS probe；不刪 immutable versions，失敗時 fail closed。

B2 pointer key 除 capability 最小化外，必須 account-wide scope（Backblaze writeBuckets 限制）且與 data key 同一 account；data key 仍必須 bucket+prefix scoped。Operational checkpoint leakage scan 擴充到所有 B2 key ID/application-key secrets。Provider qualification PASS 只代表 durable backend 有資格進下一 phase；不自動建立 GitHub Actions remote-live scheduler，也不變更 model/readiness gate。
