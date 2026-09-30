# Development Handoff

更新日期：2026-09-30

## Current state

- 第一個 NBA pregame moneyline portable vertical slice 已完成到 research / paper-only operational level。
- DuckDB schema：0009。
- Branch：main。
- Git：`main` 已建立公開 Git history，tracking `origin/main`；repository-local identity 為 `fishke22 <fishke22@gmail.com>`。
- Public GitHub：`https://github.com/fishke22/SPORTS_EDGE_AI`，visibility=public，default branch=`main`。
- Provider：The Odds API free operational path 已完成 live validation；historical entitlement probe=HTTP 401；production_allowed=false。
- Model：research workflow 完成；沒有真實 OOS/calibration evidence 前維持未驗證。
- Betting：沒有自動下注；只有 paper-only research workflow。

## Last completed construction

- Free current odds / participants / scores connectors + quota budget。
- Manual provider entity proposal/list/approve/reject + review summary。
- Event result provenance與 canonical event resolution。
- Local NBA Elo/rest feature + training dataset from decision-time-known completed results only。
- Prediction bookmaker/source/odds_snapshot_id provenance。
- Paper trade + settlement + read-only portfolio/result interfaces。
- API/MCP/Web operational status reads。
- Portable backup/restore。
- Executable publication audit。
- Cross-platform GitHub Actions quality gate with full-SHA action pins。
- Offline system doctor / research-readiness diagnostics。
- Deterministic release bundle with fixed ZIP metadata and per-file SHA-256 manifest。
- Forward point-in-time collector with due-check、quota guard、run ledger、freshness/result coverage status 與 portable scheduler helpers。
- Research readiness/cycle with 180 first-evaluation gate、360 validation-sample-capacity gate、coverage/temporal/calibration preflight、fingerprint dedup 與 no-auto-promotion guarantee。
- Operational monitoring with heartbeat/quota/coverage/readiness drift alerts、monotonic counter checks、persisted snapshots 與 scheduler chaining。
- Repository URL offline smoke：ephemeral PROJECT_ROOT + tracked synthetic fixtures + shared market analysis，無 network/credential/persistent-state dependency。
- `docs/CLOUD_RUNTIME.md`：定義 repo URL-only 與 live cloud runtime 的能力邊界；GitHub Actions 不作正式 point-in-time state authority。
- Zero-cost runtime policy：paid/automatic billing 永久 fail-closed；沒有 verified free durable backend 就 `LIVE_REMOTE_BLOCKED`。
- Private operational checkpoint：Bronze/Silver/Gold + DuckDB state + models/reports，configured-secret leakage scan、atomic build、strict verify、empty-target restore、post-copy migration integrity 與 rollback。
- Zero-cost durable backend contract：provider-neutral capability evaluator + `local-filesystem-reference-v1` executable specification；CAS、single-writer、quota fail-closed、versioned objects、verified round-trip 已測試，reference backend 永遠不能解除 remote-live blocker。
- docs/OPERATIONS.md、API/MCP/Provider/Data Contract/ADR/README closeout。

## Validation

- pytest：9.1.1，121 passed；Phase 14 backend contract/CAS/quota/round-trip regressions 已納入。
- Phase 12 targeted：`sports-edge repo-smoke`=PASS；08:30Z as-of 只看到 08:00Z odds；recommendations=NO_BET/NO_VALIDATED_EDGE，validated_edge_claimed=false；repository-smoke + CLI targeted 10 passed；Ruff passed；mypy 61 source files / 0 issues。
- persisted-readiness regression：snapshot 存在時 read facade 不重建 training dataset；無 snapshot 時 fallback live assessment；snapshot sample/status/remaining/blockers 與 ledger 一致。
- Ruff：passed。
- mypy：66 source files / 0 issues。
- frontend Vitest：2 passed。
- TypeScript/Vite production build：passed。
- npm audit：0 vulnerabilities。
- portability：passed。
- Phase 14 final full bootstrap：passed；migration 0009、Ruff、mypy 66 source files、121 Python tests、Frontend 2 tests/build/npm audit 全綠；doctor 只有既有 production_allowed=false WARN。
- Phase 10 live smoke：readiness 0/180/360、MANUAL/SCHEDULED cycle 均 NOT_READY；model_registry/backtest_runs 維持 0。
- Phase 11 live smoke：latest operational snapshot=SCHEDULED / OK / 0 alerts；odds/result/sample delta=0；Task Scheduler Last Result=0。
- publication audit：首次 commit 後重新掃描 Git history，0 blockers / 0 warnings；175 tracked files，public push gate 通過。
- system doctor：DEGRADED / ready_for_research=true；schema/locks/frontend build/credential 均 OK，只有 production gate WARN。
- release bundle：builder / manifest / deterministic hash / raw-exclusion smoke 已通過；runtime ZIP 位於 ignored backups/releases。
- Windows Task Scheduler：`SPORTS_EDGE_AI Forward Collection` 已註冊，每 60 分鐘 wake；Run As fishk / Interactive-only / IgnoreNew / StartWhenAvailable / 10 分鐘 limit。Task action script 現為 collection -> research-cycle -> ops-monitor；實機 trigger 成功，collection=SCHEDULED+SKIPPED、research=SCHEDULED+NOT_READY、monitor=SCHEDULED+OK、quota 維持 493。
- localhost:8000 已有非本專案服務，因此 smoke 使用 18000；未終止或修改既有 8000 listener。

