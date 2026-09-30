from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import typer

from sports_edge_ai.application.backblaze_b2_roundtrip import (
    run_backblaze_b2_live_roundtrip,
)
from sports_edge_ai.application.backblaze_b2_status import (
    get_backblaze_b2_preflight_status,
)
from sports_edge_ai.application.checkpoint_backend_smoke import (
    run_checkpoint_backend_contract_smoke,
)
from sports_edge_ai.application.doctor import run_system_doctor
from sports_edge_ai.application.entity_mapping import (
    approve_entity_mapping,
    get_mapping_review_summary,
    list_entity_proposals,
    reject_entity_mapping,
)
from sports_edge_ai.application.forward_collection import (
    get_forward_collection_status,
    run_forward_collection,
)
from sports_edge_ai.application.free_provider_pipeline import (
    normalize_current_nba_h2h,
    normalize_nba_scores,
    propose_nba_participant_mappings,
)
from sports_edge_ai.application.local_nba_modeling import evaluate_local_nba_research
from sports_edge_ai.application.local_nba_research import build_nba_feature_from_local_history
from sports_edge_ai.application.market_analysis import analyze_market
from sports_edge_ai.application.market_baseline import build_market_baseline
from sports_edge_ai.application.operational_monitor import (
    get_operational_status,
    run_operational_monitor,
)
from sports_edge_ai.application.paper_trading import open_paper_trade, settle_open_paper_trades
from sports_edge_ai.application.prediction_service import generate_nba_prediction_records
from sports_edge_ai.application.repository_smoke import run_repository_smoke
from sports_edge_ai.application.research_readiness import (
    get_nba_research_readiness_status,
    run_nba_research_cycle,
)
from sports_edge_ai.application.synthetic_pipeline import ingest_synthetic_snapshot
from sports_edge_ai.application.the_odds_api_pipeline import normalize_historical_nba_h2h
from sports_edge_ai.application.zero_cost_runtime import get_zero_cost_runtime_status
from sports_edge_ai.common.release_bundle import build_release_bundle
from sports_edge_ai.common.root import ProjectPaths
from sports_edge_ai.common.settings import Settings
from sports_edge_ai.domain.schemas import DataQualityStatus
from sports_edge_ai.infrastructure.backup import create_research_backup, restore_research_backup
from sports_edge_ai.infrastructure.db import migrate
from sports_edge_ai.infrastructure.odds_repository import get_event_odds_as_of
from sports_edge_ai.infrastructure.operational_checkpoint import (
    create_operational_checkpoint,
    restore_operational_checkpoint,
    verify_operational_checkpoint,
)
from sports_edge_ai.infrastructure.paper_trade_repository import list_ready_paper_event_ids
from sports_edge_ai.infrastructure.prediction_repository import get_prediction_record
from sports_edge_ai.infrastructure.provider_usage_repository import get_latest_provider_usage
from sports_edge_ai.infrastructure.providers.the_odds_api import (
    PROVIDER_ID,
    fetch_historical_nba_h2h_snapshot,
)
from sports_edge_ai.infrastructure.providers.the_odds_api_free import (
    fetch_current_nba_h2h,
    fetch_nba_participants,
    fetch_nba_scores,
)

app = typer.Typer(help="SPORTS_EDGE_AI portable CLI")


def _settings_and_odds_api_key() -> tuple[Settings, str]:
    settings = Settings()
    key = (
        ""
        if settings.the_odds_api_key is None
        else settings.the_odds_api_key.get_secret_value().strip()
    )
    if not key:
        raise typer.BadParameter(
            "SPORTS_EDGE_THE_ODDS_API_KEY is required and must be non-empty; "
            "use configure-odds-api-key or a local .env file"
        )
    return settings, key


def _write_local_odds_api_key(api_key: str) -> Path:
    normalized = api_key.strip()
    if not normalized or "\n" in normalized or "\r" in normalized:
        raise typer.BadParameter("The Odds API key must be a non-empty single line")
    paths = ProjectPaths.discover()
    env_path = paths.root / ".env"
    existing = env_path.read_text(encoding="utf-8-sig").splitlines() if env_path.is_file() else []
    prefix = "SPORTS_EDGE_THE_ODDS_API_KEY="
    retained = [line for line in existing if not line.startswith(prefix)]
    content = "\n".join([*retained, f"{prefix}{normalized}"]).strip("\n") + "\n"
    temporary = env_path.with_name(".env.tmp")
    temporary.write_text(content, encoding="utf-8")
    temporary.replace(env_path)
    return env_path


