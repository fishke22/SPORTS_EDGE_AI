# Changelog

## [Unreleased]

### Added
- Added `sports-edge repo-smoke`, an offline/credential-free ephemeral repository smoke that proves migrations, point-in-time as-of isolation, shared market analysis, and fail-closed `NO_VALIDATED_EDGE` behavior from a public checkout.
- Added `docs/CLOUD_RUNTIME.md` defining the repo URL-only execution contract and the durable compute/storage/secret requirements for true computer-independent live collection.
- GitHub Actions Python matrix now executes the repository smoke on Windows/Linux and Python 3.11/3.14; Actions remains CI/ephemeral and is not promoted to operational state authority.
- Added a hard fail-closed zero-cost runtime policy: paid services and automatic billing are forbidden, public Git/Actions artifacts cannot be operational state authority, and remote live collection remains blocked until a free private durable backend passes capability checks.
- Added private full operational checkpoints for Bronze/Silver/Gold, DuckDB state, models, and reports with per-file hashes/sizes, configured-secret leakage detection, atomic archive publication, strict path validation, empty-target restore, migration integrity checks, and rollback on restore failure.
- GitHub Actions now exercises operational-checkpoint creation and zero-cost policy status on the cross-platform Python matrix without promoting CI artifacts to durable state.
- Pinned Linux CI jobs to `ubuntu-24.04` after GitHub announced the `ubuntu-latest` image migration to Ubuntu 26, avoiding unreviewed runner-image drift in the quality gate.
- Added `zero-cost-checkpoint-backend-v1`, a provider-neutral checkpoint storage protocol/capability evaluator plus a local reference adapter with content-addressed versions, atomic pointer updates, compare-and-swap generation checks, exclusive writer locking, quota fail-closed behavior, verified export, and full restore round-trip smoke.
- Added stale-generation, concurrent-writer, quota-preserves-history, capability-gate, round-trip, CLI, and CI regressions; the local reference adapter is explicitly never remote-live eligible.
- Added Phase 15 zero-cost backend candidate assessment. Backblaze B2 is documented as conditional-only pending real-account no-payment/data-cap/private/scoped-key round-trip evidence; Supabase remains secondary-only, while R2, Google Drive, and Dropbox Basic are rejected for the hard zero-cost state-authority role under current public terms.
- Added Phase 16A Backblaze B2 Native API safety preflight and checkpoint adapter contract: offline-by-default status, two-key least-privilege model, private/lifecycle/replication checks, immutable upload + bucket-revision CAS pointer, 403 quota and 409 conflict fail-closed handling, checksum verification, and conservative 250 MB checkpoint limit. Real account cap evidence confirms $0 storage/download and transaction caps, while no-payment-method and live round-trip gates remain unresolved.
- Added Phase 16B Backblaze live qualification tooling: explicit-confirmation, empty-bucket-only synthetic checkpoint upload/fetch/restore, current-pointer verification, provider stale-revision CAS conflict probe, same-account/account-wide pointer-key gates, and B2 credential leakage scanning in operational checkpoints. User-confirmed no-payment evidence now completes the manual billing-safety gate; real bucket/key/provider round-trip remains pending.

### Fixed
- Normalized ANSI styling in the new `b2-live-roundtrip` explicit-confirmation CLI regression. The first Phase 16B clean GitHub run exposed the same Rich/Typer terminal-color portability issue previously fixed for another safety-message test; command behavior and confirmation requirements are unchanged.

## [0.1.1] - 2026-09-29

### Security
- Upgraded the development/test dependency to `pytest>=9.0.3,<10`; `uv.lock` resolves pytest 9.1.1, addressing the GitHub Dependabot medium-severity tmpdir handling advisory reported against pytest < 9.0.3.
- Normalized ANSI styling in the CLI `--force` safety-message regression so clean GitHub Actions runners verify the actual error text rather than terminal color encoding.
- Full Python regression remains green on pytest 9.1.1: 103 passed; Ruff and mypy also pass.

### Fixed
- `scripts/bootstrap.ps1` now checks every native `uv`/`npm` command exit code and fails immediately, preventing a broken local environment from being reported as a successful bootstrap.

## [0.1.0] - 2026-09-29

