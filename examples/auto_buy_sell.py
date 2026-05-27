from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict

if str(Path.cwd()) not in sys.path:
    sys.path.insert(0, str(Path.cwd()))

from forty_two_auto.onchain import OnchainClient, load_dotenv, load_onchain_config


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Minimal 42space direct-contract buy/sell runner.")
    parser.add_argument("--env", default=".env")
    parser.add_argument("--market", required=True)
    parser.add_argument("--token", required=True, type=int)
    parser.add_argument("--send", action="store_true", help="Broadcast real transactions.")
    parser.add_argument("--i-understand-real-money", action="store_true")
    sub = parser.add_subparsers(dest="action", required=True)

    buy = sub.add_parser("buy", help="Approve BUSDT if needed, then buy/mint outcome token.")
    buy.add_argument("--amount-usdt", required=True, type=Decimal)
    buy.add_argument("--auto-approve", action="store_true")

    sell = sub.add_parser("sell", help="Approve outcome token if needed, then sell/redeem.")
    sell.add_argument("--amount-tokens", required=True, type=Decimal)
    sell.add_argument("--auto-approve", action="store_true")

    revoke_busdt = sub.add_parser("revoke-busdt", help="Reset BUSDT allowance to zero.")
    revoke_busdt.set_defaults(revoke_kind="busdt")

    revoke_outcome = sub.add_parser("revoke-outcome", help="Reset outcome token allowance to zero.")
    revoke_outcome.set_defaults(revoke_kind="outcome")

    args = parser.parse_args(argv)
    try:
        load_dotenv(args.env)
        _assert_send_allowed(args)
        _assert_amount_limits(args)
        client = OnchainClient(load_onchain_config(args.env))
        if args.action == "buy":
            payload = _buy(client, args)
        elif args.action == "sell":
            payload = _sell(client, args)
        elif args.action == "revoke-busdt":
            payload = _revoke_busdt(client, args)
        elif args.action == "revoke-outcome":
            payload = _revoke_outcome(client, args)
        else:
            raise SystemExit(f"unsupported action: {args.action}")
    except SystemExit as exc:
        if exc.code not in (None, 0):
            print(str(exc), file=sys.stderr)
            return 1
        return 0
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def _buy(client: OnchainClient, args: argparse.Namespace) -> Dict[str, Any]:
    check = client.check()
    payload: Dict[str, Any] = {"action": "buy", "wallet": _short(check.wallet_address), "sent": []}
    if check.busdt_balance < float(args.amount_usdt):
        raise SystemExit("BUSDT balance is lower than requested buy amount")
    if check.busdt_allowance_to_router < float(args.amount_usdt):
        _assert_auto_approve_allowed(args, args.amount_usdt, "BUSDT")
        approve_tx = client.build_approve_busdt_tx(args.amount_usdt)
        payload["approve_busdt"] = _tx_preview(client, approve_tx)
        if not args.auto_approve:
            payload["blocked"] = "BUSDT allowance is too low; rerun with --auto-approve after reviewing the preview."
            return payload
        if args.send:
            payload["sent"].append(_send_and_wait(client, approve_tx, "approve_busdt"))
    buy_tx = client.build_buy_tx(args.market, args.token, args.amount_usdt)
    payload["buy"] = {
        "tx": _json_safe_tx(buy_tx),
        "cost": _cost_to_dict(client.simulate_mint_cost(args.market, args.token, args.amount_usdt, tx=buy_tx)),
    }
    if args.send:
        payload["sent"].append(_send_and_wait(client, buy_tx, "buy"))
    return payload


def _sell(client: OnchainClient, args: argparse.Namespace) -> Dict[str, Any]:
    position = client.outcome_position(args.market, args.token)
    payload: Dict[str, Any] = {"action": "sell", "position_before": asdict(position), "sent": []}
    if Decimal(str(position.balance)) < args.amount_tokens:
        raise SystemExit("outcome token balance is lower than requested sell amount")
    if Decimal(str(position.allowance_to_router)) < args.amount_tokens:
        _assert_auto_approve_allowed(args, args.amount_tokens, "outcome")
        approve_tx = client.build_approve_outcome_tx(args.market, args.token, args.amount_tokens)
        payload["approve_outcome"] = _tx_preview(client, approve_tx)
        if not args.auto_approve:
            payload["blocked"] = "Outcome allowance is too low; rerun with --auto-approve after reviewing the preview."
            return payload
        if args.send:
            payload["sent"].append(_send_and_wait(client, approve_tx, "approve_outcome"))
    sell_tx = client.build_sell_tx(args.market, args.token, args.amount_tokens)
    payload["sell"] = {
        "tx": _json_safe_tx(sell_tx),
        "cost": _cost_to_dict(client.simulate_redeem_cost(args.market, args.token, args.amount_tokens, tx=sell_tx)),
    }
    if args.send:
        payload["sent"].append(_send_and_wait(client, sell_tx, "sell"))
    return payload


