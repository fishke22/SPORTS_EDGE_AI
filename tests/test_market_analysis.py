from __future__ import annotations

import shutil
from datetime import UTC, datetime
from pathlib import Path

import pytest
from typer.testing import CliRunner

from sports_edge_ai.application.market_analysis import analyze_market
from sports_edge_ai.application.net_ev import net_ev
from sports_edge_ai.application.synthetic_pipeline import ingest_synthetic_snapshot
from sports_edge_ai.cli import app
from sports_edge_ai.common.root import ProjectPaths
from sports_edge_ai.domain.schemas import (
    DataQualityStatus,
    PayoutCostRule,
    Recommendation,
)
from sports_edge_ai.infrastructure.db import migrate
from sports_edge_ai.infrastructure.rules_repository import get_payout_cost_rule

PROJECT_ROOT = Path(__file__).parents[1]


def _portable_root(tmp_path: Path) -> ProjectPaths:
    root = tmp_path / "portable"
    migrations = root / "sql" / "migrations"
    migrations.mkdir(parents=True)
    (root / ".sports-edge-root").write_text("SPORTS_EDGE_AI\n", encoding="utf-8")
    for migration in (PROJECT_ROOT / "sql" / "migrations").glob("*.sql"):
        shutil.copy2(migration, migrations / migration.name)
    return ProjectPaths(root)


def _fixture(name: str) -> Path:
    return PROJECT_ROOT / "fixtures" / "synthetic" / name


def test_zero_cost_rule_preserves_gross_ev(tmp_path: Path) -> None:
    paths = _portable_root(tmp_path)
    migrate(paths)
    as_of = datetime(2026, 10, 1, 8, 30, tzinfo=UTC)
    rule = get_payout_cost_rule(
        rule_version="synthetic-zero-cost-v1",
        decision_as_of=as_of,
        paths=paths,
    )

    assert net_ev(model_probability=0.60, decimal_odds=1.80, rule=rule) == pytest.approx(0.08)


def test_cost_rule_reduces_net_ev() -> None:
    rule = PayoutCostRule(
        rule_version="test-cost-v1",
        jurisdiction="TEST",
        market_scope="ALL",
        effective_from=datetime(2026, 1, 1, tzinfo=UTC),
        payout_factor=0.95,
        stake_cost_rate=0.01,
        fixed_cost_per_unit_stake=0.01,
        source_ref="tests",
        verified_at=datetime(2026, 1, 1, tzinfo=UTC),
    )

    assert net_ev(model_probability=0.60, decimal_odds=1.80, rule=rule) == pytest.approx(0.006)


def test_rule_version_must_be_effective_at_decision_time(tmp_path: Path) -> None:
    paths = _portable_root(tmp_path)
    migrate(paths)

    with pytest.raises(ValueError, match="not effective"):
        get_payout_cost_rule(
            rule_version="synthetic-zero-cost-v1",
            decision_as_of=datetime(2025, 12, 31, 23, 59, tzinfo=UTC),
            paths=paths,
        )


def test_market_analysis_routes_model_probability_through_risk_gate(
    tmp_path: Path,
) -> None:
    paths = _portable_root(tmp_path)
    ingest_synthetic_snapshot(_fixture("nba_moneyline_snapshot.json"), paths=paths)
    as_of = datetime(2026, 10, 1, 8, 30, tzinfo=UTC)

    unvalidated = analyze_market(
        event_id="SYNTH_NBA_001",
        decision_as_of=as_of,
        model_probabilities={"HOME": 0.60, "AWAY": 0.40},
        payout_cost_rule_version="synthetic-zero-cost-v1",
        uncertainty=0.10,
        data_quality=DataQualityStatus.GREEN,
        model_validated=False,
        paths=paths,
    )
    validated = analyze_market(
        event_id="SYNTH_NBA_001",
        decision_as_of=as_of,
        model_probabilities={"HOME": 0.60, "AWAY": 0.40},
        payout_cost_rule_version="synthetic-zero-cost-v1",
        uncertainty=0.10,
        data_quality=DataQualityStatus.GREEN,
        model_validated=True,
        paths=paths,
    )

    unvalidated_by_selection = {row.selection: row for row in unvalidated}
    validated_by_selection = {row.selection: row for row in validated}

    assert unvalidated_by_selection["HOME"].recommendation is Recommendation.NO_VALIDATED_EDGE
    assert validated_by_selection["HOME"].recommendation is Recommendation.EDGE
    assert validated_by_selection["HOME"].net_ev == pytest.approx(0.08)
    assert validated_by_selection["HOME"].edge > 0.0
    assert validated_by_selection["AWAY"].recommendation is Recommendation.NO_BET
    assert all(row.max_input_observed_at <= as_of for row in validated)


def test_market_analysis_rejects_probabilities_that_do_not_sum_to_one(
    tmp_path: Path,
) -> None:
    paths = _portable_root(tmp_path)
    ingest_synthetic_snapshot(_fixture("nba_moneyline_snapshot.json"), paths=paths)

    with pytest.raises(ValueError, match="must sum to 1.0"):
        analyze_market(
            event_id="SYNTH_NBA_001",
            decision_as_of=datetime(2026, 10, 1, 8, 30, tzinfo=UTC),
            model_probabilities={"HOME": 0.60, "AWAY": 0.50},
            payout_cost_rule_version="synthetic-zero-cost-v1",
            uncertainty=0.10,
            data_quality=DataQualityStatus.GREEN,
            model_validated=False,
            paths=paths,
        )


def test_red_data_quality_vetoes_market_analysis(tmp_path: Path) -> None:
    paths = _portable_root(tmp_path)
    ingest_synthetic_snapshot(_fixture("nba_moneyline_snapshot.json"), paths=paths)

    records = analyze_market(
        event_id="SYNTH_NBA_001",
        decision_as_of=datetime(2026, 10, 1, 8, 30, tzinfo=UTC),
        model_probabilities={"HOME": 0.60, "AWAY": 0.40},
        payout_cost_rule_version="synthetic-zero-cost-v1",
        uncertainty=0.10,
        data_quality=DataQualityStatus.RED,
        model_validated=True,
        paths=paths,
    )

    assert all(row.recommendation is Recommendation.NO_BET for row in records)


def test_cli_analyze_market_uses_shared_service(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths = _portable_root(tmp_path)
    ingest_synthetic_snapshot(_fixture("nba_moneyline_snapshot.json"), paths=paths)
    monkeypatch.setenv("SPORTS_EDGE_ROOT", str(paths.root))

    result = CliRunner().invoke(
        app,
        [
            "analyze-market",
            "SYNTH_NBA_001",
            "2026-10-01T08:30:00Z",
            '{"HOME": 0.60, "AWAY": 0.40}',
        ],
    )

    assert result.exit_code == 0, result.stdout
    assert '"NO_VALIDATED_EDGE"' in result.stdout
