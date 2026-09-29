from __future__ import annotations

import hashlib
from datetime import datetime

from sports_edge_ai.common.root import ProjectPaths
from sports_edge_ai.domain.schemas import (
    DataQualityStatus,
    PaperTradeRecord,
    PredictionRecord,
    Recommendation,
    SettlementRecord,
)
from sports_edge_ai.infrastructure.db import connect_readonly, migrate
from sports_edge_ai.infrastructure.model_repository import get_model_registry_record
from sports_edge_ai.infrastructure.paper_trade_repository import (
    list_open_paper_trades,
    persist_paper_trade,
    persist_settlement,
    update_paper_trade_status,
)
from sports_edge_ai.infrastructure.prediction_repository import persist_prediction_record
from sports_edge_ai.infrastructure.result_repository import get_latest_event_result


def open_paper_trade(
    *,
    prediction: PredictionRecord,
    odds_snapshot_id: str,
    stake: float,
    paths: ProjectPaths | None = None,
    settlement_rule_version: str = "paper-moneyline-v1",
) -> PaperTradeRecord:
    effective_paths = paths or ProjectPaths.discover()
    migrate(effective_paths)
    if stake <= 0.0:
        raise ValueError("stake must be positive")
    if prediction.generated_at > prediction.as_of:
        raise ValueError("prediction generated_at must not exceed as_of")
    if prediction.recommendation is not Recommendation.EDGE:
        raise ValueError("paper trade requires EDGE recommendation")
    if prediction.data_quality is not DataQualityStatus.GREEN:
        raise ValueError("paper trade requires GREEN data quality")
    if prediction.net_ev <= 0.0:
        raise ValueError("paper trade requires positive net EV")

    registry = get_model_registry_record(
        model_id=prediction.model_id,
        model_version=prediction.model_version,
        paths=effective_paths,
    )
    if registry is None or registry.status != "VALIDATED":
        raise ValueError("paper trade requires model_registry status VALIDATED")

    connection = connect_readonly(effective_paths)
    try:
        snapshot = connection.execute(
            """
            SELECT event_id, market_id, decimal_odds, observed_at,
                   provider_timestamp, is_live, bookmaker, source
            FROM odds_snapshots
            WHERE odds_snapshot_id = ?
            """,
            [odds_snapshot_id],
        ).fetchone()
    finally:
        connection.close()
    if snapshot is None:
        raise ValueError("odds snapshot not found")
    if snapshot[0] != prediction.event_id or snapshot[1] != prediction.market_id:
        raise ValueError("odds snapshot does not match prediction event/market")
    if snapshot[3] > prediction.as_of:
        raise ValueError("odds snapshot was not observable at prediction as_of")
    if snapshot[4] is not None and snapshot[4] > prediction.as_of:
        raise ValueError("provider timestamp exceeds prediction as_of")
    if bool(snapshot[5]):
        raise ValueError("automatic paper-trade opening from live odds is disabled")
    if prediction.odds_snapshot_id is not None and prediction.odds_snapshot_id != odds_snapshot_id:
        raise ValueError("odds snapshot does not match prediction provenance")
    if prediction.bookmaker is not None and prediction.bookmaker != snapshot[6]:
        raise ValueError("bookmaker does not match prediction provenance")
    if prediction.source is not None and prediction.source != snapshot[7]:
        raise ValueError("source does not match prediction provenance")

    odds_decimal = float(snapshot[2])
    material = (
        f"{prediction.prediction_id}|{odds_snapshot_id}|{stake:.12g}|{settlement_rule_version}"
    ).encode()
    record = PaperTradeRecord(
        paper_trade_id=hashlib.sha256(material).hexdigest()[:32],
        prediction_id=prediction.prediction_id,
        event_id=prediction.event_id,
        market_id=prediction.market_id,
        decision_at=prediction.as_of,
        odds_snapshot_id=odds_snapshot_id,
        odds_decimal=odds_decimal,
        stake=stake,
        status="OPEN",
        model_version=prediction.model_version,
        settlement_rule_version=settlement_rule_version,
    )
    persist_prediction_record(prediction, paths=effective_paths)
    persist_paper_trade(record, paths=effective_paths)
    return record


def settle_open_paper_trades(
    *,
    event_id: str,
    settled_at: datetime,
    paths: ProjectPaths | None = None,
) -> tuple[SettlementRecord, ...]:
    if settled_at.tzinfo is None or settled_at.utcoffset() is None:
        raise ValueError("settled_at must be timezone-aware")
    effective_paths = paths or ProjectPaths.discover()
    migrate(effective_paths)
    result = get_latest_event_result(event_id=event_id, paths=effective_paths)
    if result is None or not result.completed or result.result_outcome is None:
        return ()
    if result.observed_at > settled_at:
        raise ValueError("result was not observable at settled_at")

    trades = list_open_paper_trades(event_id=event_id, paths=effective_paths)
    settlements: list[SettlementRecord] = []
    for trade in trades:
        if trade.settlement_rule_version != "paper-moneyline-v1":
            raise ValueError("unsupported paper settlement rule version")
        if settled_at < trade.decision_at:
            raise ValueError("settled_at must not precede paper trade decision_at")
        connection = connect_readonly(effective_paths)
        try:
            market = connection.execute(
                """
                SELECT market_type, period, selection
                FROM canonical_markets
                WHERE market_id = ?
                """,
                [trade.market_id],
            ).fetchone()
        finally:
            connection.close()
        if market is None:
            raise ValueError("canonical market not found for paper trade")
        if market[0] != "MONEYLINE" or market[1] != "FULL_GAME":
            raise ValueError("paper settlement currently supports full-game moneyline only")

        selection = str(market[2])
        if result.result_outcome == "TIE":
            status = "VOID"
            void_reason = "TIE_UNSUPPORTED"
            gross_payout = trade.stake
        elif selection == result.result_outcome:
            status = "WIN"
            void_reason = None
            gross_payout = trade.stake * trade.odds_decimal
        else:
            status = "LOSE"
            void_reason = None
            gross_payout = 0.0
        net_payout = gross_payout
        pnl = net_payout - trade.stake
        material = (
            f"{trade.paper_trade_id}|{result.event_result_id}|paper-decimal-v1|paper-no-tax-v1"
        ).encode()
        settlement = SettlementRecord(
            settlement_id=hashlib.sha256(material).hexdigest()[:32],
            paper_trade_id=trade.paper_trade_id,
            event_id=trade.event_id,
            market_id=trade.market_id,
            settlement_status=status,
            market_result=result.result_outcome,
            void_reason=void_reason,
            payout_rule_version="paper-decimal-v1",
            tax_rule_version="paper-no-tax-v1",
            gross_payout=gross_payout,
            net_payout=net_payout,
            pnl=pnl,
            settled_at=settled_at,
        )
        persist_settlement(settlement, paths=effective_paths)
        update_paper_trade_status(
            paper_trade_id=trade.paper_trade_id,
            status="VOID" if status == "VOID" else "SETTLED",
            paths=effective_paths,
        )
        settlements.append(settlement)
    return tuple(settlements)
