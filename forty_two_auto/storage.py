from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

from .classifier import classify_market
from .quotes import QuoteResult


DEFAULT_DB_PATH = Path(__file__).resolve().parents[1] / "data" / "forty_two_auto.sqlite3"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def connect(db_path: str | Path = DEFAULT_DB_PATH) -> sqlite3.Connection:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 30000")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    init_db(conn)
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS markets (
            market_address TEXT PRIMARY KEY,
            question TEXT,
            slug TEXT,
            status TEXT,
            market_type TEXT,
            market_type_label TEXT,
            type_reason TEXT,
            start_date TEXT,
            end_date TEXT,
            volume REAL,
            total_market_cap REAL,
            traders INTEGER,
            oracle_name TEXT,
            raw_json TEXT NOT NULL,
            first_seen_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS outcomes (
            market_address TEXT NOT NULL,
            token_id TEXT NOT NULL,
            outcome_name TEXT,
            price REAL,
            payout REAL,
            volume REAL,
            market_cap REAL,
            raw_json TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (market_address, token_id)
        );

        CREATE TABLE IF NOT EXISTS market_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            observed_at TEXT NOT NULL,
            market_address TEXT NOT NULL,
            volume REAL,
            total_market_cap REAL,
            traders INTEGER,
            raw_json TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS outcome_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            observed_at TEXT NOT NULL,
            market_address TEXT NOT NULL,
            token_id TEXT NOT NULL,
            outcome_name TEXT,
            price REAL,
            payout REAL,
            volume REAL,
            market_cap REAL,
            raw_json TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS quotes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            market_address TEXT NOT NULL,
            token_id TEXT NOT NULL,
            side TEXT NOT NULL,
            amount_usdt REAL NOT NULL,
            price REAL,
            payout REAL,
            expected_tokens REAL,
            expected_collateral_usdt REAL,
            fee_usdt REAL,
            fee_rate REAL,
            slippage_bps REAL,
            gas_usdt REAL,
            confidence TEXT,
            executable INTEGER NOT NULL,
            reason TEXT,
            raw_json TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            mode TEXT NOT NULL,
            side TEXT NOT NULL,
            status TEXT NOT NULL,
            market_address TEXT NOT NULL,
            token_id TEXT NOT NULL,
            amount_usdt REAL NOT NULL,
            quote_id INTEGER,
            risk_reasons TEXT NOT NULL,
            raw_json TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS fills (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            order_id INTEGER NOT NULL,
            fill_type TEXT NOT NULL,
            amount_usdt REAL,
            token_amount REAL,
            price REAL,
            raw_json TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            event_type TEXT NOT NULL,
            payload_json TEXT NOT NULL
        );
        """
    )
    conn.commit()


def upsert_market(conn: sqlite3.Connection, market: Dict[str, Any], observed_at: Optional[str] = None) -> None:
    observed_at = observed_at or utc_now_iso()
    classification = classify_market(market)
    address = str(market.get("address") or "")
    if not address:
        return
    existing = conn.execute("SELECT first_seen_at FROM markets WHERE market_address = ?", (address,)).fetchone()
    first_seen_at = existing["first_seen_at"] if existing else observed_at
    conn.execute(
        """
        INSERT INTO markets
            (market_address, question, slug, status, market_type, market_type_label, type_reason,
             start_date, end_date, volume, total_market_cap, traders, oracle_name,
             raw_json, first_seen_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(market_address) DO UPDATE SET
            question=excluded.question,
            slug=excluded.slug,
            status=excluded.status,
            market_type=excluded.market_type,
            market_type_label=excluded.market_type_label,
            type_reason=excluded.type_reason,
            start_date=excluded.start_date,
            end_date=excluded.end_date,
            volume=excluded.volume,
            total_market_cap=excluded.total_market_cap,
            traders=excluded.traders,
            oracle_name=excluded.oracle_name,
            raw_json=excluded.raw_json,
            updated_at=excluded.updated_at
        """,
        (
            address,
            market.get("question"),
            market.get("slug"),
            market.get("status"),
            classification["market_type"],
            classification["market_type_label"],
            classification["type_reason"],
            market.get("startDate"),
            market.get("endDate"),
            _float_or_none(market.get("volume")),
            _float_or_none(market.get("totalMarketCap")),
            _int_or_none(market.get("traders")),
            (market.get("oracle") or {}).get("name") if isinstance(market.get("oracle"), dict) else None,
            json.dumps(market, ensure_ascii=False),
            first_seen_at,
            observed_at,
        ),
    )
    for outcome in market.get("outcomes") or []:
        upsert_outcome(conn, address, outcome, observed_at)
    insert_market_snapshot(conn, market, observed_at)


def upsert_outcome(conn: sqlite3.Connection, market_address: str, outcome: Dict[str, Any], observed_at: str) -> None:
    token_id = str(outcome.get("tokenId") or outcome.get("token_id") or "")
    if not token_id:
        return
    conn.execute(
        """
        INSERT INTO outcomes
            (market_address, token_id, outcome_name, price, payout, volume, market_cap, raw_json, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(market_address, token_id) DO UPDATE SET
            outcome_name=excluded.outcome_name,
            price=excluded.price,
            payout=excluded.payout,
            volume=excluded.volume,
            market_cap=excluded.market_cap,
            raw_json=excluded.raw_json,
            updated_at=excluded.updated_at
        """,
        (
            market_address,
            token_id,
            outcome.get("name") or outcome.get("outcome"),
            _float_or_none(outcome.get("price")),
            _float_or_none(outcome.get("payout")),
            _float_or_none(outcome.get("volume")),
            _float_or_none(outcome.get("marketCap")),
            json.dumps(outcome, ensure_ascii=False),
            observed_at,
        ),
    )
    conn.execute(
        """
        INSERT INTO outcome_snapshots
            (observed_at, market_address, token_id, outcome_name, price, payout, volume, market_cap, raw_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            observed_at,
            market_address,
            token_id,
            outcome.get("name") or outcome.get("outcome"),
            _float_or_none(outcome.get("price")),
            _float_or_none(outcome.get("payout")),
            _float_or_none(outcome.get("volume")),
            _float_or_none(outcome.get("marketCap")),
            json.dumps(outcome, ensure_ascii=False),
        ),
    )


def insert_market_snapshot(conn: sqlite3.Connection, market: Dict[str, Any], observed_at: str) -> None:
    conn.execute(
        """
        INSERT INTO market_snapshots
            (observed_at, market_address, volume, total_market_cap, traders, raw_json)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            observed_at,
            market.get("address"),
            _float_or_none(market.get("volume")),
            _float_or_none(market.get("totalMarketCap")),
            _int_or_none(market.get("traders")),
            json.dumps(market, ensure_ascii=False),
        ),
    )


def upsert_markets(conn: sqlite3.Connection, markets: Iterable[Dict[str, Any]]) -> int:
    observed_at = utc_now_iso()
    count = 0
    with conn:
        for market in markets:
            upsert_market(conn, market, observed_at)
            count += 1
    return count


def insert_quote(conn: sqlite3.Connection, quote: QuoteResult) -> int:
    payload = quote.to_dict()
    with conn:
        cur = conn.execute(
            """
            INSERT INTO quotes
                (created_at, market_address, token_id, side, amount_usdt, price, payout,
                 expected_tokens, expected_collateral_usdt, fee_usdt, fee_rate, slippage_bps,
                 gas_usdt, confidence, executable, reason, raw_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                quote.created_at,
                quote.market_address,
                quote.token_id,
                quote.side,
                quote.amount_usdt,
                quote.price,
                quote.payout,
                quote.expected_tokens,
                quote.expected_collateral_usdt,
                quote.fee_usdt,
                quote.fee_rate,
                quote.slippage_bps,
                quote.gas_usdt,
                quote.confidence,
                1 if quote.executable else 0,
                quote.reason,
                json.dumps(payload, ensure_ascii=False),
            ),
        )
    return int(cur.lastrowid)


def insert_order(
    conn: sqlite3.Connection,
    mode: str,
    side: str,
    status: str,
    market_address: str,
    token_id: str,
    amount_usdt: float,
    quote_id: Optional[int],
    risk_reasons: list[str],
    raw: Dict[str, Any],
) -> int:
    with conn:
        cur = conn.execute(
            """
            INSERT INTO orders
                (created_at, mode, side, status, market_address, token_id, amount_usdt,
                 quote_id, risk_reasons, raw_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                utc_now_iso(),
                mode,
                side,
                status,
                market_address,
                token_id,
                amount_usdt,
                quote_id,
                json.dumps(risk_reasons, ensure_ascii=False),
                json.dumps(raw, ensure_ascii=False),
            ),
        )
    return int(cur.lastrowid)


def insert_fill(
    conn: sqlite3.Connection,
    order_id: int,
    fill_type: str,
    amount_usdt: float,
    token_amount: float,
    price: float,
    raw: Dict[str, Any],
) -> int:
    with conn:
        cur = conn.execute(
            """
            INSERT INTO fills
                (created_at, order_id, fill_type, amount_usdt, token_amount, price, raw_json)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                utc_now_iso(),
                order_id,
                fill_type,
                amount_usdt,
                token_amount,
                price,
                json.dumps(raw, ensure_ascii=False),
            ),
        )
    return int(cur.lastrowid)


def audit(conn: sqlite3.Connection, event_type: str, payload: Dict[str, Any]) -> None:
    with conn:
        conn.execute(
            "INSERT INTO audit_log (created_at, event_type, payload_json) VALUES (?, ?, ?)",
            (utc_now_iso(), event_type, json.dumps(payload, ensure_ascii=False)),
        )


def latest_report(conn: sqlite3.Connection) -> Dict[str, Any]:
    market_count = conn.execute("SELECT count(*) AS n FROM markets").fetchone()["n"]
    order_count = conn.execute("SELECT count(*) AS n FROM orders").fetchone()["n"]
    fill_count = conn.execute("SELECT count(*) AS n FROM fills").fetchone()["n"]
    quote_count = conn.execute("SELECT count(*) AS n FROM quotes").fetchone()["n"]
    by_type = [
        dict(row)
        for row in conn.execute(
            """
            SELECT market_type, count(*) AS markets, round(sum(COALESCE(volume, 0)), 2) AS volume
            FROM markets
            GROUP BY market_type
            ORDER BY volume DESC
            """
        ).fetchall()
    ]
    recent_orders = [
        dict(row)
        for row in conn.execute(
            """
            SELECT created_at, mode, side, status, market_address, token_id, amount_usdt, risk_reasons
            FROM orders
            ORDER BY id DESC
            LIMIT 10
            """
        ).fetchall()
    ]
    return {
        "markets": market_count,
        "quotes": quote_count,
        "orders": order_count,
        "fills": fill_count,
        "by_type": by_type,
        "recent_orders": recent_orders,
    }


def _float_or_none(value: Any) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int_or_none(value: Any) -> Optional[int]:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None
