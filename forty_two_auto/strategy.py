from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Iterable, List, Protocol

from .execution import (
    DryRunExecutionAdapter,
    LiveExecutionAdapter,
    OrderRequest,
    OrderResult,
    PaperExecutionAdapter,
    quote_request_from_order,
)
from .quotes import EstimatedQuoteProvider, find_outcome
from .risk import RiskConfig
from .storage import audit, upsert_markets


@dataclass(frozen=True)
class StrategySignal:
    market_address: str
    token_id: str
    side: str
    amount_usdt: float
    reason: str
    today_risk_usdt: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)


class Strategy(Protocol):
    def generate(self, markets: Iterable[Dict[str, Any]]) -> Iterable[StrategySignal]:
        """Return desired buy/sell signals for the supplied market snapshots."""


def run_strategy(
    conn,
    markets: Iterable[Dict[str, Any]],
    strategy: Strategy,
    mode: str = "paper",
    risk_config: RiskConfig | None = None,
    quote_provider: EstimatedQuoteProvider | None = None,
) -> List[OrderResult]:
    market_list = list(markets)
    upsert_markets(conn, market_list)
    market_by_address = {str(market.get("address") or ""): market for market in market_list}
    provider = quote_provider or EstimatedQuoteProvider()
    adapter = _adapter_for_mode(mode)
    results: List[OrderResult] = []

    for signal in strategy.generate(market_list):
        market = market_by_address.get(signal.market_address)
        if not market:
            audit(conn, "strategy_signal_rejected", {"signal": asdict(signal), "reason": "market not supplied"})
            continue
        try:
            outcome = find_outcome(market, signal.token_id)
            order = OrderRequest(
                market_address=signal.market_address,
                token_id=signal.token_id,
                side=signal.side,
                amount_usdt=signal.amount_usdt,
                mode=mode,
                today_risk_usdt=signal.today_risk_usdt,
            )
            quote = provider.quote(quote_request_from_order(order), outcome)
            result = adapter.execute(conn, order, quote, risk_config)
            audit(
                conn,
                "strategy_signal_executed",
                {"signal": asdict(signal), "result": result.to_dict()},
            )
            results.append(result)
        except Exception as exc:
            audit(conn, "strategy_signal_rejected", {"signal": asdict(signal), "reason": str(exc)})
    return results


def _adapter_for_mode(mode: str):
    if mode == "paper":
        return PaperExecutionAdapter()
    if mode == "dry-run":
        return DryRunExecutionAdapter()
    if mode == "live":
        return LiveExecutionAdapter()
    raise ValueError("mode must be paper, dry-run, or live")
