from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Literal, Optional

Side = Literal["buy", "sell"]


@dataclass(frozen=True)
class QuoteRequest:
    market_address: str
    token_id: str
    side: Side
    amount_usdt: float
    token_amount: Optional[float] = None


@dataclass(frozen=True)
class QuoteResult:
    market_address: str
    token_id: str
    side: Side
    amount_usdt: float
    price: float
    payout: float
    expected_tokens: float
    expected_collateral_usdt: float
    fee_usdt: float
    fee_rate: float
    slippage_bps: float
    gas_usdt: Optional[float]
    confidence: str
    executable: bool
    reason: str
    created_at: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class EstimatedQuoteProvider:
    """Conservative quote provider until a verified 42 quote/redeem path is connected."""

    def __init__(self, fee_rate: float = 0.008, default_slippage_bps: float = 100.0, gas_usdt: Optional[float] = None):
        self.fee_rate = fee_rate
        self.default_slippage_bps = default_slippage_bps
        self.gas_usdt = gas_usdt

    def quote(self, request: QuoteRequest, outcome: Dict[str, Any]) -> QuoteResult:
        price = _positive_float(outcome.get("price"))
        payout = _positive_float(outcome.get("payout"))
        now = datetime.now(timezone.utc).isoformat()
        if request.side not in ("buy", "sell"):
            raise ValueError("side must be buy or sell")
        if request.amount_usdt <= 0:
            return self._unavailable(request, price, payout, "amount_usdt must be positive", now)
        if price <= 0:
            return self._unavailable(request, price, payout, "outcome price is unavailable or zero", now)

        fee = request.amount_usdt * self.fee_rate
        net_amount = max(0.0, request.amount_usdt - fee)
        if request.side == "buy":
            expected_tokens = net_amount / price
            expected_collateral = 0.0
            reason = "estimated buy/mint quote from current outcome price; no verified executable route attached"
        else:
            expected_tokens = request.token_amount if request.token_amount is not None else request.amount_usdt / price
            gross_collateral = expected_tokens * price
            fee = gross_collateral * self.fee_rate
            expected_collateral = max(0.0, gross_collateral - fee)
            reason = "estimated sell/redeem quote from current outcome price; no verified executable route attached"

        return QuoteResult(
            market_address=request.market_address,
            token_id=request.token_id,
            side=request.side,
            amount_usdt=request.amount_usdt,
            price=price,
            payout=payout,
            expected_tokens=expected_tokens,
            expected_collateral_usdt=expected_collateral,
            fee_usdt=fee,
            fee_rate=self.fee_rate,
            slippage_bps=self.default_slippage_bps,
            gas_usdt=self.gas_usdt,
            confidence="estimated",
            executable=False,
            reason=reason,
            created_at=now,
        )

    def _unavailable(self, request: QuoteRequest, price: float, payout: float, reason: str, now: str) -> QuoteResult:
        return QuoteResult(
            market_address=request.market_address,
            token_id=request.token_id,
            side=request.side,
            amount_usdt=request.amount_usdt,
            price=price,
            payout=payout,
            expected_tokens=0.0,
            expected_collateral_usdt=0.0,
            fee_usdt=0.0,
            fee_rate=self.fee_rate,
            slippage_bps=self.default_slippage_bps,
            gas_usdt=self.gas_usdt,
            confidence="unavailable",
            executable=False,
            reason=reason,
            created_at=now,
        )


def find_outcome(market: Dict[str, Any], token_id: str) -> Dict[str, Any]:
    for outcome in market.get("outcomes") or []:
        if str(outcome.get("tokenId") or outcome.get("token_id") or "") == str(token_id):
            return outcome
    raise ValueError(f"token_id not found in market outcomes: {token_id}")


def _positive_float(value: Any) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return 0.0
    return parsed if parsed > 0 else 0.0
