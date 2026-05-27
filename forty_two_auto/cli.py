from __future__ import annotations

import argparse
import importlib
import json
import os
import sys
import time
from dataclasses import asdict
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

from .classifier import classify_market
from .execution import (
    DryRunExecutionAdapter,
    LiveExecutionAdapter,
    OrderRequest,
    PaperExecutionAdapter,
    quote_request_from_order,
)
from .market_data import FortyTwoClient
from .execution_paths import check_execution_paths
from .modes import automation_modes
from .onchain import OnchainClient, load_onchain_config
from .quotes import EstimatedQuoteProvider, find_outcome
from .risk import RiskConfig
from .storage import audit, connect, latest_report, upsert_markets
from .strategy import run_strategy


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not hasattr(args, "func"):
        parser.print_help()
        return 2
    return int(args.func(args))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="42auto", description="Open 42space automation framework.")
    parser.add_argument("--db", default=str(Path("data") / "forty_two_auto.sqlite3"))
    sub = parser.add_subparsers(dest="command")

    scan = sub.add_parser("scan", help="Scan 42 markets.")
    scan_sub = scan.add_subparsers(dest="scan_command")
    scan_once = scan_sub.add_parser("once", help="Scan live markets once.")
    scan_once.add_argument("--limit", type=int, default=500)
    scan_once.add_argument("--status", default="live")
    scan_once.add_argument("--json", action="store_true")
    scan_once.set_defaults(func=cmd_scan_once)

    scan_loop = scan_sub.add_parser("loop", help="Scan live markets repeatedly.")
    scan_loop.add_argument("--limit", type=int, default=500)
    scan_loop.add_argument("--status", default="live")
    scan_loop.add_argument("--interval", type=float, default=10.0)
    scan_loop.add_argument("--iterations", type=int, default=0, help="0 means run forever")
    scan_loop.set_defaults(func=cmd_scan_loop)

    quote = sub.add_parser("quote", help="Create a buy/sell quote.")
    add_order_args(quote)
    quote.set_defaults(func=cmd_quote)

    paper = sub.add_parser("paper", help="Record a paper buy/sell.")
    paper_sub = paper.add_subparsers(dest="paper_side")
    for side in ("buy", "sell"):
        node = paper_sub.add_parser(side)
        add_order_args(node, default_side=side)
        node.set_defaults(func=cmd_paper)

    plan = sub.add_parser("plan-order", help="Record a dry-run buy/sell plan.")
    plan_sub = plan.add_subparsers(dest="plan_side")
    for side in ("buy", "sell"):
        node = plan_sub.add_parser(side)
        add_order_args(node, default_side=side)
        node.set_defaults(func=cmd_plan_order)

    live = sub.add_parser("live", help="Attempt a gated live buy/sell.")
    live_sub = live.add_subparsers(dest="live_side")
    for side in ("buy", "sell"):
        node = live_sub.add_parser(side)
        add_order_args(node, default_side=side)
        node.add_argument("--enable-live", action="store_true")
        node.add_argument("--confirm-compliance", action="store_true")
        node.set_defaults(func=cmd_live)

    strategy = sub.add_parser("strategy", help="Run a third-party strategy.")
    strategy_sub = strategy.add_subparsers(dest="strategy_command")
    strategy_run = strategy_sub.add_parser("run", help="Scan markets and run a strategy class.")
    strategy_run.add_argument("--strategy", required=True, help="Import path such as examples.simple_strategy:ExampleStrategy")
    strategy_run.add_argument("--mode", default="paper", choices=["paper", "dry-run", "live"])
    strategy_run.add_argument("--limit", type=int, default=50)
    strategy_run.add_argument("--status", default="live")
    strategy_run.add_argument("--enable-live", action="store_true")
    strategy_run.add_argument("--confirm-compliance", action="store_true")
    strategy_run.add_argument("--json", action="store_true")
    strategy_run.set_defaults(func=cmd_strategy_run)

    onchain = sub.add_parser("onchain", help="On-chain readiness and transaction tools.")
    onchain_sub = onchain.add_subparsers(dest="onchain_command")
    onchain_check = onchain_sub.add_parser("check", help="Check wallet, chain, BUSDT balance, and allowance.")
    onchain_check.add_argument("--env", default=".env")
    onchain_check.set_defaults(func=cmd_onchain_check)
    onchain_approve = onchain_sub.add_parser("approve-busdt", help="Build or optionally send a BUSDT approval transaction for FTRouter.")
    onchain_approve.add_argument("--env", default=".env")
    onchain_approve.add_argument("--amount-usdt", required=True, type=Decimal)
    onchain_approve.add_argument("--send", action="store_true")
    onchain_approve.add_argument("--i-understand-real-money", action="store_true")
    onchain_approve.set_defaults(func=cmd_onchain_approve_busdt)
    onchain_revoke_busdt = onchain_sub.add_parser("revoke-busdt", help="Build or optionally send BUSDT approval reset to zero.")
    onchain_revoke_busdt.add_argument("--env", default=".env")
    onchain_revoke_busdt.add_argument("--send", action="store_true")
    onchain_revoke_busdt.add_argument("--i-understand-real-money", action="store_true")
    onchain_revoke_busdt.set_defaults(func=cmd_onchain_revoke_busdt)
    onchain_buy = onchain_sub.add_parser("build-buy", help="Build or optionally send a FTRouter swap buy transaction.")
    onchain_buy.add_argument("--env", default=".env")
    onchain_buy.add_argument("--market", required=True, dest="market_address")
    onchain_buy.add_argument("--token", required=True, dest="token_id", type=int)
    onchain_buy.add_argument("--amount-usdt", required=True, type=Decimal)
    onchain_buy.add_argument("--min-out", default=0, type=int, help="Minimum output token units accepted by FTRouter.")
    onchain_buy.add_argument("--send", action="store_true")
    onchain_buy.add_argument("--i-understand-real-money", action="store_true")
    onchain_buy.set_defaults(func=cmd_onchain_build_buy)
    onchain_approve_outcome = onchain_sub.add_parser("approve-outcome", help="Build or optionally send an outcome-token approval for FTRouter.")
    onchain_approve_outcome.add_argument("--env", default=".env")
    onchain_approve_outcome.add_argument("--market", required=True, dest="market_address")
    onchain_approve_outcome.add_argument("--token", required=True, dest="token_id", type=int)
    onchain_approve_outcome.add_argument("--amount-tokens", required=True, type=Decimal)
    onchain_approve_outcome.add_argument("--send", action="store_true")
    onchain_approve_outcome.add_argument("--i-understand-real-money", action="store_true")
    onchain_approve_outcome.set_defaults(func=cmd_onchain_approve_outcome)
    onchain_revoke_outcome = onchain_sub.add_parser("revoke-outcome", help="Build or optionally send outcome-token approval reset to zero.")
    onchain_revoke_outcome.add_argument("--env", default=".env")
    onchain_revoke_outcome.add_argument("--market", required=True, dest="market_address")
    onchain_revoke_outcome.add_argument("--token", required=True, dest="token_id", type=int)
    onchain_revoke_outcome.add_argument("--send", action="store_true")
    onchain_revoke_outcome.add_argument("--i-understand-real-money", action="store_true")
    onchain_revoke_outcome.set_defaults(func=cmd_onchain_revoke_outcome)
    onchain_sell = onchain_sub.add_parser("build-sell", help="Build or optionally send a FTRouter swap sell/redeem transaction.")
    onchain_sell.add_argument("--env", default=".env")
    onchain_sell.add_argument("--market", required=True, dest="market_address")
    onchain_sell.add_argument("--token", required=True, dest="token_id", type=int)
    onchain_sell.add_argument("--amount-tokens", required=True, type=Decimal)
    onchain_sell.add_argument("--min-out", default=0, type=int, help="Minimum collateral units accepted from redeem.")
    onchain_sell.add_argument("--send", action="store_true")
    onchain_sell.add_argument("--i-understand-real-money", action="store_true")
    onchain_sell.set_defaults(func=cmd_onchain_build_sell)
    onchain_positions = onchain_sub.add_parser("positions", help="Read outcome token balances for a market.")
    onchain_positions.add_argument("--env", default=".env")
    onchain_positions.add_argument("--market", required=True, dest="market_address")
    onchain_positions.add_argument("--tokens", default="1,2,4", help="Comma-separated token ids, for example 1,2,4.")
    onchain_positions.set_defaults(func=cmd_onchain_positions)

    report = sub.add_parser("report", help="Print a local framework report.")
    report.add_argument("--json", action="store_true")
    report.set_defaults(func=cmd_report)

    paths = sub.add_parser("paths", help="Diagnose available execution paths.")
    paths.add_argument("--env", default=".env")
    paths.add_argument("--json", action="store_true")
    paths.add_argument("--skip-network", action="store_true")
    paths.set_defaults(func=cmd_paths)

    modes = sub.add_parser("modes", help="List framework automation modes.")
    modes.add_argument("--json", action="store_true")
    modes.set_defaults(func=cmd_modes)
    return parser


