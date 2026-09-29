from __future__ import annotations

import asyncio
import shutil
from pathlib import Path

from mcp import Client

from sports_edge_ai.application.synthetic_pipeline import ingest_synthetic_snapshot
from sports_edge_ai.common.root import ProjectPaths
from sports_edge_ai.interfaces.mcp_server import mcp

PROJECT_ROOT = Path(__file__).parents[1]


def _portable_root(tmp_path: Path) -> ProjectPaths:
    root = tmp_path / "portable"
    migrations = root / "sql" / "migrations"
    migrations.mkdir(parents=True)
    (root / ".sports-edge-root").write_text("SPORTS_EDGE_AI\n", encoding="utf-8")
    for migration in (PROJECT_ROOT / "sql" / "migrations").glob("*.sql"):
        shutil.copy2(migration, migrations / migration.name)
    return ProjectPaths(root)


def test_mcp_tools_are_read_only_and_return_structured_json(
    tmp_path: Path,
    monkeypatch,
) -> None:
    paths = _portable_root(tmp_path)
    ingest_synthetic_snapshot(
        PROJECT_ROOT / "fixtures" / "synthetic" / "nba_moneyline_snapshot.json",
        paths=paths,
    )
    monkeypatch.setenv("SPORTS_EDGE_ROOT", str(paths.root))

    async def exercise() -> None:
        async with Client(mcp) as client:
            listed = await client.list_tools()
            assert listed.tools
            assert all(
                tool.annotations is not None
                and tool.annotations.read_only_hint is True
                and tool.annotations.open_world_hint is False
                and tool.output_schema is not None
                for tool in listed.tools
            )

            health = await client.call_tool("get_system_health_tool", {})
            assert health.is_error is False
            assert health.structured_content == {
                "status": "ok",
                "database_ready": True,
                "schema_version": "0009",
            }

            analysis = await client.call_tool(
                "get_market_analysis_tool",
                {
                    "event_id": "SYNTH_NBA_001",
                    "as_of": "2026-10-01T08:30:00Z",
                    "home_probability": 0.60,
                    "away_probability": 0.40,
                },
            )
            assert analysis.is_error is False
            assert analysis.structured_content is not None
            records = analysis.structured_content["records"]
            by_selection = {row["selection"]: row for row in records}
            assert by_selection["HOME"]["recommendation"] == "NO_VALIDATED_EDGE"
            assert by_selection["AWAY"]["recommendation"] == "NO_BET"

            entities = await client.call_tool(
                "get_canonical_entities_tool",
                {"entity_kind": "TEAM", "sport": "NBA", "entity_id_prefix": "NBA_"},
            )
            assert entities.is_error is False
            assert entities.structured_content is not None
            assert len(entities.structured_content["records"]) == 30

            proposals = await client.call_tool(
                "get_entity_proposals_tool",
                {"provider_id": "provider_the_odds_api", "status": "PENDING"},
            )
            assert proposals.is_error is False
            assert proposals.structured_content is not None
            assert proposals.structured_content["records"] == []

            summary = await client.call_tool(
                "get_mapping_review_summary_tool",
                {"provider_id": "provider_the_odds_api", "entity_kind": "TEAM"},
            )
            assert summary.is_error is False
            assert summary.structured_content is not None
            assert summary.structured_content["proposal_count"] == 0
            assert summary.structured_content["review_completion_rate"] == 1.0

            usage = await client.call_tool(
                "get_provider_usage_tool",
                {"provider_id": "provider_the_odds_api"},
            )
            assert usage.is_error is False
            assert usage.structured_content == {"found": False, "usage": None}

            collection = await client.call_tool(
                "get_forward_collection_status_tool",
                {"provider_id": "provider_the_odds_api"},
            )
            assert collection.is_error is False
            assert collection.structured_content is not None
            assert collection.structured_content["current_due"] is True
            assert collection.structured_content["scores_due"] is False
            assert collection.structured_content["latest_run"] is None

            readiness = await client.call_tool("get_nba_research_readiness_tool", {})
            assert readiness.is_error is False
            assert readiness.structured_content is not None
            assessment = readiness.structured_content["assessment"]
            assert assessment["readiness_status"] == "NOT_READY"
            assert assessment["usable_sample_count"] == 0
            assert assessment["evaluation_min_usable_samples"] == 180
            assert readiness.structured_content["latest_run"] is None

            operations = await client.call_tool("get_operational_status_tool", {})
            assert operations.is_error is False
            assert operations.structured_content is not None
            assert operations.structured_content["severity"] == "WARN"
            assert "collection_heartbeat_missing" in operations.structured_content["alerts"]

            result = await client.call_tool(
                "get_event_result_tool",
                {"event_id": "UNKNOWN_EVENT"},
            )
            assert result.is_error is False
            assert result.structured_content == {"found": False, "result": None}

            portfolio = await client.call_tool("get_paper_portfolio_tool", {})
            assert portfolio.is_error is False
            assert portfolio.structured_content is not None
            assert portfolio.structured_content["open_count"] == 0
            assert portfolio.structured_content["settled_count"] == 0
            assert portfolio.structured_content["realized_pnl"] == 0.0

    asyncio.run(exercise())
