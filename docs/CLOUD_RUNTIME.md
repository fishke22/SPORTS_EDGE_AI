# Cloud / AI Runtime Contract

更新日期：2026-09-29

本文件定義「只把公開 GitHub repository URL 交給 AI」時，SPORTS_EDGE_AI 可以與不可以保證的範圍。
原則是 **不為了雲端化而降低 point-in-time、持久性、secret 或模型驗證標準**。

## 1. Repo URL-only：可行的範圍

若 AI 本身具備一般程式執行環境（可存取 GitHub、Git、Python 3.11+、uv，並允許建立暫存檔），
它可以只依公開 repository URL clone 專案並執行完全離線、無 credential 的 smoke：

~~~bash
git clone https://github.com/fishke22/SPORTS_EDGE_AI.git
cd SPORTS_EDGE_AI
uv sync --frozen
uv run sports-edge repo-smoke
~~~

repo-smoke：

- 不呼叫 The Odds API 或其他網路 provider。
- 不讀取或要求 .env / API key。
- 在 OS 暫存目錄建立獨立 PROJECT_ROOT，複製 tracked SQL migrations。
- 依序 ingest 兩個 tracked synthetic snapshots。
- 以 2026-10-01T08:30:00Z 建立 as-of market baseline，明確驗證 09:00Z future snapshot 沒有 leakage。
- 走正式 shared Market Analysis Service，而不是另外重寫一套 demo 邏輯。
- 固定 model_validated=false，因此即使 synthetic model probability 產生正 EV，也不得輸出 EDGE。
- 執行完成後刪除暫存 state；不碰 clone 本身的 data/、state/、models/、reports/。

這代表「repo URL → clone → 重建程式 → 執行可驗證的離線分析」是可行的。
它不代表 repo 本身包含真實盤口歷史或 validated model evidence。

若 AI 只能閱讀網頁、不能執行 shell/程式碼，單一 repository URL 本身不能讓它真正執行分析。

## 2. Repo URL-only：不可取代的資料

公開 Git repository 故意不包含：

- The Odds API credential。
- runtime DuckDB。
- Bronze/Silver/Gold 真實資料。
- private reports / model artifacts / backups。
- 持續累積的 decision-time / closing odds 與 completed-result evidence。

因此只給 repo URL 的新 AI instance **無法重建從未提交到 Git 的真實 point-in-time 歷史**。
如果硬把這些 runtime/raw 資料提交到 public Git，會破壞資料授權、secret hygiene、repository 體積與操作安全，
所以本專案禁止用這種方式換取表面上的「零設定雲端化」。

## 3. 真實 live analysis：需要遠端 runtime

要在個人電腦關機時仍持續收集並分析真實資料，至少需要：

1. 遠端 compute：VM、container host 或其他可排程執行 Python 的 runtime。
2. durable storage：持久磁碟/volume，保存 data/、state/，必要時包含 models/、reports/。
3. secret manager / environment injection：把 SPORTS_EDGE_THE_ODDS_API_KEY 放在 runtime secret，不放 Git。
4. scheduler：定期呼叫既有 one-shot collect-forward -> research-cycle -> ops-monitor。
5. 單一 writer 或明確 database concurrency 策略；portable DuckDB profile 不應讓多個 ephemeral runner 同時寫同一 state。
6. 版本固定：部署應 pin Git tag/commit；升級前仍跑 CI/publication/portability gate。

目前程式已把 collector 設計成 one-shot application service，因此 scheduler 可從 Windows Task Scheduler
替換成遠端 cron/container scheduler，而不需改寫 domain logic。

## 4. 為什麼不把 GitHub Actions 當正式 collector

GitHub Actions 適合：

- CI。
- repo-smoke。
- publication audit。
- release bundle。
- 人工 workflow_dispatch 的短期、可丟棄研究工作。

GitHub Actions **不作為目前 portable profile 的正式長期資料收集/state authority**，原因包括：

- runner filesystem 是 ephemeral。
- artifact/cache 不等同 transactional durable database。
- scheduled workflow 不是 point-in-time ingestion 的持久 storage contract。
- 多 run 可能造成 writer/concurrency 問題。
- secret 與 public/fork execution context 需要額外治理。
- 把 DuckDB/真實 raw history 當 workflow artifact 傳來傳去，會讓 provenance、atomicity、成本與故障恢復變差。

因此「不上個人電腦」的正確下一步是 **遠端持久 runtime**，不是強迫 GitHub Actions 扮演資料庫。

## 5. 建議的演進順序

目前先維持：

- GitHub：公開 source + CI + release + offline repo smoke。
- 本機：現有 forward collector 繼續累積真實 evidence。
- 模型：資料不足維持 NOT_READY / NO_VALIDATED_EDGE。

等需要真正脫離個人電腦時，再建立 optional cloud profile：

- clone/pull 指定 tag。
- persistent volume 掛載 operational directories。
- secret injection。
- one-shot scheduler。
- API/MCP read surface。
- backup/restore 與 health monitoring。

在沒有選定遠端平台、持久儲存與費用方案前，不先加入會降低資料品質的 workaround。
