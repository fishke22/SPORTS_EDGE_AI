# Public GitHub Publication Checklist

更新日期：2026-09-28

第一次 public push 前必須停止並由使用者確認 repository name、visibility、tracked files、license
與 audit 結果。Audit 通過不等於已授權 public push。

## Automated gate

~~~powershell
uv run python scripts\publication_audit.py --write-report
npm --prefix frontend audit
git diff --check
uv run sports-edge build-release
~~~

Publication audit blocker：

- tracked .env / non-empty secret-like assignment / credential token pattern
- tracked Bronze/Silver/Gold runtime data
- tracked production DuckDB/state、model artifact、report、backup、logs
- tracked file > 5 MiB
- machine-specific Windows absolute path
- 缺少 `.github/workflows/ci.yml` 或 external GitHub Action 未 pin 到完整 40-character commit SHA
- 缺少 LICENSE / README / DATA_POLICY / SECURITY / THIRD_PARTY_NOTICES / 本 checklist

Dependency license metadata 的 UNKNOWN / copyleft detection 目前列 WARNING，必須人工複核，
不自動宣告 license compatibility。

## Manual gate

- 確認 provider raw payload、付費/受限資料未進 Git。
- 確認 synthetic contract fixture 為 project-authored，不含第三方真實 raw bytes。
- 確認 .env.example 無真實 credential。
- 確認 git history secret scan；若目前沒有 commit，需在第一次 commit 後、public push 前再跑一次。
- 確認 third-party notices 與 dependency licenses。
- 確認 repository 名稱與 public visibility。
- 使用者明確確認第一次 public push。

目前狀態：首次 commit 後已重新執行 automated publication audit，Git history scan 為 0 blockers / 0 warnings；
使用者已明確授權首次公開發布，`fishke22/SPORTS_EDGE_AI` 已以 Public / `main` 完成首次 push。
實際 audit JSON 可寫入 reports/audits/publication_audit.json（runtime report，不提交 Git）。
