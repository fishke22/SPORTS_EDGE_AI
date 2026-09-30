# Zero-Cost Durable Backend Candidate Assessment

更新日期：2026-09-30

本文件是 Phase 15 的只讀候選調查結果。目的不是選「最便宜」服務，而是找出是否有後端能同時符合 SPORTS_EDGE_AI 的 hard policy：

- 永不付費；不得 automatic billing。
- private durable storage。
- atomic/versioned publish。
- single-writer / CAS。
- quota failure 必須 fail closed。
- secret 與 checkpoint 分離。
- checkpoint 可匯出搬家。
- 不得為了免費額度刪除 point-in-time evidence。

所有結論都只代表 2026-09-30 公開文件狀態；未做真實帳號 round-trip 前不得解除 `LIVE_REMOTE_BLOCKED`。

## 結論摘要

### Backblaze B2 — CONDITIONAL CANDIDATE

目前最值得進入下一輪實測，但**尚未 APPROVED**。

公開文件支持：

- B2 前 10 GB 儲存免費。
- 官方說明可在不提供 billing method 的情況下開始使用。
- Bucket 可設為 private。
- B2 buckets 預設保留版本。
- Native API 的 bucket `revision` + `b2_update_bucket.ifRevisionIs` 可作 CAS，衝突回 409。
- 非付費帳號有 daily transaction caps；超過會回 403，而不是要求程式自動付費。
- Application key 可限制 buckets/capabilities/prefix。

主要 blocker：

- Backblaze 同時明確說明：若沒有設定 data caps，usage 可無上限且可能累積費用。
- 公開文件沒有證明「data cap 可以可靠設成精確 $0」；只說可輸入每日 dollar amount。
- 因此在真實帳號內確認「無付款方式 + hard caps + private bucket + scoped key」之前，不能把 `automatic_billing_possible` 判為 false。
- Cloud Replication 另有 payment-history 要求，不屬本專案 zero-cost path，禁止啟用。

若進 Phase 16，預定設計：
1. Immutable checkpoint object 用 B2 file version/content hash。
2. Current pointer 放 bucketInfo。
3. 以 bucket revision + `ifRevisionIs` 做 CAS。
4. Application key 僅授權單一 private bucket 的必要 read/writeBuckets/read/writeFiles 能力。
5. 程式另做 10 GB / transaction free-quota preflight，接近門檻就停止 publish。
6. 任一 403 cap、409 conflict、quota、auth 或 checksum error 都 fail closed。
7. 不設定 lifecycle 自動刪除 point-in-time checkpoint；若容量接近免費上限，停止 collection 並要求人工搬移/封存，不刪歷史換空間。

官方來源：
- https://www.backblaze.com/cloud-storage/pricing
- https://help.backblaze.com/hc/en-us/
- https://www.backblaze.com/docs/cloud-storage-buckets
- https://www.backblaze.com/apidocs/b2-update-bucket
- https://www.backblaze.com/apidocs/b2-create-key
- https://www.backblaze.com/docs/cloud-storage-data-caps-and-alerts
- https://www.backblaze.com/docs/cloud-storage-create-and-manage-caps-and-alerts

## Supabase Free — CONDITIONAL SECONDARY / NOT PRIMARY

優點：
- Free plan 為 $0。
- Storage Free quota 目前 1 GB，Free plan over-usage 欄位沒有付費 overage。
- 可用 Postgres row transaction 作 pointer/CAS 類控制，Storage bucket 可 private。

不適合作 primary checkpoint authority 的原因：
- Free project 低活動約 7 天可能 auto-pause。
- Storage quota 只有 1 GB，明顯小於 B2 10 GB。
- Free project 沒有付費級 automatic backups / PITR。
- 暫停後 remote scheduler 可能無法即時 restore/publish。

可保留作未來 metadata/control-plane 候選，但目前不作主 checkpoint store。

官方來源：
- https://supabase.com/pricing
- https://supabase.com/docs/guides/storage/pricing
- https://supabase.com/docs/guides/platform/free-project-pausing
- https://supabase.com/docs/guides/platform/billing-on-supabase

## Cloudflare R2 — REJECT FOR HARD ZERO-COST POLICY

R2 有每月免費額度（10 GB-month、Class A/B free operations），但官方 Get Started 明確要求完成 R2 subscription checkout，定價文件也說超出免費額度後依 storage/operations 月結計費。

因此它不符合本專案「不得 automatic billing / 永不付費」的 hard requirement。

官方來源：
- https://developers.cloudflare.com/r2/get-started/
- https://developers.cloudflare.com/r2/pricing/

## Google Drive API — REJECT FOR LONG-TERM HARD ZERO-COST POLICY

Google Drive API 目前標準使用在每日 threshold 內不額外收費，但官方已公告 2026-05-01 後的新 quota model，並寫明超過 daily threshold 的收費預計在 2026 年稍後導入，而且會連到 Google Cloud billing account。

這種即將改變的計費契約不適合當「永不付費」state authority。

官方來源：
- https://developers.google.com/workspace/drive/api/guides/limits

## Dropbox Basic — REJECT AS STATE AUTHORITY

Dropbox Basic 有 2 GB 免費空間，API 的 update write mode + rev 可做到 CAS 類更新；但 Dropbox 官方同時說明部分 Basic 帳號若長期超過 quota，除了功能限制外，Dropbox **可能刪除帳號擁有的檔案**。

這違反「quota failure 不得以刪除 point-in-time evidence 解決」的 hard policy，因此不作 authoritative checkpoint backend。

官方來源：
- https://help.dropbox.com/storage-space/over-quota
- https://dropbox.github.io/dropbox-sdk-js/global.html

## GitHub Actions — APPROVED FOR EPHEMERAL COMPUTE ONLY

GitHub 官方目前說 public repository 使用 standard GitHub-hosted runners 免費且不限量。這使 public `fishke22/SPORTS_EDGE_AI` 可作免費 ephemeral scheduler/compute 候選。

但 runner filesystem 是 ephemeral，Actions artifact/cache 不得升格成 state authority。因此 Phase 16 若 Backblaze 真實驗證通過，可能的 zero-cost topology 是：

`GitHub Actions standard runner -> B2 private checkpoint restore -> secret injection -> one-shot collect/research/monitor -> B2 CAS publish`

GitHub Actions 只負責 compute，不保存 authoritative operational state。

官方來源：
- https://docs.github.com/en/actions/reference/runners/github-hosted-runners
- https://docs.github.com/en/actions/concepts/billing-and-usage

## Phase 15 Gate

目前唯一進入下一輪的候選是 **Backblaze B2 / CONDITIONAL**。

`LIVE_REMOTE_BLOCKED` 必須維持，直到 Phase 16 用真實免費帳號完成：

- no-payment-method / billing safety 人工確認；
- data cap 可設定且足以保證 $0 的確認；
- private bucket；
- scoped application key；
- upload/download/checksum；
- bucket revision CAS conflict；
- transaction/download cap fail-closed；
- clean-runtime restore；
- old checkpoint preservation；
- GitHub Actions secret injection smoke。

若其中任何一項無法證明，Backblaze 也淘汰，cloud live 施工線停止；本機 live + repo smoke + private checkpoint 繼續維持。
