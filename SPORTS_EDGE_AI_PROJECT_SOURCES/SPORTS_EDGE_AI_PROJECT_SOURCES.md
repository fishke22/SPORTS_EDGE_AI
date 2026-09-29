---
title: "SPORTS_EDGE_AI 專案來源總綱（施工版）"
version: "0.1.0-reconstructed"
date: "2026-09-28"
language: "zh-TW"
status: "由 2026-09-27 Project source 合併規格重建之施工契約"
---

# SPORTS_EDGE_AI 專案來源總綱

> 本檔供後續施工 Agent 在本機快速恢復工程契約。它依據 ChatGPT Project 中的
> `deep-research-report (3).md` 與較新的 `deep-research-report (4).md` 整理；
> 若未來取得原始單獨交付的 canonical `SPORTS_EDGE_AI_PROJECT_SOURCES.md`，
> 應先驗證 checksum，再以原始檔取代本施工版，不得無證據宣稱 byte-for-byte 相同。

## 1. 定位

SPORTS_EDGE_AI 是 Sports Quant Research Platform，不是猜球神器。核心是 point-in-time data、
market probability、calibrated model probability、fair odds、edge、gross/net EV、uncertainty、
data quality、CLV 與 risk。資料或證據不足時，`NO BET` / `NO_VALIDATED_EDGE` 是正確輸出。

## 2. Portable-first

目前工作位置可以是任何磁碟。業務程式、SQL、config、scripts 不得依賴固定安裝位置、使用者名稱、
Python 或 Node 絕對路徑。Root resolver：`SPORTS_EDGE_ROOT` 明確 override → repository marker →
package-relative search → 無法解析則明確報錯。

Portable profile：Python + uv + DuckDB + Parquet + Polars + Pydantic/Pandera + pytest。
PostgreSQL/TimescaleDB、Prefect、MLflow、Redis、Docker Compose 只可作 optional server profile。

## 3. Single-core / multi-interface

Standalone CLI、FastAPI REST、React Web UI、MCP Server 必須共用同一套 domain/application services。
禁止在 route、MCP tool、React component 或 CLI handler 重算 EV、風控或模型邏輯。

## 4. Data lake 與時間語意

固定 `data/bronze -> data/silver -> data/gold`。Bronze 優先 immutable；Silver canonical；
Gold feature/model-ready。State、models、reports、logs、backups 都以 PROJECT_ROOT 為基準。

重要資料至少區分 event/provider/source time、observed_at、ingested_at、effective_at、decision_as_of。
回測硬限制是任何輸入都不得晚於 decision_as_of；historical truth 不等於 historical knowledge。

## 5. Canonical contracts

至少版本化：event、market、odds snapshot、prediction、model registry、backtest、paper trading、
settlement、risk、data quality、provider/license registry。Odds snapshot 不 overwrite。
原始資料 reference 只保存相對路徑與 hash/provenance。

## 6. Model / backtest

Market-implied/de-vig probability 是必要 baseline。新模型逐步採 Elo/Glicko、Poisson/Dixon-Coles、
Logistic、Gradient Boosting、Bayesian 與 sport-specific simulation；只有 OOS 與 calibration 證據較好才晉級。

禁止 temporal random shuffle、future leakage、closing odds 回填、最終傷兵狀態回填。
使用 walk-forward / rolling / expanding validation。至少評估 sample count、Brier、LogLoss、ECE、
ROI/Yield、CLV、Max Drawdown、bootstrap CI、risk of ruin、model stability。

## 7. Risk

Risk Engine 可 veto 模型訊號。禁止 Martingale、追損、保證收益。正 EV 不等於已驗證 edge；
模型未通過 gate 時應回傳 `NO_VALIDATED_EDGE`。預設 paper-only，不實作自動下注。

## 8. First vertical slice

一次只完成一個 sport 的端到端流程。第一個 slice 先以 NBA pregame moneyline + synthetic fixture /
合法 global market baseline 建立 raw → bronze → normalize → silver → feature → market baseline →
model probability → calibration → pricing → risk → backtest → CLI/API/Web/MCP；台灣運彩 adapter
在合法資料存取方式確認後接入。

## 9. MCP / API / UI

MCP 預設 read-only，薄封裝 application services；正式施工時必須依官方 Python SDK 當期 stable
版本 pin major/version，不得照舊文章猜 API。受限 `run_backtest` 必須限制日期、資料量、CPU/runtime、
輸出與 concurrency。Web UI 要能清楚顯示沒有優勢、資料不足與風險，不得使用穩贏/必中等語言。

## 10. GitHub publication

公開前必做 secret/license/data/large-file/history/dependency audit。不得公開 API key、token、cookie、
私人投注資料、production DB、backup、付費/禁止再散布 raw data。README/docs 以繁體中文為主，
程式 identifier 使用英文。第一次真正 public push 前必須交由使用者確認一次。

## 11. Agent workflow

開工先讀 `AGENTS.md`、README、本檔、IMPLEMENTATION_STATUS、DEV_HANDOFF、DECISIONS、git status/diff。
WebCodex 優先；無法存取才切 Remote Desktop Commander；同一工作樹同一時間只允許一個 writer。
每個 phase：inspect → plan → modify → tests → lint/type → diff → hygiene → 更新施工文件 → handoff。
