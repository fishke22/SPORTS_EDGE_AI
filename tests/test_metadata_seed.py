from __future__ import annotations

import shutil
from pathlib import Path

from sports_edge_ai.common.root import ProjectPaths
from sports_edge_ai.infrastructure.db import connect, migrate

PROJECT_ROOT = Path(__file__).parents[1]


def _portable_root(tmp_path: Path) -> ProjectPaths:
    root = tmp_path / "portable"
    migrations = root / "sql" / "migrations"
    migrations.mkdir(parents=True)
    (root / ".sports-edge-root").write_text("SPORTS_EDGE_AI\n", encoding="utf-8")
    for migration in (PROJECT_ROOT / "sql" / "migrations").glob("*.sql"):
        shutil.copy2(migration, migrations / migration.name)
    return ProjectPaths(root)


def test_synthetic_provider_license_and_entity_mapping_seed(tmp_path: Path) -> None:
    paths = _portable_root(tmp_path)
    result = migrate(paths)

    assert result.current_version == "0009"
    connection = connect(paths)
    try:
        provider = connection.execute(
            "SELECT provider_name, production_allowed FROM provider_registry "
            "WHERE provider_id = 'provider_synthetic_nba'"
        ).fetchone()

        license_row = connection.execute(
            "SELECT redistribution_allowed, automated_access_allowed "
            "FROM source_license_registry "
            "WHERE license_id = 'license_synthetic_project'"
        ).fetchone()
        mappings = connection.execute(
            "SELECT provider_entity_id, canonical_entity_id, confidence "
            "FROM provider_entity_mapping "
            "WHERE provider_id = 'provider_synthetic_nba' "
            "ORDER BY provider_entity_id"
        ).fetchall()
        real_provider = connection.execute(
            "SELECT provider_name, enabled, production_allowed, auth_type "
            "FROM provider_registry WHERE provider_id = 'provider_the_odds_api'"
        ).fetchone()
        real_license = connection.execute(
            "SELECT commercial_allowed, redistribution_allowed, "
            "automated_access_allowed, credential_required "
            "FROM source_license_registry "
            "WHERE license_id = 'license_the_odds_api_terms_20260831'"
        ).fetchone()
        capabilities = dict(
            connection.execute(
                "SELECT capability, capability_value "
                "FROM provider_capability_registry "
                "WHERE provider_id = 'provider_the_odds_api'"
            ).fetchall()
        )
    finally:
        connection.close()

    assert provider == ("Synthetic NBA Fixture", False)
    assert license_row == (True, True)
    assert mappings == [
        ("SYNTH_AWAY", "SYNTH_AWAY", 1.0),
        ("SYNTH_HOME", "SYNTH_HOME", 1.0),
    ]
    assert real_provider == ("The Odds API", True, False, "QUERY_API_KEY")
    assert real_license == (True, False, True, True)
    assert capabilities["historical_snapshot_semantics"] == "closest_snapshot_lte_requested"
    assert capabilities["historical_plan_requirement"] == "paid_plan"
    assert capabilities["paid_rate_limit_rps"] == "30"
