from __future__ import annotations

from typing import Any

from sports_edge_ai.common.root import ProjectPaths
from sports_edge_ai.domain.schemas import PaperTradeRecord, SettlementRecord
from sports_edge_ai.infrastructure.db import connect, connect_readonly


def _trade_from_row(row: tuple[Any, ...]) -> PaperTradeRecord:
    return PaperTradeRecord(
        paper_trade_id=str(row[0]),
        prediction_id=str(row[1]),
        event_id=str(row[2]),
        market_id=str(row[3]),
        decision_at=row[4],
        odds_snapshot_id=str(row[5]),
        odds_decimal=float(row[6]),
        stake=float(row[7]),
        status=str(row[8]),
        model_version=str(row[9]),
        settlement_rule_version=str(row[10]),
    )


def persist_paper_trade(
    record: PaperTradeRecord,
    *,
    paths: ProjectPaths | None = None,
) -> None:
    connection = connect(paths)
    try:
        existing = connection.execute(
            "SELECT * FROM paper_trades WHERE paper_trade_id = ?",
            [record.paper_trade_id],
        ).fetchone()
        if existing is not None:
            if _trade_from_row(existing) != record:
                raise RuntimeError("paper trade id already exists with different content")
            return
        connection.execute(
            """
            INSERT INTO paper_trades VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                record.paper_trade_id,
                record.prediction_id,
                record.event_id,
                record.market_id,
                record.decision_at,
                record.odds_snapshot_id,
                record.odds_decimal,
                record.stake,
                record.status,
                record.model_version,
                record.settlement_rule_version,
            ],
        )
    finally:
        connection.close()


def list_open_paper_trades(
    *,
    event_id: str,
    paths: ProjectPaths | None = None,
) -> tuple[PaperTradeRecord, ...]:
    connection = connect_readonly(paths)
    try:
        rows = connection.execute(
            """
            SELECT * FROM paper_trades
            WHERE event_id = ? AND status = 'OPEN'
            ORDER BY decision_at, paper_trade_id
            """,
            [event_id],
        ).fetchall()
    finally:
        connection.close()
    return tuple(_trade_from_row(row) for row in rows)


def update_paper_trade_status(
    *,
    paper_trade_id: str,
    status: str,
    paths: ProjectPaths | None = None,
) -> None:
    connection = connect(paths)
    try:
        changed = connection.execute(
            """
            UPDATE paper_trades SET status = ? WHERE paper_trade_id = ?
            RETURNING paper_trade_id
            """,
            [status, paper_trade_id],
        ).fetchone()
        if changed is None:
            raise ValueError("paper trade not found")
    finally:
        connection.close()


def persist_settlement(
    record: SettlementRecord,
    *,
    paths: ProjectPaths | None = None,
) -> None:
    connection = connect(paths)
    try:
        existing = connection.execute(
            """
            SELECT settlement_id, paper_trade_id, event_id, market_id,
                   settlement_status, market_result, void_reason,
                   payout_rule_version, tax_rule_version, gross_payout,
                   net_payout, pnl, settled_at
            FROM settlements
            WHERE settlement_id = ?
            """,
            [record.settlement_id],
        ).fetchone()
        if existing is not None:
            existing_record = SettlementRecord(
                settlement_id=existing[0],
                paper_trade_id=existing[1],
                event_id=existing[2],
                market_id=existing[3],
                settlement_status=existing[4],
                market_result=existing[5],
                void_reason=existing[6],
                payout_rule_version=existing[7],
                tax_rule_version=existing[8],
                gross_payout=existing[9],
                net_payout=existing[10],
                pnl=existing[11],
                settled_at=existing[12],
            )
            if existing_record != record:
                raise RuntimeError("settlement id already exists with different content")
            return
        connection.execute(
            """
            INSERT INTO settlements (
                settlement_id, event_id, market_id, settlement_status,
                market_result, void_reason, payout_rule_version,
                tax_rule_version, gross_payout, net_payout, pnl,
                settled_at, paper_trade_id
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                record.settlement_id,
                record.event_id,
                record.market_id,
                record.settlement_status,
                record.market_result,
                record.void_reason,
                record.payout_rule_version,
                record.tax_rule_version,
                record.gross_payout,
                record.net_payout,
                record.pnl,
                record.settled_at,
                record.paper_trade_id,
            ],
        )
    finally:
        connection.close()


def get_settlement_for_trade(
    *,
    paper_trade_id: str,
    paths: ProjectPaths | None = None,
) -> SettlementRecord | None:
    connection = connect_readonly(paths)
    try:
        row = connection.execute(
            """
            SELECT settlement_id, paper_trade_id, event_id, market_id,
                   settlement_status, market_result, void_reason,
                   payout_rule_version, tax_rule_version, gross_payout,
                   net_payout, pnl, settled_at
            FROM settlements
            WHERE paper_trade_id = ?
            ORDER BY settled_at DESC
            LIMIT 1
            """,
            [paper_trade_id],
        ).fetchone()
    finally:
        connection.close()
    if row is None:
        return None
    return SettlementRecord(
        settlement_id=row[0],
        paper_trade_id=row[1],
        event_id=row[2],
        market_id=row[3],
        settlement_status=row[4],
        market_result=row[5],
        void_reason=row[6],
        payout_rule_version=row[7],
        tax_rule_version=row[8],
        gross_payout=row[9],
        net_payout=row[10],
        pnl=row[11],
        settled_at=row[12],
    )


def list_paper_trades(
    *,
    status: str | None = None,
    paths: ProjectPaths | None = None,
) -> tuple[PaperTradeRecord, ...]:
    connection = connect_readonly(paths)
    try:
        params: list[object] = []
        where = ""
        if status is not None:
            where = "WHERE status = ?"
            params.append(status)
        rows = connection.execute(
            f"""
            SELECT * FROM paper_trades
            {where}
            ORDER BY decision_at DESC, paper_trade_id
            """,
            params,
        ).fetchall()
    finally:
        connection.close()
    return tuple(_trade_from_row(row) for row in rows)


def list_settlements(
    *,
    paths: ProjectPaths | None = None,
) -> tuple[SettlementRecord, ...]:
    connection = connect_readonly(paths)
    try:
        rows = connection.execute(
            """
            SELECT settlement_id, paper_trade_id, event_id, market_id,
                   settlement_status, market_result, void_reason,
                   payout_rule_version, tax_rule_version, gross_payout,
                   net_payout, pnl, settled_at
            FROM settlements
            ORDER BY settled_at DESC, settlement_id
            """
        ).fetchall()
    finally:
        connection.close()
    return tuple(
        SettlementRecord(
            settlement_id=row[0],
            paper_trade_id=row[1],
            event_id=row[2],
            market_id=row[3],
            settlement_status=row[4],
            market_result=row[5],
            void_reason=row[6],
            payout_rule_version=row[7],
            tax_rule_version=row[8],
            gross_payout=row[9],
            net_payout=row[10],
            pnl=row[11],
            settled_at=row[12],
        )
        for row in rows
    )


def list_ready_paper_event_ids(
    *,
    paths: ProjectPaths | None = None,
) -> tuple[str, ...]:
    connection = connect_readonly(paths)
    try:
        rows = connection.execute(
            """
            SELECT DISTINCT trade.event_id
            FROM paper_trades trade
            JOIN event_results result
              ON result.event_id = trade.event_id
             AND result.completed = TRUE
            WHERE trade.status = 'OPEN'
            ORDER BY trade.event_id
            """
        ).fetchall()
    finally:
        connection.close()
    return tuple(str(row[0]) for row in rows)