## Tool handoff

Phase 10 主要由 WebCodex 施工；stream recovery timeout 後，使用者明確要求切換 Remote Desktop Commander。切換前先核對 git status/diff 與 handoff；RDC 接手時確認 persisted-readiness optimization、schema 0008 與既有 scheduler chain 都已落檔，因此沒有重做已完成修改。Phase 11 自 migration 0009、operational monitor、介面/scheduler 接線到 closeout 全由 RDC 作為唯一 writer，沒有雙 writer。
Phase 12 repository URL/cloud-ready contract 由 WebCodex checkout 作為唯一 writer；沒有與 RDC 同時修改 D:\\sport。第一個合併 validation shell 因舊 PowerShell 不支援 `&&` 且後續整組 job timeout，改用 structured `run_process` 拆解驗證；repo-smoke 與 targeted tests 實際通過後才更新文件。
Phase 13 仍由 WebCodex 作為唯一 writer。Stream recovery polling timeout 後使用者要求從中斷處續作；session recovery 顯示 checkpoint regressions、zero-cost runtime/CLI/tests 與一次 validation 已在 timeout 期間實際完成，因此沒有重做。接續只完成未落地的 docs/CI、最終 bootstrap、publication audit 與發布收尾。
Phase 14 由 WebCodex 作為唯一 writer，工作樹自 `907fed0` clean HEAD 開始。此 phase 僅建立 backend protocol/reference adapter 與 contract regression，不連接外部服務、不建立帳號、不要求信用卡或付款資訊。
Phase 15 由 WebCodex 作為唯一 writer，自 clean `27d899a` 開始；只做官方公開文件調查與 docs 更新，不改 runtime code、不建立外部帳號/資源。

## Known external gates

- SPORTS_EDGE_THE_ODDS_API_KEY 已透過 ignored local .env 驗證可用；不得提交或回顯 secret。
- historical paid entitlement probe 回 HTTP 401；不要執行 10-credit historical odds call。
- live provider mapping 已 review：30 approved / 2 rejected / 0 pending / completion=1.0。
- current live state：44 canonical events / 642 odds snapshots / 0 completed results；最新 provider quota remaining=493 / used=7。初始 mapping validation 仍為 GREEN / mapping_rate=1.0。
- production model validation 尚未達成，正確輸出仍可為 NO_VALIDATED_EDGE。
- Public repo URL 已能在具 execution runtime 的 AI/cloud checkout 執行無 credential `sports-edge repo-smoke`；但真實 point-in-time runtime data 不在 Git，電腦關機後要持續 live collection 仍需另建 durable cloud runtime。
- 使用者要求永不付費；`zero-cost-runtime-v1` 已將 paid/automatic billing、public Git state、Actions artifact state authority、刪 evidence 換 quota 全列為 forbidden fallback。Operational checkpoint 可安全搬移完整 runtime，但目前沒有 verified free private durable backend，因此 remote live 仍 blocked。
- Phase 14 已完成 `zero-cost-checkpoint-backend-v1` 與 local reference adapter；它證明 backend 介面/CAS/quota/round-trip 可行，但因 NO_REMOTE_ACCESS + REFERENCE_ONLY_BACKEND 仍不可用於 remote live。
- Phase 15：Backblaze B2 為唯一 CONDITIONAL candidate；優點為 10 GB free/no billing method to start/private/versioned/bucket revision CAS/non-paying caps，blocker 是未在真實帳號證明 hard $0 cap/no-payment safety。Supabase secondary only；R2/Google Drive/Dropbox 淘汰。詳見 `docs/ZERO_COST_BACKEND_CANDIDATES.md`。
- 台灣運彩 adapter / payout-tax version 尚無合法官方資料來源，未硬編碼猜值。
- Git identity 已以 repository-local 設定為 `fishke22 <fishke22@gmail.com>`；首次 commit 與 public push 已完成。
- 後續 GitHub 修改仍應維持 publication audit、secret/data/license gate 與 CI quality gate。

## Next action after this handoff

本機 hourly collection/research/monitor 與模型/readiness gate 保持不變。下一階段 Phase 16 是 Backblaze B2 real-account preflight + adapter round-trip；但必須先有使用者建立的免費 B2 帳號，並人工確認未綁付款方式與 data caps。取得 scoped application key 後才施工 adapter。若 data cap 無法證明 hard $0 或任何 round-trip/CAS/quota gate 不通過，就淘汰 B2、停止 cloud live 施工並維持 LIVE_REMOTE_BLOCKED。
