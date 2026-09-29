# Model Validation

任何模型先與 market-implied/de-vig baseline 比較。禁止 temporal random shuffle；使用 walk-forward、
rolling/expanding window 與 rolling retraining。Base model training、calibration、final test 必須時間隔離。

正式 gate 至少評估 sample count、Brier、LogLoss、ECE/calibration、ROI/Yield、CLV、Max Drawdown、
bootstrap confidence interval、risk of ruin、model stability。未通過 gate 的正確狀態是
`NO_VALIDATED_EDGE`，不得為了產生推薦降低門檻。

## Walk-Forward Scaffold

已建立 expanding-window scaffold：輸入 timestamp 必須 timezone-aware 且 strictly increasing；每一 fold 都要求 `train_end < test_start`，不提供 random shuffle 路徑。這只是時間切分與 leakage guard，尚未代表模型通過驗證。

目前 scaffold 的 `validated_edge=false` 且 recommendation 固定為 `NO_VALIDATED_EDGE`。只有在後續 sport-specific model 完成 out-of-sample probability metrics、calibration 與風險/績效 gate 後，才可改變此狀態。

## Recommendation Gate

Market Analysis Service 已可計算模型 probability 對 listed odds 的 gross/net EV，但 `is_model_validated` 仍是獨立 gate。正 Net EV 不會自動晉升為 EDGE；未完成 OOS/calibration 驗證時必須保持 `NO_VALIDATED_EDGE`。Data Quality RED、非正 Net EV 與 data conflict 仍可覆蓋模型訊號。


## NBA V1 Research Baseline

第一個 sport-specific baseline 為可解釋 logistic model。輸入只含 rating difference、rest difference 與 home-court indicator；不使用 closing odds、賽果、未來 injury/status 或任何晚於 `decision_as_of` 的資料。

Walk-forward 每個 fold 重新 fit model。除了 train/test decision time 分離外，training sample 的 `result_observed_at` 必須不晚於該 fold 的 test start，確保當時真的已可取得 label。Test fold 不允許 overlap。

### 指標定義

- Brier / LogLoss / ECE：同時對 model probability 與 decision-time de-vig market baseline 計算。
- ROI：unit-stake backtest total PnL / configured starting bankroll。
- Yield：unit-stake total PnL / bet count；在目前每筆 stake 固定為 1 的 evaluator 中等同 PnL / total staked。
- CLV：selected offered decimal odds / corresponding closing decimal odds - 1。
- Max Drawdown：starting bankroll equity curve 的 peak-to-trough 比例。
- Bootstrap CI：以已下注樣本回報做 deterministic bootstrap 的 per-bet yield confidence interval。
- Risk of ruin：相同有限 test horizon、相同 starting bankroll 下的 bootstrap ruin fraction；不是無限期破產機率。

Synthetic samples 的任何漂亮結果都不構成 edge 證據。目前 `WalkForwardEvaluationRecord.is_model_validated=false` 且 recommendation 固定 `NO_VALIDATED_EDGE`。下一階段必須建立獨立 time-separated calibration 與正式 validation gate。

## Time-Separated Calibration 與 Validation Gate

Platt calibration 不得使用 validation/test window 的 outcomes。Base-training outcomes 必須先完成，再進入 calibration window；calibration outcomes 全部可知後的 `fitted_at` 才是該 calibrator 最早可使用時點。Walk-forward 啟用 calibration 時，每個 fold 都獨立切分 base-train → calibration → test。

第一版 research validation policy 是工程 gate，不是保證收益標準。它同時檢查：
- sample / bet count
- model 相對 market baseline 的 Brier、LogLoss、ECE
- Yield、CLV、Max Drawdown
- bootstrap yield CI low
- finite-horizon risk of ruin
- evidence tier

目前 `SYNTHETIC` evidence 永遠不能使 model validated。即使所有數值 threshold 都通過，仍必須有允許的 point-in-time evidence tier。Validation gate 成功也只代表 model/version 通過 policy，不代表任何特定事件存在 EDGE。

## Research Readiness Gate

`nba-readiness-v1` 不另創一套模型門檻，而是從目前正式 research config 與 `nba-research-gate-v1` 推導執行條件：

- decision horizon = 6 小時
- minimum training = 160 samples
- test fold = 20 samples，non-overlap
- calibration window = 20 samples
- 第一個可執行 fold：160 + 20 = 180 usable samples
- validation policy minimum OOS sample_count = 200；以 20-sample folds 計，需要 10 folds，因此 minimum usable capacity = 160 + 200 = 360

180 表示「可以開始產生 research OOS evidence」，360 表示「sample_count gate 理論上可滿足」；兩者都不是 validated。Bet count 與所有 probability/calibration/performance/risk thresholds 仍由 validation policy 決定。

Readiness preflight 對每個 complete fold檢查：test start 前是否已有至少 160 個 settled training labels、base training 是否同時包含兩個 outcome classes、calibration window 是否同時包含兩個 classes、training outcomes 是否早於 calibration start、calibration outcomes 是否早於 test start。任何一項不滿足都回 NOT_READY，而不是讓 evaluator 在排程背景中嘗試使用未來 label。

Dataset 另追蹤 decision-time / closing odds coverage。只有同一 event 能在 6 小時 decision horizon 與賽前 closing cut 同時形成完整 HOME/AWAY moneyline pair，且 feature construction 成功，才成為 usable training sample。

Automatic cycle 只產生研究 evidence。即使 `EVALUATED_GATE_PASSED`，`model_promotion_performed` 固定為 false，且不寫 `model_registry`。Promotion 必須走顯式 model lifecycle /人工 review；單場 recommendation 仍由 Market Analysis + Risk Gate 決定。