def add_order_args(parser: argparse.ArgumentParser, default_side: Optional[str] = None) -> None:
    parser.add_argument("--market", required=True, dest="market_address")
    parser.add_argument("--token", required=True, dest="token_id")
    if default_side:
        parser.set_defaults(side=default_side)
    else:
        parser.add_argument("--side", required=True, choices=["buy", "sell"])
    parser.add_argument("--amount-usdt", required=True, type=float)


def cmd_scan_once(args: argparse.Namespace) -> int:
    client = FortyTwoClient()
    markets, pagination = client.markets(status=args.status, limit=args.limit)
    conn = connect(args.db)
    count = upsert_markets(conn, markets)
    audit(conn, "scan_once", {"count": count, "status": args.status, "pagination": pagination})
    rows = [_market_summary(market) for market in markets]
    if args.json:
        print(json.dumps({"count": count, "markets": rows, "pagination": pagination}, ensure_ascii=False, indent=2))
    else:
        print(f"scanned={count}")
        for row in rows[:20]:
            print(f"{row['market_type']}\t{row['volume']:.2f}\t{row['address']}\t{row['question']}")
    return 0


def cmd_scan_loop(args: argparse.Namespace) -> int:
    iterations = 0
    while True:
        cmd_scan_once(args)
        iterations += 1
        if args.iterations and iterations >= args.iterations:
            return 0
        time.sleep(args.interval)


