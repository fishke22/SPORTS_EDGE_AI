import json
from pathlib import Path

from sports_edge_ai.application.pricing import devig_multiplicative


def test_synthetic_moneyline_fixture_is_usable() -> None:
    path = Path(__file__).parents[1] / "fixtures" / "synthetic" / "nba_moneyline_snapshot.json"
    payload = json.loads(path.read_text(encoding="utf-8"))

    assert payload["event"]["event_id"].startswith("SYNTH_")
    fair = devig_multiplicative(payload["odds"])
    assert round(sum(fair.values()), 12) == 1.0