@app.command("configure-odds-api-key")
def configure_odds_api_key() -> None:
    key = typer.prompt(
        "The Odds API key",
        hide_input=True,
        confirmation_prompt=True,
    )
    env_path = _write_local_odds_api_key(key)
    typer.echo(
        json.dumps(
            {
                "status": "configured",
                "env_relative": env_path.relative_to(ProjectPaths.discover().root).as_posix(),
                "credential_nonempty": True,
            },
            ensure_ascii=False,
        )
    )


@app.command()
def health() -> None:
    paths = ProjectPaths.discover()
    payload = {
        "status": "ok",
        "project_root": str(paths.root),
        "database_relative": str(Path("state") / paths.database.name),
    }
    typer.echo(json.dumps(payload, ensure_ascii=False))


@app.command("repo-smoke")
def repository_smoke() -> None:
    result = run_repository_smoke()
    typer.echo(
        json.dumps(
            {
                "status": result.status,
                "mode": result.mode,
                "schema_version": result.schema_version,
                "event_id": result.event_id,
                "decision_as_of": result.decision_as_of.isoformat(),
                "max_input_observed_at": result.max_input_observed_at.isoformat(),
                "baseline_odds": dict(result.baseline_odds),
                "recommendations": list(result.recommendations),
                "risk_blockers": list(result.risk_blockers),
                "network_required": result.network_required,
                "credentials_required": result.credentials_required,
                "persistent_state_required": result.persistent_state_required,
                "validated_edge_claimed": result.validated_edge_claimed,
                "limitations": list(result.limitations),
            },
            ensure_ascii=False,
        )
    )


@app.command("init-db")
def init_db() -> None:
    result = migrate()
    typer.echo(
        json.dumps(
            {
                "status": "ok",
                "applied_migrations": list(result.applied),
                "current_version": result.current_version,
            },
            ensure_ascii=False,
        )
    )


@app.command("ingest-synthetic")
def ingest_synthetic(fixture: Path) -> None:
    result = ingest_synthetic_snapshot(fixture)
    typer.echo(
        json.dumps(
            {
                "status": "ok",
                "ingest_run_id": result.bronze.ingest_run_id,
                "event_id": result.event.event_id,
                "odds_count": len(result.odds),
                "silver_paths": list(result.silver_paths),
            },
            ensure_ascii=False,
        )
    )


@app.command("odds-as-of")
def odds_as_of(event_id: str, as_of: str) -> None:
    decision_as_of = datetime.fromisoformat(as_of.replace("Z", "+00:00"))
    rows = get_event_odds_as_of(event_id=event_id, decision_as_of=decision_as_of)
    typer.echo(
        json.dumps(
            {
                "event_id": event_id,
                "as_of": decision_as_of.isoformat(),
                "odds": [
                    {
                        "market_id": row.market_id,
                        "bookmaker": row.bookmaker,
                        "decimal_odds": row.decimal_odds,
                        "observed_at": row.observed_at.isoformat(),
                    }
                    for row in rows
                ],
            },
            ensure_ascii=False,
        )
    )


@app.command("market-baseline")
def market_baseline(event_id: str, as_of: str) -> None:
    decision_as_of = datetime.fromisoformat(as_of.replace("Z", "+00:00"))
    dataset = build_market_baseline(
        event_id=event_id,
        decision_as_of=decision_as_of,
    )
    typer.echo(
        json.dumps(
            {
                "event_id": event_id,
                "as_of": decision_as_of.isoformat(),
                "relative_path": dataset.relative_path,
                "records": [record.model_dump(mode="json") for record in dataset.records],
            },
            ensure_ascii=False,
        )
    )


