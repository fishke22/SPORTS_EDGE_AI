# Security

請勿提交 API key、token、cookie、帳密、provider contract、私人投注紀錄、production database、raw backup 或敏感 log。
`.env` 與 secrets 預設被 Git 忽略；公開前仍必須掃描 working tree 與 Git history，不能只依賴 `.gitignore`。

若發現 secret 曾進入 history，應視為可能外洩：先停止公開流程，再移除歷史內容並 rotate/revoke credential。