def cmd_quote(args: argparse.Namespace) -> int:
    quote = _build_quote(args)
    conn = connect(args.db)
    from .storage import insert_quote

    insert_quote(conn, quote)
    print(json.dumps(quote.to_dict(), ensure_ascii=False, indent=2))
    return 0


def cmd_paper(args: argparse.Namespace) -> int:
    return _run_order(args, PaperExecutionAdapter(), RiskConfig())


def cmd_plan_order(args: argparse.Namespace) -> int:
    return _run_order(args, DryRunExecutionAdapter(), RiskConfig())


def cmd_live(args: argparse.Namespace) -> int:
    config = RiskConfig(live_enabled=bool(args.enable_live), compliance_confirmed=bool(args.confirm_compliance))
    return _run_order(args, LiveExecutionAdapter(), config)


def cmd_strategy_run(args: argparse.Namespace) -> int:
    strategy = _load_strategy(args.strategy)
    client = FortyTwoClient()
    markets, pagination = client.markets(status=args.status, limit=args.limit)
    conn = connect(args.db)
    risk_config = RiskConfig(
        live_enabled=bool(args.enable_live),
        compliance_confirmed=bool(args.confirm_compliance),
    )
    results = run_strategy(conn, markets, strategy, mode=args.mode, risk_config=risk_config)
    payload = {
        "mode": args.mode,
        "market_count": len(markets),
        "pagination": pagination,
        "result_count": len(results),
        "results": [result.to_dict() for result in results],
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"mode={args.mode} markets={len(markets)} results={len(results)}")
        for result in results:
            reasons = "; ".join(result.risk.reasons)
            print(f"{result.status}\t{result.side}\t{result.quote.market_address}\t{result.quote.token_id}\t{reasons}")
    return 0 if all(result.status not in ("rejected", "blocked") for result in results) else 1