@app.command("analyze-market")
def analyze_market_command(
    event_id: str,
    as_of: str,
    model_probabilities_json: str,
    payout_cost_rule_version: str = "synthetic-zero-cost-v1",
    uncertainty: float = 0.10,
    data_quality: DataQualityStatus = DataQualityStatus.GREEN,
    model_validated: bool = False,
) -> None:
    decision_as_of = datetime.fromisoformat(as_of.replace("Z", "+00:00"))
    model_probabilities = json.loads(model_probabilities_json)
    if not isinstance(model_probabilities, dict):
        raise typer.BadParameter("model_probabilities_json must decode to an object")

    records = analyze_market(
        event_id=event_id,
        decision_as_of=decision_as_of,
        model_probabilities={
            str(selection): float(probability)
            for selection, probability in model_probabilities.items()
        },
        payout_cost_rule_version=payout_cost_rule_version,
        uncertainty=uncertainty,
        data_quality=data_quality,
        model_validated=model_validated,
    )
    typer.echo(
        json.dumps(
            {
                "event_id": event_id,
                "as_of": decision_as_of.isoformat(),
                "records": [record.model_dump(mode="json") for record in records],
            },
            ensure_ascii=False,
        )
    )


@app.command("ingest-the-odds-api-historical")
def ingest_the_odds_api_historical(
    requested_at: str,
    region: str = "us",
) -> None:
    settings, api_key = _settings_and_odds_api_key()
    decision_time = datetime.fromisoformat(requested_at.replace("Z", "+00:00"))
    fetch = fetch_historical_nba_h2h_snapshot(
        api_key=api_key,
        requested_at=decision_time,
        region=region,
        paths=settings.paths,
    )
    normalized = normalize_historical_nba_h2h(fetch, paths=settings.paths)
    if normalized.unresolved_entities:
        ingest_status = "bronze_only_unresolved_mapping"
    elif not normalized.odds:
        ingest_status = "bronze_only_no_usable_odds"
    else:
        ingest_status = "canonicalized"
    typer.echo(
        json.dumps(
            {
                "status": ingest_status,
                "provider": fetch.bronze.provider,
                "requested_at": decision_time.isoformat(),
                "snapshot_at": fetch.snapshot.timestamp.isoformat(),
                "bronze_relative_path": fetch.bronze.relative_path,
                "manifest_relative_path": fetch.bronze.manifest_relative_path,
                "events_count": len(normalized.events),
                "odds_count": len(normalized.odds),
                "data_quality": normalized.data_quality.status.value,
                "mapping_rate": normalized.data_quality.mapping_rate,
                "unresolved_entities": list(normalized.unresolved_entities),
                "quota": {
                    "remaining": fetch.quota.remaining,
                    "used": fetch.quota.used,
                    "last_cost": fetch.quota.last_cost,
                },
            },
            ensure_ascii=False,
        )
    )


@app.command("odds-api-propose-nba-mappings")
def odds_api_propose_nba_mappings() -> None:
    settings, api_key = _settings_and_odds_api_key()
    fetch = fetch_nba_participants(
        api_key=api_key,
        paths=settings.paths,
        local_monthly_budget=settings.the_odds_api_monthly_credit_budget,
    )
    proposals = propose_nba_participant_mappings(fetch, paths=settings.paths)
    summary = get_mapping_review_summary(
        provider_id=PROVIDER_ID,
        entity_kind="TEAM",
        paths=settings.paths,
    )
    typer.echo(
        json.dumps(
            {
                "status": "review_required",
                "proposal_count": len(proposals),
                "pending_count": summary.pending_count,
                "approved_count": summary.approved_count,
                "rejected_count": summary.rejected_count,
                "quota": {
                    "remaining": fetch.quota.remaining,
                    "used": fetch.quota.used,
                    "last_cost": fetch.quota.last_cost,
                },
            },
            ensure_ascii=False,
        )
    )


@app.command("entity-proposals")
def entity_proposals(
    provider_id: str = PROVIDER_ID,
    status: str | None = "PENDING",
) -> None:
    records = list_entity_proposals(provider_id=provider_id, status=status)
    typer.echo(
        json.dumps(
            {
                "provider_id": provider_id,
                "status": status,
                "records": [record.model_dump(mode="json") for record in records],
            },
            ensure_ascii=False,
        )
    )


@app.command("approve-entity-mapping")
def approve_entity_mapping_command(
    provider_entity_id: str,
    canonical_entity_id: str,
    review_note: str = "",
) -> None:
    record = approve_entity_mapping(
        provider_id=PROVIDER_ID,
        entity_kind="TEAM",
        provider_entity_id=provider_entity_id,
        canonical_entity_id=canonical_entity_id,
        review_note=review_note or None,
    )
    typer.echo(json.dumps(record.model_dump(mode="json"), ensure_ascii=False))