### Added
- Initial public GitHub release at `fishke22/SPORTS_EDGE_AI` after post-commit publication audit passed with zero blockers and zero warnings.
- Portable project-root resolver and project paths.
- Pydantic canonical contracts for event/market/odds/prediction/model/backtest/paper/settlement/risk/data quality.
- DuckDB migration runner and initial Foundation schema.
- Baseline market pricing primitives and conservative risk gate.
- Foundation tests and construction handoff documentation.
- Bronze content-addressed raw objects, immutable ingest manifests, and provenance migration `0002`.
- Synthetic NBA normalization to Silver Parquet and canonical DuckDB rows.
- Point-in-time as-of odds repository with future-snapshot exclusion tests.
- CLI commands `ingest-synthetic` and `odds-as-of`.
- Explicit `pytz` runtime dependency required by DuckDB `TIMESTAMPTZ` Python conversion.
- Migration `0003` with synthetic provider/license seed and provider entity mapping.
- Gold market-baseline Parquet builder with implied probability, multiplicative de-vig, fair odds, gross EV baseline, and point-in-time hard gate.
- Expanding walk-forward scaffold that forbids temporal overlap and remains `NO_VALIDATED_EDGE` until model validation.
- CLI command `market-baseline` and Windows `tzdata` runtime dependency.
- Migration `0004` with versioned payout/cost rules and a non-production synthetic zero-cost seed.
- Net EV service and rule-effective-time repository.
- Shared Market Analysis Service integrating model probability, market baseline, edge, gross/net EV, data quality, and risk decisions.
- CLI command `analyze-market` plus rule-version and risk-gate regression tests.

- NBA V1 point-in-time feature and training-sample contracts with feature/odds/result timestamp guards.
- Interpretable pure-Python NBA logistic baseline using rating difference, rest difference, and home-court indicator.
- `analyze_nba_market` adapter that routes model probabilities through the shared Market Analysis Service.
- Expanding NBA walk-forward evaluator with model-vs-market Brier/LogLoss/ECE, ROI/Yield, CLV, Max Drawdown, bootstrap yield CI, and finite-horizon risk of ruin.
- Walk-forward leakage guards for settled labels, non-overlapping test windows, and full-fold payout/cost-rule validity.

- Time-separated Platt calibration service and per-fold calibrated walk-forward support.
- Versioned validation-policy contracts with explicit evidence tiers and synthetic fail-closed behavior.
- Canonical JSON NBA model artifacts with content-addressed SHA-256 paths and checksum verification.
- Portable model registry / backtest persistence plus deterministic full backtest reports under `reports/backtests/`.
- Calibrated NBA single-event analysis path that still routes through the shared Market Analysis Service.
- FastAPI `/api/v1` adapter for health, as-of odds, market baseline/analysis, model registry, and backtest reads.
- Shared interface service and typed interface response schemas used by REST and MCP.
- Official MCP Python SDK v2 server with six read-only/idempotent structured-output tools.
- DuckDB read-only connections for interface query repositories and non-mutating uninitialized health checks.
- React 19 + TypeScript + Vite + ECharts synthetic dashboard with REST-only domain access.
- Lazy/module ECharts bundle split, frontend Vitest contract test, and frontend production build.
- Portable bootstrap now runs Python lint/type/test plus npm ci/Vitest/Vite build; portability scan includes frontend source/config.
- Market analysis now rejects mutually-exclusive model probabilities that do not sum to 1.0.
- Migration `0005` with The Odds API source-license/provider capability evidence and research-only provider registration.
- The Odds API v4 historical NBA h2h client with secret-only credential handling, quota-header parsing, sanitized HTTP errors, and immutable Bronze storage.
- Conservative historical timestamp validation using snapshot and market/bookmaker update timestamps.
- The Odds API canonical normalization with provider entity mapping gate, Data Quality RED fail-closed behavior, Silver Parquet, and DuckDB persistence.
- Synthetic provider-schema contract fixture and regression tests for future-snapshot rejection, secret leakage, missing mappings, and as-of visibility.
- CLI command `ingest-the-odds-api-historical`; API key is read only from `SPORTS_EDGE_THE_ODDS_API_KEY`.