def cmd_report(args: argparse.Namespace) -> int:
    conn = connect(args.db)
    report = latest_report(conn)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print("# 42auto Report")
        print(f"markets: {report['markets']}")
        print(f"quotes: {report['quotes']}")
        print(f"orders: {report['orders']}")
        print(f"fills: {report['fills']}")
        print("\n## Markets By Type")
        for row in report["by_type"]:
            print(f"- {row['market_type']}: {row['markets']} markets, volume {row['volume']}")
        print("\n## Recent Orders")
        for row in report["recent_orders"]:
            print(f"- {row['created_at']} {row['mode']} {row['side']} {row['status']} {row['market_address']} {row['token_id']} {row['amount_usdt']}")
    return 0


def cmd_paths(args: argparse.Namespace) -> int:
    statuses = check_execution_paths(args.env, include_network=not args.skip_network)
    rows = [status.to_dict() for status in statuses]
    if args.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
    else:
        print("# Execution Paths")
        for row in rows:
            print(f"- {row['priority']} {row['path']}: {row['status']}")
            print(f"  adapter: {row['open_source_adapter']}")
            print(f"  evidence: {row['evidence']}")
            print(f"  next: {row['next_step']}")
            print(f"  boundary: {row['boundary']}")
    return 0


def cmd_modes(args: argparse.Namespace) -> int:
    modes = [mode.to_dict() for mode in automation_modes()]
    if args.json:
        print(json.dumps(modes, ensure_ascii=False, indent=2))
    else:
        print("# Automation Modes")
        for mode in modes:
            sends = "sends tx" if mode["sends_transaction"] else "no tx"
            print(f"- L{mode['level']} {mode['name']} [{mode['status']}, {sends}]")
            print(f"  purpose: {mode['purpose']}")
            print(f"  next: {mode['next_step']}")
            print(f"  boundary: {mode['boundary']}")
    return 0


def cmd_onchain_check(args: argparse.Namespace) -> int:
    try:
        client = OnchainClient(load_onchain_config(args.env))
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    check = client.check()
    print(json.dumps(check.__dict__, ensure_ascii=False, indent=2))
    if check.chain_id != 56:
        print("wrong chain id; expected BNB Chain 56", file=sys.stderr)
        return 1
    return 0