@app.command("reject-entity-mapping")
def reject_entity_mapping_command(
    provider_entity_id: str,
    review_note: str,
) -> None:
    record = reject_entity_mapping(
        provider_id=PROVIDER_ID,
        entity_kind="TEAM",
        provider_entity_id=provider_entity_id,
        review_note=review_note,
    )
    typer.echo(json.dumps(record.model_dump(mode="json"), ensure_ascii=False))


@app.command("ingest-the-odds-api-current")
def ingest_the_odds_api_current(region: str | None = None) -> None:
    settings, api_key = _settings_and_odds_api_key()
    fetch = fetch_current_nba_h2h(
        api_key=api_key,
        paths=settings.paths,
        region=region or settings.the_odds_api_region,
        local_monthly_budget=settings.the_odds_api_monthly_credit_budget,
    )
    normalized = normalize_current_nba_h2h(fetch, paths=settings.paths)
    typer.echo(
        json.dumps(
            {
                "status": (
                    "canonicalized"
                    if normalized.odds
                    else "bronze_only_unresolved_or_no_usable_odds"
                ),
                "events_count": len(normalized.events),
                "odds_count": len(normalized.odds),
                "data_quality": normalized.data_quality.status.value,
                "mapping_rate": normalized.data_quality.mapping_rate,
                "unresolved_entities": list(normalized.unresolved_entities),
                "quota": {
                    "remaining": fetch.quota.remaining,
                    "used": fetch.quota.used,
                    "last_cost": fetch.quota.last_cost,
                },
            },
            ensure_ascii=False,
        )
    )


@app.command("ingest-the-odds-api-scores")
def ingest_the_odds_api_scores(days_from: int = 3) -> None:
    settings, api_key = _settings_and_odds_api_key()
    fetch = fetch_nba_scores(
        api_key=api_key,
        paths=settings.paths,
        days_from=days_from,
        local_monthly_budget=settings.the_odds_api_monthly_credit_budget,
    )
    normalized = normalize_nba_scores(fetch, paths=settings.paths)
    typer.echo(
        json.dumps(
            {
                "status": (
                    "normalized"
                    if not normalized.unresolved_provider_events
                    else "normalized_with_unresolved_events"
                ),
                "result_count": len(normalized.results),
                "unresolved_provider_events": list(normalized.unresolved_provider_events),
                "quota": {
                    "remaining": fetch.quota.remaining,
                    "used": fetch.quota.used,
                    "last_cost": fetch.quota.last_cost,
                },
            },
            ensure_ascii=False,
        )
    )


@app.command("provider-usage")
def provider_usage(provider_id: str = PROVIDER_ID) -> None:
    usage = get_latest_provider_usage(provider_id=provider_id)
    typer.echo(
        json.dumps(
            {
                "found": usage is not None,
                "usage": None if usage is None else usage.model_dump(mode="json"),
            },
            ensure_ascii=False,
        )
    )


@app.command("collect-forward")
def collect_forward(
    include_scores: bool = True,
    force_current: bool = False,
    force_scores: bool = False,
    trigger_kind: str = "MANUAL",
) -> None:
    settings, api_key = _settings_and_odds_api_key()
    record = run_forward_collection(
        api_key=api_key,
        paths=settings.paths,
        region=settings.the_odds_api_region,
        local_monthly_budget=settings.the_odds_api_monthly_credit_budget,
        current_min_interval_minutes=settings.forward_current_min_interval_minutes,
        scores_min_interval_minutes=settings.forward_scores_min_interval_minutes,
        scores_days_from=settings.forward_scores_days_from,
        include_scores=include_scores,
        force_current=force_current,
        force_scores=force_scores,
        trigger_kind=trigger_kind,
    )
    typer.echo(json.dumps(record.model_dump(mode="json"), ensure_ascii=False))


@app.command("collection-status")
def collection_status() -> None:
    settings = Settings()
    status = get_forward_collection_status(
        paths=settings.paths,
        current_min_interval_minutes=settings.forward_current_min_interval_minutes,
        scores_min_interval_minutes=settings.forward_scores_min_interval_minutes,
    )
    typer.echo(json.dumps(status.model_dump(mode="json"), ensure_ascii=False))


@app.command("research-readiness")
def research_readiness() -> None:
    status = get_nba_research_readiness_status()
    typer.echo(json.dumps(status.model_dump(mode="json"), ensure_ascii=False))


