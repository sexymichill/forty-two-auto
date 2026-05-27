from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional

from .market_data import FortyTwoClient
from .onchain import OnchainClient, load_onchain_config


@dataclass(frozen=True)
class ExecutionPathStatus:
    path: str
    status: str
    priority: str
    open_source_adapter: str
    evidence: str
    next_step: str
    boundary: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def check_execution_paths(env_path: str = ".env", include_network: bool = True) -> List[ExecutionPathStatus]:
    """Return the supported execution paths without exposing secrets.

    The public framework only exposes market-data reads and direct protocol
    execution. Signal/radar and hosted-wallet/browser-assist workflows are kept
    out of the open-source execution bundle.
    """

    statuses: List[ExecutionPathStatus] = []
    statuses.append(_check_contract_path(env_path))
    statuses.append(_check_rest_path(include_network))
    return statuses


def _check_contract_path(env_path: str) -> ExecutionPathStatus:
    try:
        client = OnchainClient(load_onchain_config(env_path))
        check = client.check()
        if check.connected and check.chain_id == 56:
            status = "OK"
            evidence = (
                f"BNB Chain connected; wallet {_redact_address(check.wallet_address)}; "
                f"BUSDT={check.busdt_balance:.6f}; allowance={check.busdt_allowance_to_router:.6f}"
            )
            next_step = "Use onchain approve/revoke/buy/sell or examples/auto_buy_sell.py with explicit confirmation or the unattended live gate."
        else:
            status = "NEEDS_ATTENTION"
            evidence = f"connected={check.connected}; chain_id={check.chain_id}; expected_chain_id=56"
            next_step = "Fix RPC/network before building or sending transactions."
    except Exception as exc:
        status = "NOT_READY"
        evidence = str(exc)
        next_step = "Fill local .env with RPC and a private-key wallet that actually holds funds."
    return ExecutionPathStatus(
        path="direct_contract",
        status=status,
        priority="P0",
        open_source_adapter="OnchainClient + onchain CLI + auto_buy_sell example",
        evidence=evidence,
        next_step=next_step,
        boundary="Private keys stay local; every real send requires either the per-run flag or all unattended live env gates.",
    )


def _check_rest_path(include_network: bool) -> ExecutionPathStatus:
    if not include_network:
        evidence = "network check skipped"
        status = "READ_ONLY"
    else:
        try:
            markets, _ = FortyTwoClient().markets(status="live", limit=1)
            status = "READ_ONLY_OK" if markets else "READ_ONLY_EMPTY"
            evidence = f"42 REST market-data read returned {len(markets)} live market(s)."
        except Exception as exc:
            status = "READ_ONLY_ERROR"
            evidence = str(exc)
    return ExecutionPathStatus(
        path="official_rest_or_internal_api",
        status=status,
        priority="P1",
        open_source_adapter="Market-data client only.",
        evidence=evidence,
        next_step="Only add a REST execution adapter if 42 publishes or verifies an authenticated order API.",
        boundary="Do not invent or scrape hidden order endpoints; reads are fine, execution is not assumed.",
    )


def _redact_address(address: str) -> str:
    if len(address) <= 12:
        return address
    return f"{address[:6]}...{address[-4:]}"
