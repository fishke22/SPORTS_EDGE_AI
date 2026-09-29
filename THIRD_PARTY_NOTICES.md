# Third-Party Notices

SPORTS_EDGE_AI 原創程式碼目前採 Apache-2.0。Python dependencies 由 `pyproject.toml` / `uv.lock` 鎖定；
正式公開 release 前必須執行 dependency/license audit 並在此補上必要 notices。

本 repository 不宣稱任何第三方 sports/odds data 受 Apache-2.0 授權。The Odds API、Sportradar、
StatsBomb、台灣運彩或其他 provider 的資料權利均依其各自條款處理。

Phase 4 新增 MCP Python SDK、FastAPI/Uvicorn 與 React/TypeScript/Vite/ECharts 前端依賴；精確版本以 `uv.lock` 與 `frontend/package-lock.json` 為準。此處只記錄依賴範圍，不視為已完成 license clearance；第一次公開 push 前仍必須執行 dependency/license audit 並補齊必要 notices。
