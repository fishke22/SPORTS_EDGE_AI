# Data Policy

本 repository 預設只允許提交原創程式碼、schemas、文件、migration、synthetic/sample fixtures 與可合法再散布的最小資料。
真實 provider raw payload、付費 odds、私人投注紀錄、production database、backups、credentials 與禁止再散布資料不得提交。

任何 provider 接入前都必須在 source/license registry 記錄來源條款、商業使用、再散布、自動化存取、attribution、
review date 與證據 reference。Code license 不會重新授權第三方 data。

## The Odds API

Phase 5A provider review 記錄於 `docs/PROVIDERS.md` 與 migration `0005`。The Odds API 真實 raw payload 可作本機研究保存，但不得提交 Git 或作 standalone raw data feed/downloadable dataset 對外再散布；`public_export_allowed` 固定 false。

Public repository 可包含 connector source、schema、source/license metadata、derived methodology 與專案自製 synthetic contract fixture。任何真實 provider payload、API key、quota/account details 或授權不明資料都不得提交。
