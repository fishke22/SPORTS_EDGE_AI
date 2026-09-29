# Portability

`PROJECT_ROOT` 是概念；目前實作用 `SPORTS_EDGE_ROOT` 作顯式 override，並支援 `.sports-edge-root` / repository marker 自動解析。程式、SQL、設定與 scripts 不得硬編碼安裝磁碟或使用者名稱。

可攜 source artifact 包含 Python source、`pyproject.toml` + `uv.lock`、`frontend/package.json` + `package-lock.json`、資料契約、state schema、models/reports 規格與設定。`.venv`、`node_modules`、frontend `dist` 都是可重建產物，不應視為可攜 source artifact。

最低施工環境需有 Python 3.11+、uv、Node.js/npm。`scripts/bootstrap.ps1` 會：

1. `uv sync --extra dev`
2. 初始化/驗證 DuckDB migration
3. 執行 Ruff、mypy、pytest
4. `npm --prefix frontend ci`
5. 執行 frontend Vitest
6. 執行 TypeScript/Vite production build

上述 native commands 任一 exit code 非 0，bootstrap 必須立即失敗。`.venv` 若損壞可直接刪除並由 lockfile 重建；它不是 portable artifact，也不得用刪除 state/data/model 來處理環境故障。

`scripts/verify_portability.ps1` 會掃描 Python、PowerShell、SQL、tests 與 frontend source/config，拒絕硬編碼 Windows absolute path；之後執行 read-only CLI health。

每次 release 應執行 bootstrap、portability scan，並在獨立位置做 copy/bootstrap/restore smoke test。Runtime DuckDB、private reports、raw licensed data、credentials 與 build cache 不得因搬移而混入公開 source。
