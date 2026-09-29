# Contributing

所有變更應維持 portable-first、point-in-time、single-core/multi-interface 與 risk-veto 原則。
修改 schema、migration、pricing、risk、backtest 或 provider adapter 時必須補測試與文件。

提交前至少執行：
`uv run pytest`、`uv run ruff check .`、`uv run mypy src`、`scripts/verify_portability.ps1`。
不得為了讓測試通過而移除重要驗證或降低門檻。
