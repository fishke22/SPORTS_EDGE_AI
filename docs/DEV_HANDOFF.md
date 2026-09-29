# Development Handoff

更新日期：2026-09-29

## Current state

- 第一個 NBA pregame moneyline portable vertical slice 已完成到 research / paper-only operational level。
- DuckDB schema：0009。
- Branch：main。
- Commit：尚無 commit；repository-local Git identity 已設定為 `fishke22 <fishke22@gmail.com>`。
- Public push：未執行，也未授權。
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
- docs/OPERATIONS.md、API/MCP/Provider/Data Contract/ADR/README closeout。

## Validation

- pytest：103 passed。
- persisted-readiness regression：snapshot 存在時 read facade 不重建 training dataset；無 snapshot 時 fallback live assessment；snapshot sample/status/remaining/blockers 與 ledger 一致。
- Ruff：passed。
- mypy：60 source files / 0 issues。
- frontend Vitest：2 passed。
- TypeScript/Vite production build：passed。
- npm audit：0 vulnerabilities。
- portability：passed。
- full bootstrap：passed；migration 0009 current。
- Phase 10 live smoke：readiness 0/180/360、MANUAL/SCHEDULED cycle 均 NOT_READY；model_registry/backtest_runs 維持 0。
- Phase 11 live smoke：latest operational snapshot=SCHEDULED / OK / 0 alerts；odds/result/sample delta=0；Task Scheduler Last Result=0。
- publication audit：Phase 11 staged tree 0 blockers / 0 warnings，ready_for_user_review=true；163 tracked files / git_commit_count=0。
- system doctor：DEGRADED / ready_for_research=true；schema/locks/frontend build/credential 均 OK，只有 production gate WARN。
- release bundle：builder / manifest / deterministic hash / raw-exclusion smoke 已通過；runtime ZIP 位於 ignored backups/releases。
- Windows Task Scheduler：`SPORTS_EDGE_AI Forward Collection` 已註冊，每 60 分鐘 wake；Run As fishk / Interactive-only / IgnoreNew / StartWhenAvailable / 10 分鐘 limit。Task action script 現為 collection -> research-cycle -> ops-monitor；實機 trigger 成功，collection=SCHEDULED+SKIPPED、research=SCHEDULED+NOT_READY、monitor=SCHEDULED+OK、quota 維持 493。
- localhost:8000 已有非本專案服務，因此 smoke 使用 18000；未終止或修改既有 8000 listener。

## Tool handoff

Phase 10 主要由 WebCodex 施工；stream recovery timeout 後，使用者明確要求切換 Remote Desktop Commander。切換前先核對 git status/diff 與 handoff；RDC 接手時確認 persisted-readiness optimization、schema 0008 與既有 scheduler chain 都已落檔，因此沒有重做已完成修改。Phase 11 自 migration 0009、operational monitor、介面/scheduler 接線到 closeout 全由 RDC 作為唯一 writer，沒有雙 writer。

## Known external gates

- SPORTS_EDGE_THE_ODDS_API_KEY 已透過 ignored local .env 驗證可用；不得提交或回顯 secret。
- historical paid entitlement probe 回 HTTP 401；不要執行 10-credit historical odds call。
- live provider mapping 已 review：30 approved / 2 rejected / 0 pending / completion=1.0。
- current live state：44 canonical events / 642 odds snapshots / 0 completed results；最新 provider quota remaining=493 / used=7。初始 mapping validation 仍為 GREEN / mapping_rate=1.0。
- production model validation 尚未達成，正確輸出仍可為 NO_VALIDATED_EDGE。
- 台灣運彩 adapter / payout-tax version 尚無合法官方資料來源，未硬編碼猜值。
- Git identity 已以 repository-local 設定為 `fishke22 <fishke22@gmail.com>`；首次 commit 尚未執行。
- 第一次 public push 必須取得使用者確認。

## Next action after this handoff

Forward collector + research readiness + operational monitor 已串成 hourly chain。目前 usable samples=0，readiness=NOT_READY，operational severity=OK；系統會持續累積 decision/closing odds 與 completed results，達 180 usable samples才首次自動產生 research evaluation evidence，達 360 只代表具備 200 OOS sample capacity，仍不得自動 promotion。下一步是監看第一批 completed games 到來後的 decision/closing coverage 與 usable-sample delta，若 coverage 出現缺口由 monitor WARN，而不是降低驗證門檻。Task 使用 Interactive-only token，不保存 Windows 密碼，因此登出期間不執行；登入後 StartWhenAvailable 可補啟動。若要首次 GitHub 公開，Git identity 已設定；仍須重新跑 publication audit，並由使用者確認 repo name/visibility/tracked files/license 後才 push。