@app.command("research-cycle")
def research_cycle(trigger_kind: str = "MANUAL") -> None:
    record = run_nba_research_cycle(trigger_kind=trigger_kind)
    typer.echo(json.dumps(record.model_dump(mode="json"), ensure_ascii=False))


@app.command("ops-status")
def ops_status() -> None:
    record = get_operational_status()
    typer.echo(json.dumps(record.model_dump(mode="json"), ensure_ascii=False))


@app.command("ops-monitor")
def ops_monitor(trigger_kind: str = "MANUAL") -> None:
    record = run_operational_monitor(trigger_kind=trigger_kind)
    typer.echo(json.dumps(record.model_dump(mode="json"), ensure_ascii=False))


@app.command("paper-open")
def paper_open(
    prediction_id: str,
    stake: float = 1.0,
    odds_snapshot_id: str | None = None,
) -> None:
    prediction = get_prediction_record(prediction_id=prediction_id)
    if prediction is None:
        raise typer.BadParameter("prediction_id not found")
    effective_snapshot_id = odds_snapshot_id or prediction.odds_snapshot_id
    if effective_snapshot_id is None:
        raise typer.BadParameter("prediction has no odds_snapshot_id provenance")
    trade = open_paper_trade(
        prediction=prediction,
        odds_snapshot_id=effective_snapshot_id,
        stake=stake,
    )
    typer.echo(json.dumps(trade.model_dump(mode="json"), ensure_ascii=False))


@app.command("paper-settle")
def paper_settle(event_id: str, settled_at: str) -> None:
    timestamp = datetime.fromisoformat(settled_at.replace("Z", "+00:00"))
    records = settle_open_paper_trades(event_id=event_id, settled_at=timestamp)
    typer.echo(
        json.dumps(
            {
                "event_id": event_id,
                "settlements": [record.model_dump(mode="json") for record in records],
            },
            ensure_ascii=False,
        )
    )


@app.command("local-nba-research")
def local_nba_research(
    decision_horizon_hours: int = 6,
    min_train_size: int = 160,
    test_size: int = 20,
    calibration_size: int = 20,
    bootstrap_iterations: int = 1000,
) -> None:
    result = evaluate_local_nba_research(
        decision_horizon_hours=decision_horizon_hours,
        min_train_size=min_train_size,
        test_size=test_size,
        calibration_size=calibration_size,
        bootstrap_iterations=bootstrap_iterations,
    )
    typer.echo(
        json.dumps(
            {
                "status": result.status,
                "candidate_event_count": result.dataset.candidate_event_count,
                "sample_count": len(result.dataset.samples),
                "skipped_missing_odds": result.dataset.skipped_missing_odds,
                "skipped_non_decisive_result": result.dataset.skipped_non_decisive_result,
                "evaluation": (
                    None if result.evaluation is None else result.evaluation.model_dump(mode="json")
                ),
                "validation": (
                    None if result.validation is None else result.validation.model_dump(mode="json")
                ),
            },
            ensure_ascii=False,
        )
    )


@app.command("predict-nba")
def predict_nba(
    event_id: str,
    as_of: str,
    model_id: str,
    model_version: str,
    uncertainty: float = 0.10,
) -> None:
    decision_as_of = datetime.fromisoformat(as_of.replace("Z", "+00:00"))
    feature = build_nba_feature_from_local_history(
        event_id=event_id,
        decision_as_of=decision_as_of,
    )
    predictions = generate_nba_prediction_records(
        feature=feature,
        model_id=model_id,
        model_version=model_version,
        uncertainty=uncertainty,
        data_quality=DataQualityStatus.GREEN,
    )
    typer.echo(
        json.dumps(
            {
                "event_id": event_id,
                "as_of": decision_as_of.isoformat(),
                "feature": feature.model_dump(mode="json"),
                "predictions": [record.model_dump(mode="json") for record in predictions],
            },
            ensure_ascii=False,
        )
    )


@app.command("paper-ready-events")
def paper_ready_events() -> None:
    typer.echo(
        json.dumps(
            {"event_ids": list(list_ready_paper_event_ids())},
            ensure_ascii=False,
        )
    )