- Migration 0006 with provider usage snapshots, entity-mapping proposals/review state, event results, paper-trade settlement linkage, and paper zero-cost research rule.
- Free-plan The Odds API current NBA h2h, participants, and scores clients with local credit-budget enforcement.
- Manual entity-mapping proposal/list/approve/reject workflow, mapping review summary, and formal NBA candidate filtering.
- Event-result provenance repository and local NBA Elo/rest feature reconstruction from decision-time-known completed results only.
- Local canonical-history NBA training dataset with separate decision-time and closing odds for CLV/research evaluation.
- Local NBA research orchestration returning INSUFFICIENT_DATA or walk-forward + validation-gate evidence without fabricating a model edge.
- Prediction persistence with bookmaker/source/odds_snapshot_id provenance tied to the exact as-of market snapshot.
- Paper-only trade open/settle workflow requiring VALIDATED + EDGE + GREEN + positive Net EV, with versioned fail-closed settlement.
- Read-only API/MCP endpoints for canonical entities, mapping proposals/summary, provider usage, event results, and paper portfolio.
- React operational cards for provider usage, mapping review, and paper portfolio; no mutation or betting controls in the Web UI.
- Portable research backup/restore with checksum/path validation, raw-data exclusion, and explicit force required for restore.
- Executable publication audit covering tracked secret/runtime/raw/data/model/report/backup files, large files, machine-specific paths, governance files, Git history state, and dependency license metadata.
- Standalone CLI commands for free-provider operations, mapping review, local NBA research, prediction, paper workflow, provider usage, backup, and restore.
- docs/OPERATIONS.md runbook covering ingestion through paper settlement and release gating.
- Offline `sports-edge doctor` reporting schema/lock/build/credential/provider-gate readiness without network calls.
- Deterministic release bundle builder with fixed ZIP metadata, per-file SHA-256 manifest, PROJECT_ROOT output guard, and publication-audit prerequisite.
- Cross-platform GitHub Actions quality gate for Windows/Linux and Python 3.11/3.14 plus frontend, publication audit, and release-bundle smoke.
- Publication audit now requires the CI workflow and blocks external GitHub Actions that are not pinned to full 40-character commit SHAs.
- Live The Odds API validation: 32 participants reviewed to 30 approved NBA franchise mappings / 2 rejected non-franchise participants; current h2h canonicalized 41 events and 212 odds with GREEN data quality; historical entitlement probe returned HTTP 401.
- Root-local secret isolation: Settings now loads dotenv only from resolved PROJECT_ROOT, process environment retains precedence, and empty secrets are rejected.
- Added hidden-input `configure-odds-api-key` CLI workflow and regression coverage preventing credential leakage/cross-workspace contamination.
- Migration 0007 forward collection run ledger with SUCCESS/DEGRADED/SKIPPED/PARTIAL/FAILED evidence, quota deltas, freshness and result-coverage status.
- One-shot collect-forward / read-only collection-status workflow with 3-hour current cadence, 12-hour scores cadence, credit-budget gate, and scores calls only when a past canonical event is still missing a completed result.
- Read-only FastAPI/MCP/Web forward-collection status surfaces; collector execution remains CLI/scheduler-only.
- Portable PowerShell collector runner plus Windows Task Scheduler register/unregister helpers with WhatIf, IgnoreNew, StartWhenAvailable, and bounded execution time.
- Forward collector error ledger explicitly redacts the active API key; same-timestamp quota rows are ordered deterministically by cumulative requests used.

- Migration 0008 research readiness ledger with 180-sample first-evaluation capacity, 360-sample validation-capacity gate, temporal/calibration preflight, persisted snapshots, fingerprint dedup, and explicit no-auto-promotion guarantee.
- Read-only FastAPI/MCP/Web NBA research-readiness surfaces backed by persisted hourly evidence to avoid rebuilding the full training dataset on every query.
- Migration 0009 operational-monitor snapshots covering collection/research heartbeats, provider quota/local budget, result gaps, odds coverage, readiness progress, and monotonic counter drift.
- Added ops-monitor / ops-status CLI commands, read-only FastAPI/MCP/Web operational-health surfaces, and scheduler chaining collection -> research-cycle -> operational monitor.
- Operational monitor treats ordinary NOT_READY as healthy research state; stale/failure/quota/coverage conditions generate WARN/FAIL without automatic repair, model promotion, or betting actions.