def cmd_onchain_build_buy(args: argparse.Namespace) -> int:
    try:
        client = OnchainClient(load_onchain_config(args.env))
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    check = client.check()
    if check.chain_id != 56:
        print("wrong chain id; expected BNB Chain 56", file=sys.stderr)
        return 1
    if check.busdt_balance < float(args.amount_usdt):
        print("BUSDT balance is lower than requested amount", file=sys.stderr)
        return 1
    if check.busdt_allowance_to_router < float(args.amount_usdt):
        print("BUSDT allowance is lower than requested amount; run onchain approve-busdt first", file=sys.stderr)
        return 1
    tx = client.build_buy_tx(args.market_address, args.token_id, args.amount_usdt, min_out=args.min_out)
    payload = {"transaction": _json_safe_tx(tx), "sent": False}
    try:
        payload["cost"] = _cost_to_dict(client.simulate_mint_cost(args.market_address, args.token_id, args.amount_usdt, tx=tx))
    except Exception as exc:
        payload["cost_error"] = str(exc)
    if args.send:
        if not _send_allowed(args):
            print(_send_gate_message(), file=sys.stderr)
            print(json.dumps(payload, ensure_ascii=False, indent=2))
            return 1
        if "cost_error" in payload:
            print("cost/gas estimation failed; refusing to send", file=sys.stderr)
            print(json.dumps(payload, ensure_ascii=False, indent=2))
            return 1
        tx_hash = client.send_transaction(tx)
        payload["sent"] = True
        payload["tx_hash"] = tx_hash
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def cmd_onchain_build_sell(args: argparse.Namespace) -> int:
    try:
        client = OnchainClient(load_onchain_config(args.env))
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    check = client.check()
    if check.chain_id != 56:
        print("wrong chain id; expected BNB Chain 56", file=sys.stderr)
        return 1
    position = client.outcome_position(args.market_address, args.token_id)
    if Decimal(str(position.balance)) < args.amount_tokens:
        print("outcome token balance is lower than requested amount", file=sys.stderr)
        print(json.dumps(position.__dict__, ensure_ascii=False, indent=2))
        return 1
    if Decimal(str(position.allowance_to_router)) < args.amount_tokens:
        print("outcome token allowance is lower than requested amount; run onchain approve-outcome first", file=sys.stderr)
        print(json.dumps(position.__dict__, ensure_ascii=False, indent=2))
        return 1
    tx = client.build_sell_tx(args.market_address, args.token_id, args.amount_tokens, min_out=args.min_out)
    payload = {"transaction": _json_safe_tx(tx), "sent": False, "position_before": position.__dict__}
    try:
        payload["cost"] = _cost_to_dict(client.simulate_redeem_cost(args.market_address, args.token_id, args.amount_tokens, tx=tx))
    except Exception as exc:
        payload["cost_error"] = str(exc)
    if args.send:
        if not _send_allowed(args):
            print(_send_gate_message(), file=sys.stderr)
            print(json.dumps(payload, ensure_ascii=False, indent=2))
            return 1
        if "cost_error" in payload:
            print("cost/gas estimation failed; refusing to send", file=sys.stderr)
            print(json.dumps(payload, ensure_ascii=False, indent=2))
            return 1
        tx_hash = client.send_transaction(tx)
        payload["sent"] = True
        payload["tx_hash"] = tx_hash
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def cmd_onchain_approve_busdt(args: argparse.Namespace) -> int:
    try:
        client = OnchainClient(load_onchain_config(args.env))
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    check = client.check()
    if check.chain_id != 56:
        print("wrong chain id; expected BNB Chain 56", file=sys.stderr)
        return 1
    tx = client.build_approve_busdt_tx(args.amount_usdt)
    payload = {"transaction": _json_safe_tx(tx), "sent": False}
    try:
        payload["gas_cost"] = asdict(client.estimate_tx_cost(tx))
    except Exception as exc:
        payload["cost_error"] = str(exc)
    if args.send:
        if not _send_allowed(args):
            print(_send_gate_message(), file=sys.stderr)
            print(json.dumps(payload, ensure_ascii=False, indent=2))
            return 1
        if "cost_error" in payload:
            print("gas estimation failed; refusing to send", file=sys.stderr)
            print(json.dumps(payload, ensure_ascii=False, indent=2))
            return 1
        tx_hash = client.send_transaction(tx)
        payload["sent"] = True
        payload["tx_hash"] = tx_hash
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def cmd_onchain_revoke_busdt(args: argparse.Namespace) -> int:
    args.amount_usdt = Decimal("0")
    return cmd_onchain_approve_busdt(args)