@app.command("checkpoint-backend-smoke")
def checkpoint_backend_smoke() -> None:
    result = run_checkpoint_backend_contract_smoke()
    typer.echo(
        json.dumps(
            {
                "status": result.status,
                "backend_id": result.backend_id,
                "remote_live_eligible": result.remote_live_eligible,
                "blockers": list(result.blockers),
                "checkpoint_sha256": result.checkpoint_sha256,
                "generation": result.generation,
                "restored_marker": result.restored_marker,
            },
            ensure_ascii=False,
        )
    )


@app.command("b2-preflight-status")
def b2_preflight_status(
    live: bool = typer.Option(
        False,
        "--live",
        help="Contact Backblaze using locally configured credentials; secrets are never printed.",
    ),
) -> None:
    assessment = get_backblaze_b2_preflight_status(live=live)
    typer.echo(
        json.dumps(
            {
                "policy_version": assessment.policy_version,
                "status": assessment.status,
                "storage_operations_allowed": assessment.storage_operations_allowed,
                "remote_live_ready": assessment.remote_live_ready,
                "blockers": list(assessment.blockers),
                "manual_evidence": {
                    "no_payment_method_confirmed": (
                        assessment.manual_evidence.no_payment_method_confirmed
                    ),
                    "zero_dollar_storage_cap_confirmed": (
                        assessment.manual_evidence.zero_dollar_storage_cap_confirmed
                    ),
                    "zero_dollar_download_cap_confirmed": (
                        assessment.manual_evidence.zero_dollar_download_cap_confirmed
                    ),
                    "transaction_caps_confirmed": (
                        assessment.manual_evidence.transaction_caps_confirmed
                    ),
                },
                "provider_evidence": {
                    "credentials_configured": (
                        assessment.provider_evidence.credentials_configured
                    ),
                    "bucket_configured": assessment.provider_evidence.bucket_configured,
                    "bucket_private": assessment.provider_evidence.bucket_private,
                    "lifecycle_rules_absent": (
                        assessment.provider_evidence.lifecycle_rules_absent
                    ),
                    "cloud_replication_disabled": (
                        assessment.provider_evidence.cloud_replication_disabled
                    ),
                    "data_key_bucket_scoped": (
                        assessment.provider_evidence.data_key_bucket_scoped
                    ),
                    "data_key_prefix_scoped": (
                        assessment.provider_evidence.data_key_prefix_scoped
                    ),
                    "data_key_capabilities_minimal": (
                        assessment.provider_evidence.data_key_capabilities_minimal
                    ),
                    "pointer_key_capabilities_minimal": (
                        assessment.provider_evidence.pointer_key_capabilities_minimal
                    ),
                    "pointer_key_account_wide": (
                        assessment.provider_evidence.pointer_key_account_wide
                    ),
                    "keys_same_account": assessment.provider_evidence.keys_same_account,
                    "provider_round_trip_verified": (
                        assessment.provider_evidence.provider_round_trip_verified
                    ),
                },
            },
            ensure_ascii=False,
        )
    )


@app.command("b2-live-roundtrip")
def b2_live_roundtrip(
    confirm: bool = typer.Option(
        False,
        "--confirm",
        help=(
            "Required explicit confirmation. Performs a real B2 upload/download/CAS probe "
            "against the configured empty checkpoint bucket."
        ),
    ),
) -> None:
    if not confirm:
        raise typer.BadParameter(
            "--confirm is required because this command writes a synthetic checkpoint to B2"
        )
    result = run_backblaze_b2_live_roundtrip()
    typer.echo(
        json.dumps(
            {
                "status": result.status,
                "checkpoint_sha256": result.checkpoint_sha256,
                "generation": result.generation,
                "bytes": result.bytes,
                "restored_marker": result.restored_marker,
                "cas_conflict_verified": result.cas_conflict_verified,
                "remote_live_ready": result.remote_live_ready,
                "blockers": list(result.blockers),
                "scheduler_enabled": False,
            },
            ensure_ascii=False,
        )
    )


