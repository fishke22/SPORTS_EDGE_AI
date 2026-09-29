# Provider Registry / Source Gate

更新日期：2026-09-28

## The Odds API — Phase 5A first real provider connector

Provider ID：`provider_the_odds_api`

Source slug：`the_odds_api`

API：v4 historical sports odds

目前 registry 狀態：`enabled=true`、`production_allowed=false`。

### 官方 evidence

- Terms and Conditions：https://the-odds-api.com/terms-and-conditions.html
- API v4 documentation：https://the-odds-api.com/liveapi/guides/v4/
- Historical odds：https://the-odds-api.com/historical-odds-data/
- Rate limit：https://the-odds-api.com/guide/rate-limit.html

2026-09-28 review 所依據的 Terms 頁面標示 last updated 2026-08-31。

### License / use gate

官方條款允許儲存資料、研究/分析 dashboard、衍生值、ML/statistical model 使用，也允許資料不是主要販售產品時的商業應用。Attribution 非強制。

禁止把 provider raw data 作為獨立 API/feed/downloadable dataset 重新包裝、轉售或再散布。因此 SPORTS_EDGE_AI：

- Bronze/raw 一律 `public_export_allowed=false`。
- 真實 provider raw payload 不得提交 Git / public repository。
- 可公開程式碼、schema、synthetic contract fixture 與不含 provider raw data 的衍生方法。
- 若未來要對外提供資料 API/feed，必須重新做 terms/license review。

### Access / quota gate

Historical odds endpoint 需要 eligible paid usage plan。API credential 必須保密。官方目前對 paid usage plan 說明的 rate limit 為 30 requests/second；connector 本身不靠近上限，也不自動 aggressive retry 429。

Credential 僅由 `SPORTS_EDGE_THE_ODDS_API_KEY` 環境設定讀取；CLI 不接受 `--api-key`，避免 key 出現在 shell history。HTTP error 會做 sanitized error mapping，不回傳含 key 的 request URL。

### Point-in-time semantics

Historical endpoint 對 `date` 回傳「最接近且小於等於 requested timestamp」的 snapshot。Featured-market historical data 自 2020-06-06 起提供；2022-09 起 snapshots 為 5-minute intervals（實際 coverage 仍依 sport/bookmaker/market 加入時間而異）。

Normalization 採較保守的時間：

- envelope `timestamp` 必須 `<= requested_at`，否則 hard fail。
- bookmaker/market `last_update` 若存在也必須 `<= requested_at`。
- odds `observed_at = max(snapshot timestamp, market/bookmaker last_update)`，防止把較晚 market update 提前暴露。
- Phase 5A 只接 NBA pregame `h2h` / decimal odds；pregame 判斷使用 `commence_time > requested_at`，不能用較早 snapshot timestamp 代替 decision time。已開始事件不進此 pipeline。

### Entity mapping gate

The Odds API 事件以 team name 表示參與者。SPORTS_EDGE_AI 不會自動把 provider name 當 canonical identity。

若 `provider_entity_mapping` 缺 team mapping：

- Bronze 仍保留。
- Data Quality = `RED`。
- `mapping_rate` 依已解析 team 比例計算。
- 不寫 canonical events/markets/odds。

只有 mapping 完整後才可進 Silver/DuckDB canonical layer。

### 本輪 live validation 狀態

施工機目前沒有設定 `SPORTS_EDGE_THE_ODDS_API_KEY`，因此沒有執行真實付費 historical API call，也沒有驗證目前帳號 historical entitlement。這就是 `production_allowed=false` 保持不變的原因。

Contract tests 使用專案自製 `fixtures/synthetic/the_odds_api_historical_contract.json`，只模擬 provider schema，不包含第三方真實 raw data。


## Phase 5B — free-plan operational path

為了在沒有 historical entitlement 時仍能完成合法營運施工，新增 current NBA h2h、participants
與 scores connector。這些 endpoint 仍使用同一 credential、immutable Bronze、quota header parser、
sanitized HTTP error 與 local monthly credit budget。