def cmd_onchain_approve_outcome(args: argparse.Namespace) -> int:
    try:
        client = OnchainClient(load_onchain_config(args.env))
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    check = client.check()
    if check.chain_id != 56:
        print("wrong chain id; expected BNB Chain 56", file=sys.stderr)
        return 1
    position = client.outcome_position(args.market_address, args.token_id)
    if position.raw_balance <= 0:
        print("no outcome token balance to approve", file=sys.stderr)
        print(json.dumps(position.__dict__, ensure_ascii=False, indent=2))
        return 1
    tx = client.build_approve_outcome_tx(args.market_address, args.token_id, args.amount_tokens)
    payload = {"transaction": _json_safe_tx(tx), "sent": False, "position_before": position.__dict__}
    try:
        payload["gas_cost"] = asdict(client.estimate_tx_cost(tx))
    except Exception as exc:
        payload["cost_error"] = str(exc)
    if args.send:
        if not _send_allowed(args):
            print(_send_gate_message(), file=sys.stderr)
            print(json.dumps(payload, ensure_ascii=False, indent=2))
            return 1
        if "cost_error" in payload:
            print("gas estimation failed; refusing to send", file=sys.stderr)
            print(json.dumps(payload, ensure_ascii=False, indent=2))
            return 1
        tx_hash = client.send_transaction(tx)
        payload["sent"] = True
        payload["tx_hash"] = tx_hash
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def cmd_onchain_revoke_outcome(args: argparse.Namespace) -> int:
    try:
        client = OnchainClient(load_onchain_config(args.env))
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    check = client.check()
    if check.chain_id != 56:
        print("wrong chain id; expected BNB Chain 56", file=sys.stderr)
        return 1
    position = client.outcome_position(args.market_address, args.token_id)
    tx = client.build_approve_outcome_tx(args.market_address, args.token_id, Decimal("0"))
    payload = {"transaction": _json_safe_tx(tx), "sent": False, "position_before": position.__dict__}
    try:
        payload["gas_cost"] = asdict(client.estimate_tx_cost(tx))
    except Exception as exc:
        payload["cost_error"] = str(exc)
    if args.send:
        if not _send_allowed(args):
            print(_send_gate_message(), file=sys.stderr)
            print(json.dumps(payload, ensure_ascii=False, indent=2))
            return 1
        if "cost_error" in payload:
            print("gas estimation failed; refusing to send", file=sys.stderr)
            print(json.dumps(payload, ensure_ascii=False, indent=2))
            return 1
        tx_hash = client.send_transaction(tx)
        payload["sent"] = True
        payload["tx_hash"] = tx_hash
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def cmd_onchain_positions(args: argparse.Namespace) -> int:
    try:
        client = OnchainClient(load_onchain_config(args.env))
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    token_ids = [int(part.strip()) for part in str(args.tokens).split(",") if part.strip()]
    payload = {
        "wallet_address": client.account.address,
        "market_address": args.market_address,
        "positions": [client.outcome_position(args.market_address, token_id).__dict__ for token_id in token_ids],
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def _run_order(args: argparse.Namespace, adapter, risk_config: RiskConfig) -> int:
    quote = _build_quote(args)
    conn = connect(args.db)
    order = OrderRequest(
        market_address=args.market_address,
        token_id=args.token_id,
        side=args.side,
        amount_usdt=args.amount_usdt,
        mode=adapter.mode,
    )
    result = adapter.execute(conn, order, quote, risk_config)
    print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    return 0 if result.status not in ("rejected", "blocked") else 1


def _build_quote(args: argparse.Namespace):
    client = FortyTwoClient()
    market = client.market(args.market_address)
    if not market:
        raise SystemExit(f"market not found: {args.market_address}")
    outcome = find_outcome(market, args.token_id)
    order = OrderRequest(args.market_address, args.token_id, args.side, args.amount_usdt)
    provider = EstimatedQuoteProvider()
    return provider.quote(quote_request_from_order(order), outcome)


def _load_strategy(import_path: str):
    if ":" not in import_path:
        raise SystemExit("--strategy must be in module:ClassName format")
    module_name, class_name = import_path.split(":", 1)
    if str(Path.cwd()) not in sys.path:
        sys.path.insert(0, str(Path.cwd()))
    module = importlib.import_module(module_name)
    strategy_cls = getattr(module, class_name)
    return strategy_cls()


def _json_safe_tx(tx: Dict[str, Any]) -> Dict[str, Any]:
    safe: Dict[str, Any] = {}
    for key, value in tx.items():
        if isinstance(value, bytes):
            safe[key] = "0x" + value.hex()
        else:
            safe[key] = value
    return safe


def _cost_to_dict(cost) -> Dict[str, Any]:
    payload = asdict(cost)
    gas = payload.get("gas")
    if gas is None:
        payload["gas"] = {"gas_units": None, "gas_bnb": None, "bnb_usdt": None, "gas_usdt": None}
    return payload


def _send_allowed(args: argparse.Namespace) -> bool:
    if bool(getattr(args, "i_understand_real_money", False)):
        return True
    return (
        _env_enabled("FORTY_TWO_UNATTENDED_LIVE")
        and _env_enabled("FORTY_TWO_ENABLE_LIVE")
        and _env_enabled("FORTY_TWO_CONFIRM_COMPLIANCE")
        and not _env_enabled("FORTY_TWO_KILL_SWITCH")
    )


def _send_gate_message() -> str:
    return (
        "--send requires either --i-understand-real-money or env gates: "
        "FORTY_TWO_UNATTENDED_LIVE=true, FORTY_TWO_ENABLE_LIVE=true, "
        "FORTY_TWO_CONFIRM_COMPLIANCE=true, FORTY_TWO_KILL_SWITCH=false"
    )


def _env_enabled(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "y", "on"}


def _market_summary(market: Dict[str, Any]) -> Dict[str, Any]:
    classification = classify_market(market)
    return {
        "address": market.get("address"),
        "question": market.get("question"),
        "volume": float(market.get("volume") or 0),
        **classification,
    }


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
