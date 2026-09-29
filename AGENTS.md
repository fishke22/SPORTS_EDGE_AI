# AGENTS.md

所有 Agent 開工前必須讀取：

1. `SPORTS_EDGE_AI_PROJECT_SOURCES/SPORTS_EDGE_AI_PROJECT_SOURCES.md`
2. `README.md`
3. `docs/IMPLEMENTATION_STATUS.md`
4. `docs/DEV_HANDOFF.md`
5. `docs/DECISIONS.md`
6. `git status` 與 `git diff`

施工原則：WebCodex 優先；只有不可用時才切 Remote Desktop Commander。同一工作樹不得由兩個工具
同時修改。核心 domain/application layer 必須由 CLI、API、Web、MCP 共用。回測必須 point-in-time，
不得 temporal random shuffle 或 future leakage。資料品質或證據不足時，合法結果是 `NO_BET` 或
`NO_VALIDATED_EDGE`。禁止 Martingale、追損、保證獲利與預設自動下注。

每次 phase 完成後執行 tests、lint/type check（若配置）、diff review、workspace hygiene，並更新
`IMPLEMENTATION_STATUS.md`、`DEV_HANDOFF.md`、`DECISIONS.md`、`CHANGELOG.md`。