@app.command("zero-cost-status")
def zero_cost_status() -> None:
    status = get_zero_cost_runtime_status()
    typer.echo(
        json.dumps(
            {
                "policy_version": status.policy_version,
                "status": status.status,
                "paid_services_allowed": status.paid_services_allowed,
                "automatic_billing_allowed": status.automatic_billing_allowed,
                "public_repo_is_state_authority": status.public_repo_is_state_authority,
                "github_actions_artifact_is_state_authority": (
                    status.github_actions_artifact_is_state_authority
                ),
                "remote_live_collection_ready": status.remote_live_collection_ready,
                "checkpoint_available": status.checkpoint_available,
                "latest_checkpoint_relative_path": status.latest_checkpoint_relative_path,
                "blockers": list(status.blockers),
                "required_capabilities": list(status.required_capabilities),
                "safe_modes": list(status.safe_modes),
                "forbidden_fallbacks": list(status.forbidden_fallbacks),
            },
            ensure_ascii=False,
        )
    )


@app.command("build-operational-checkpoint")
def build_operational_checkpoint() -> None:
    artifact = create_operational_checkpoint()
    typer.echo(
        json.dumps(
            {
                "relative_path": artifact.relative_path,
                "sha256": artifact.sha256,
                "manifest_sha256": artifact.manifest_sha256,
                "file_count": artifact.file_count,
                "total_bytes": artifact.total_bytes,
                "source_schema_version": artifact.source_schema_version,
                "public_export_allowed": False,
                "secret_transport": False,
            },
            ensure_ascii=False,
        )
    )


@app.command("verify-operational-checkpoint")
def verify_operational_checkpoint_command(checkpoint_path: Path) -> None:
    paths = ProjectPaths.discover()
    source = checkpoint_path if checkpoint_path.is_absolute() else paths.root / checkpoint_path
    verification = verify_operational_checkpoint(source)
    typer.echo(
        json.dumps(
            {
                "source_name": verification.source_name,
                "sha256": verification.sha256,
                "manifest_sha256": verification.manifest_sha256,
                "created_at": verification.created_at.isoformat(),
                "file_count": verification.file_count,
                "total_bytes": verification.total_bytes,
                "source_schema_version": verification.source_schema_version,
                "includes_raw_data": verification.includes_raw_data,
                "public_export_allowed": verification.public_export_allowed,
                "secret_transport": verification.secret_transport,
            },
            ensure_ascii=False,
        )
    )


@app.command("restore-operational-checkpoint")
def restore_operational_checkpoint_command(checkpoint_path: Path) -> None:
    paths = ProjectPaths.discover()
    source = checkpoint_path if checkpoint_path.is_absolute() else paths.root / checkpoint_path
    result = restore_operational_checkpoint(source, paths=paths)
    typer.echo(
        json.dumps(
            {
                "source_checkpoint": result.source_checkpoint,
                "restored_files": list(result.restored_files),
                "source_schema_version": result.source_schema_version,
            },
            ensure_ascii=False,
        )
    )


@app.command("backup-state")
def backup_state() -> None:
    artifact = create_research_backup()
    typer.echo(
        json.dumps(
            {
                "relative_path": artifact.relative_path,
                "sha256": artifact.sha256,
                "file_count": artifact.file_count,
            },
            ensure_ascii=False,
        )
    )


@app.command("restore-state")
def restore_state(backup_path: Path, force: bool = False) -> None:
    if not force:
        raise typer.BadParameter(
            "restore can overwrite local state; rerun with --force after reviewing the backup"
        )
    result = restore_research_backup(backup_path, force=True)
    typer.echo(
        json.dumps(
            {
                "source_backup": result.source_backup,
                "restored_files": list(result.restored_files),
            },
            ensure_ascii=False,
        )
    )


@app.command("doctor")
def doctor() -> None:
    report = run_system_doctor()
    typer.echo(
        json.dumps(
            {
                "status": report.status,
                "ready_for_research": report.ready_for_research,
                "project_root": report.project_root,
                "current_schema_version": report.current_schema_version,
                "expected_schema_version": report.expected_schema_version,
                "credential_configured": report.credential_configured,
                "provider_production_allowed": report.provider_production_allowed,
                "checks": [
                    {"name": check.name, "level": check.level, "detail": check.detail}
                    for check in report.checks
                ],
            },
            ensure_ascii=False,
        )
    )
    if report.status == "FAIL":
        raise typer.Exit(code=1)


@app.command("build-release")
def build_release() -> None:
    bundle = build_release_bundle()
    typer.echo(
        json.dumps(
            {
                "relative_path": bundle.relative_path,
                "sha256": bundle.sha256,
                "manifest_sha256": bundle.manifest_sha256,
                "file_count": bundle.file_count,
                "version": bundle.version,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    app()
