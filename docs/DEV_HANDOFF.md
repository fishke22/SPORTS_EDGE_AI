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
- docs/OPERATIONS.md、API/MCP/Provider/Data Contract/ADR/README closeout。

## Validation

- pytest：9.1.1，113 passed；Phase 13 zero-cost/checkpoint regressions 已納入。
- Phase 12 targeted：`sports-edge repo-smoke`=PASS；08:30Z as-of 只看到 08:00Z odds；recommendations=NO_BET/NO_VALIDATED_EDGE，validated_edge_claimed=false；repository-smoke + CLI targeted 10 passed；Ruff passed；mypy 61 source files / 0 issues。
- persisted-readiness regression：snapshot 存在時 read facade 不重建 training dataset；無 snapshot 時 fallback live assessment；snapshot sample/status/remaining/blockers 與 ledger 一致。
- Ruff：passed。
- mypy：63 source files / 0 issues。
- frontend Vitest：2 passed。
- TypeScript/Vite production build：passed。
- npm audit：0 vulnerabilities。
- portability：passed。
- Phase 13 final full bootstrap：passed；migration 0009、Ruff、mypy 63 source files、113 Python tests、Frontend 2 tests/build/npm audit 全綠；doctor 只有既有 production_allowed=false WARN。
- Phase 10 live smoke：readiness 0/180/360、MANUAL/SCHEDULED cycle 均 NOT_READY；model_registry/backtest_runs 維持 0。
- Phase 11 live smoke：latest operational snapshot=SCHEDULED / OK / 0 alerts；odds/result/sample delta=0；Task Scheduler Last Result=0。
- publication audit：首次 commit 後重新掃描 Git history，0 blockers / 0 warnings；170 tracked files，public push gate 通過。
- system doctor：DEGRADED / ready_for_research=true；schema/locks/frontend build/credential 均 OK，只有 production gate WARN。
- release bundle：builder / manifest / deterministic hash / raw-exclusion smoke 已通過；runtime ZIP 位於 ignored backups/releases。
- Windows Task Scheduler：`SPORTS_EDGE_AI Forward Collection` 已註冊，每 60 分鐘 wake；Run As fishk / Interactive-only / IgnoreNew / StartWhenAvailable / 10 分鐘 limit。Task action script 現為 collection -> research-cycle -> ops-monitor；實機 trigger 成功，collection=SCHEDULED+SKIPPED、research=SCHEDULED+NOT_READY、monitor=SCHEDULED+OK、quota 維持 493。
- localhost:8000 已有非本專案服務，因此 smoke 使用 18000；未終止或修改既有 8000 listener。

## Tool handoff

Phase 10 主要由 WebCodex 施工；stream recovery timeout 後，使用者明確要求切換 Remote Desktop Commander。切換前先核對 git status/diff 與 handoff；RDC 接手時確認 persisted-readiness optimization、schema 0008 與既有 scheduler chain 都已落檔，因此沒有重做已完成修改。Phase 11 自 migration 0009、operational monitor、介面/scheduler 接線到 closeout 全由 RDC 作為唯一 writer，沒有雙 writer。
Phase 12 repository URL/cloud-ready contract 由 WebCodex checkout 作為唯一 writer；沒有與 RDC 同時修改 D:\\sport。第一個合併 validation shell 因舊 PowerShell 不支援 `&&` 且後續整組 job timeout，改用 structured `run_process` 拆解驗證；repo-smoke 與 targeted tests 實際通過後才更新文件。
Phase 13 仍由 WebCodex 作為唯一 writer。Stream recovery polling timeout 後使用者要求從中斷處續作；session recovery 顯示 checkpoint regressions、zero-cost runtime/CLI/tests 與一次 validation 已在 timeout 期間實際完成，因此沒有重做。接續只完成未落地的 docs/CI、最終 bootstrap、publication audit 與發布收尾。

## Known external gates

- SPORTS_EDGE_THE_ODDS_API_KEY 已透過 ignored local .env 驗證可用；不得提交或回顯 secret。
- historical paid entitlement probe 回 HTTP 401；不要執行 10-credit historical odds call。
- live provider mapping 已 review：30 approved / 2 rejected / 0 pending / completion=1.0。
- current live state：44 canonical events / 642 odds snapshots / 0 completed results；最新 provider quota remaining=493 / used=7。初始 mapping validation 仍為 GREEN / mapping_rate=1.0。
- production model validation 尚未達成，正確輸出仍可為 NO_VALIDATED_EDGE。
- Public repo URL 已能在具 execution runtime 的 AI/cloud checkout 執行無 credential `sports-edge repo-smoke`；但真實 point-in-time runtime data 不在 Git，電腦關機後要持續 live collection 仍需另建 durable cloud runtime。
- 使用者要求永不付費；`zero-cost-runtime-v1` 已將 paid/automatic billing、public Git state、Actions artifact state authority、刪 evidence 換 quota 全列為 forbidden fallback。Operational checkpoint 可安全搬移完整 runtime，但目前沒有 verified free private durable backend，因此 remote live 仍 blocked。
- 台灣運彩 adapter / payout-tax version 尚無合法官方資料來源，未硬編碼猜值。
- Git identity 已以 repository-local 設定為 `fishke22 <fishke22@gmail.com>`；首次 commit 與 public push 已完成。
- 後續 GitHub 修改仍應維持 publication audit、secret/data/license gate 與 CI quality gate。

## Next action after this handoff

Forward collector + research readiness + operational monitor 的本機 hourly chain 保持不變，模型/readiness gate 不降低。下一階段只評估「真正免費且 private durable」的 checkpoint backend adapter；候選服務必須先通過 no-billing/private/atomic-or-versioned/single-writer/quota-fail-closed/export round-trip，再考慮用 ephemeral free compute 執行 restore -> secret injection -> collect/research/monitor -> verify/publish。任何條件不滿足就保持 LIVE_REMOTE_BLOCKED，不為了電腦關機仍 live 而犧牲 point-in-time state。