def _revoke_busdt(client: OnchainClient, args: argparse.Namespace) -> Dict[str, Any]:
    tx = client.build_approve_busdt_tx(Decimal("0"))
    payload = {"action": "revoke_busdt", "tx": _json_safe_tx(tx), "gas_cost": asdict(client.estimate_tx_cost(tx)), "sent": []}
    if args.send:
        payload["sent"].append(_send_and_wait(client, tx, "revoke_busdt"))
    return payload


def _revoke_outcome(client: OnchainClient, args: argparse.Namespace) -> Dict[str, Any]:
    tx = client.build_approve_outcome_tx(args.market, args.token, Decimal("0"))
    payload = {"action": "revoke_outcome", "tx": _json_safe_tx(tx), "gas_cost": asdict(client.estimate_tx_cost(tx)), "sent": []}
    if args.send:
        payload["sent"].append(_send_and_wait(client, tx, "revoke_outcome"))
    return payload


def _tx_preview(client: OnchainClient, tx: Dict[str, Any]) -> Dict[str, Any]:
    return {"tx": _json_safe_tx(tx), "gas_cost": asdict(client.estimate_tx_cost(tx))}


def _send_and_wait(client: OnchainClient, tx: Dict[str, Any], tx_type: str) -> Dict[str, Any]:
    tx_hash = client.send_transaction(tx)
    timeout = int(_env_decimal("FORTY_TWO_RECEIPT_TIMEOUT_SECONDS", Decimal("120")))
    receipt = client.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=timeout)
    status = int(receipt.get("status", 0))
    result = {
        "type": tx_type,
        "tx_hash": tx_hash,
        "status": status,
        "block_number": receipt.get("blockNumber"),
        "gas_used": receipt.get("gasUsed"),
    }
    if status != 1:
        raise SystemExit(f"{tx_type} transaction failed: {tx_hash}")
    return result


def _cost_to_dict(cost) -> Dict[str, Any]:
    payload = asdict(cost)
    if payload.get("gas") is None:
        payload["gas"] = {"gas_units": None, "gas_bnb": None, "bnb_usdt": None, "gas_usdt": None}
    return payload


def _json_safe_tx(tx: Dict[str, Any]) -> Dict[str, Any]:
    safe: Dict[str, Any] = {}
    for key, value in tx.items():
        safe[key] = "0x" + value.hex() if isinstance(value, bytes) else value
    return safe


def _short(address: str) -> str:
    return address if len(address) <= 12 else f"{address[:6]}...{address[-4:]}"


def _assert_send_allowed(args: argparse.Namespace) -> None:
    if not args.send:
        return
    if args.i_understand_real_money:
        return
    if _env_enabled("FORTY_TWO_UNATTENDED_LIVE") and _env_enabled("FORTY_TWO_ENABLE_LIVE") and _env_enabled(
        "FORTY_TWO_CONFIRM_COMPLIANCE"
    ) and not _env_enabled("FORTY_TWO_KILL_SWITCH"):
        return
    raise SystemExit(
        "--send requires either --i-understand-real-money or env gates: "
        "FORTY_TWO_UNATTENDED_LIVE=true, FORTY_TWO_ENABLE_LIVE=true, "
        "FORTY_TWO_CONFIRM_COMPLIANCE=true, FORTY_TWO_KILL_SWITCH=false"
    )


def _assert_amount_limits(args: argparse.Namespace) -> None:
    if getattr(args, "action", "") != "buy":
        return
    max_trade = _env_decimal("FORTY_TWO_MAX_TRADE_USDT", Decimal("20"))
    if args.amount_usdt > max_trade:
        raise SystemExit(f"amount-usdt exceeds FORTY_TWO_MAX_TRADE_USDT={max_trade}")


def _assert_auto_approve_allowed(args: argparse.Namespace, amount: Decimal, approve_kind: str) -> None:
    if not args.auto_approve:
        return
    if approve_kind == "BUSDT":
        max_approve = _env_decimal("FORTY_TWO_MAX_AUTO_APPROVE_USDT", _env_decimal("FORTY_TWO_MAX_TRADE_USDT", Decimal("20")))
    else:
        max_approve = _env_decimal("FORTY_TWO_MAX_AUTO_APPROVE_TOKENS", Decimal("1000000"))
    if amount > max_approve:
        raise SystemExit(f"{approve_kind} auto-approve amount exceeds configured limit {max_approve}")


def _env_enabled(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "y", "on"}


def _env_decimal(name: str, default: Decimal) -> Decimal:
    value = os.environ.get(name)
    if not value:
        return default
    try:
        return Decimal(value)
    except Exception:
        return default


if __name__ == "__main__":
    raise SystemExit(main())