Local default budget 為 450 credits，目的在 provider quota 內保留緩衝；它不是 provider 官方方案額度
的重新定義。每次 response 的 remaining/used/last-cost 會寫入 provider_usage_snapshots。

### Manual entity mapping proposal/review

Participants 只產生 PENDING proposal，不做 fuzzy auto-approval。正式 provider_entity_mapping 只有在
人工 approve 後才寫入；reject 會移除既有 mapping 並留下 review note。API/MCP 可 read proposal、
canonical candidates、summary，但 mutation 只留 CLI。

正式 NBA mapping candidate 使用 entity_id_prefix=NBA_，避免 synthetic TEAM entity 混入人工審核清單。

### Current odds

Current NBA h2h 在 mapping 完整時走 Bronze → canonical event/market/odds；mapping 不完整時仍保留
Bronze/Data Quality evidence，但 canonicalization fail closed。Provider usage 同步記錄。

### Scores / result provenance

Scores 會保存 provider event id、scores、completed flag、observed/provider timestamp、raw source ref
與 payload hash。若 provider event 尚無 canonical event mapping，result 可先保留 provenance 並標示
unresolved；不得猜 event identity。

Local NBA Elo/rest feature 只採 decision time 前已觀測到 completed result 的 NBA games。取消、
未完成或當時未知結果的 scheduled event 不得影響 rating/rest history。

### Production gate

Free-plan connector contract 與 free endpoint live validation 已完成，但 historical paid entitlement probe 回 HTTP 401，
因此 provider_registry.production_allowed 維持 false。

### 2026-09-28 live validation evidence

- Credential 已透過本機 ignored .env 成功載入；secret 未回顯、未提交 Git。
- NBA participants live call 成功：quota remaining=499 / used=1 / last=1。
- Provider participants 共 32：30 個正式 NBA franchise mapping 已 review APPROVED；Golden State Warriors Blue / Gold 不在 NBA 官方 30 隊名單，REJECTED。
- Los Angeles Clippers 以人工 alias review 對應 canonical LA Clippers / NBA_LAC；其餘 29 隊為 exact-name mapping。
- Mapping summary：32 proposals、30 approved、2 rejected、0 pending、completion=1.0。
- Current NBA h2h live call 成功：41 events、212 odds snapshots、Data Quality GREEN、mapping_rate=1.0、unresolved_entities=0；quota remaining=498 / used=2 / last=1。
- NBA scores days_from=3 live call 成功但目前回 0 results；quota remaining=496 / used=4 / last=2。
- Historical events entitlement probe 回 HTTP 401；同一 credential 已通過 free endpoints，因此 historical paid entitlement 未通過，本輪未執行 10-credit historical odds call。
- 真實 current event as-of market baseline 成功：5 bookmakers / 10 selection records，每家 de-vig fair probability sum=1.0，且 max_input_observed_at <= decision_as_of。
- Local NBA research 因 completed result samples=0 正確回 INSUFFICIENT_DATA；不產生 evaluation / validation，也不提升 model gate。

### Forward collection cadence

Migration 0007 之後，free-provider production of research evidence 改由 one-shot forward collector 持續累積。
預設 current h2h 最短間隔 180 分鐘；scores 最短 720 分鐘，但 scores 還必須存在 scheduled_start 已過且
尚無 completed result 的 canonical event 才會 due。External scheduler 可以更頻繁喚醒；fresh run 會記
SKIPPED 且不送 provider request。

依 The Odds API v4 quota contract，1 region × 1 h2h market 的 current odds 成本通常為 1 credit；
scores 帶 daysFrom 時為 2 credits。Local monthly budget 450 仍是 hard stop，provider response headers
是 requests_used / remaining / last-cost 的實際來源。Error ledger 會再以目前 API key 字串做 redaction。
