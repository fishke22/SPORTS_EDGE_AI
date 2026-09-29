from __future__ import annotations

import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory

from sports_edge_ai.application.market_analysis import analyze_market
from sports_edge_ai.application.market_baseline import build_market_baseline
from sports_edge_ai.application.synthetic_pipeline import ingest_synthetic_snapshot
from sports_edge_ai.common.root import ROOT_MARKER, ProjectPaths
from sports_edge_ai.domain.schemas import DataQualityStatus, Recommendation
from sports_edge_ai.infrastructure.db import current_schema_version

REPOSITORY_SMOKE_EVENT_ID = "SYNTH_NBA_001"
REPOSITORY_SMOKE_DECISION_AS_OF = datetime(2026, 10, 1, 8, 30, tzinfo=UTC)
REPOSITORY_SMOKE_MODEL_PROBABILITIES = {"AWAY": 0.40, "HOME": 0.60}
EXPECTED_AS_OF_ODDS = (("AWAY", 2.10), ("HOME", 1.80))


@dataclass(frozen=True, slots=True)
class RepositorySmokeResult:
    status: str
    mode: str
    schema_version: str | None
    event_id: str
    decision_as_of: datetime
    max_input_observed_at: datetime
    baseline_odds: tuple[tuple[str, float], ...]
    recommendations: tuple[str, ...]
    risk_blockers: tuple[str, ...]
    network_required: bool
    credentials_required: bool
    persistent_state_required: bool
    validated_edge_claimed: bool
    limitations: tuple[str, ...]


def _prepare_ephemeral_root(*, source_root: Path, ephemeral_root: Path) -> None:
    migration_source = source_root / "sql" / "migrations"
    if not migration_source.is_dir():
        raise FileNotFoundError(
            f"repository smoke requires sql/migrations in the checkout: {migration_source}"
        )

    (ephemeral_root / ROOT_MARKER).write_text("SPORTS_EDGE_AI\n", encoding="utf-8")
    shutil.copytree(migration_source, ephemeral_root / "sql" / "migrations")


def run_repository_smoke(
    *,
    source_paths: ProjectPaths | None = None,
) -> RepositorySmokeResult:
    source = source_paths or ProjectPaths.discover()
    fixture_dir = source.root / "fixtures" / "synthetic"
    fixtures = (
        fixture_dir / "nba_moneyline_snapshot.json",
        fixture_dir / "nba_moneyline_snapshot_later.json",
    )
    missing = [path for path in fixtures if not path.is_file()]
    if missing:
        raise FileNotFoundError(
            "repository smoke requires tracked synthetic fixtures: "
            + ", ".join(str(path) for path in missing)
        )

    with TemporaryDirectory(prefix="sports-edge-ai-repo-smoke-") as temporary:
        ephemeral_root = Path(temporary)
        _prepare_ephemeral_root(source_root=source.root, ephemeral_root=ephemeral_root)
        paths = ProjectPaths(ephemeral_root)

        for fixture in fixtures:
            ingest_synthetic_snapshot(fixture, paths=paths)

        baseline = build_market_baseline(
            event_id=REPOSITORY_SMOKE_EVENT_ID,
            decision_as_of=REPOSITORY_SMOKE_DECISION_AS_OF,
            paths=paths,
            persist=False,
        )
        analysis = analyze_market(
            event_id=REPOSITORY_SMOKE_EVENT_ID,
            decision_as_of=REPOSITORY_SMOKE_DECISION_AS_OF,
            model_probabilities=REPOSITORY_SMOKE_MODEL_PROBABILITIES,
            payout_cost_rule_version="synthetic-zero-cost-v1",
            uncertainty=0.10,
            data_quality=DataQualityStatus.GREEN,
            model_validated=False,
            paths=paths,
        )

        if not baseline.records or not analysis:
            raise RuntimeError("repository smoke produced no market records")

        max_input_observed_at = max(record.max_input_observed_at for record in baseline.records)
        if max_input_observed_at > REPOSITORY_SMOKE_DECISION_AS_OF:
            raise RuntimeError("repository smoke detected future input beyond decision_as_of")

        baseline_odds = tuple(
            sorted((record.selection, record.decimal_odds) for record in baseline.records)
        )
        if baseline_odds != EXPECTED_AS_OF_ODDS:
            raise RuntimeError(
                "repository smoke as-of odds mismatch; a future snapshot may have leaked "
                f"into the decision view: {baseline_odds!r}"
            )

        if any(
            record.is_model_validated or record.recommendation is Recommendation.EDGE
            for record in analysis
        ):
            raise RuntimeError("repository smoke must never claim a validated model edge")

        recommendations = tuple(sorted({record.recommendation.value for record in analysis}))
        risk_blockers = tuple(
            sorted({blocker for record in analysis for blocker in record.risk_blockers})
        )
        schema_version = current_schema_version(paths)

    return RepositorySmokeResult(
        status="PASS",
        mode="OFFLINE_SYNTHETIC_EPHEMERAL",
        schema_version=schema_version,
        event_id=REPOSITORY_SMOKE_EVENT_ID,
        decision_as_of=REPOSITORY_SMOKE_DECISION_AS_OF,
        max_input_observed_at=max_input_observed_at,
        baseline_odds=baseline_odds,
        recommendations=recommendations,
        risk_blockers=risk_blockers,
        network_required=False,
        credentials_required=False,
        persistent_state_required=False,
        validated_edge_claimed=False,
        limitations=(
            "synthetic_only",
            "no_live_provider_data",
            "not_model_validation",
            "ephemeral_state_deleted_after_run",
        ),
    )
