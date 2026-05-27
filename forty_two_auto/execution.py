from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, Optional

from .quotes import QuoteRequest, QuoteResult
from .risk import RiskConfig, RiskDecision, evaluate_order_risk
from .storage import insert_fill, insert_order, insert_quote


@dataclass(frozen=True)
class OrderRequest:
    market_address: str
    token_id: str
    side: str
    amount_usdt: float
    mode: str = "paper"
    today_risk_usdt: float = 0.0


@dataclass(frozen=True)
class OrderResult:
    order_id: Optional[int]
    mode: str
    side: str
    status: str
    quote: QuoteResult
    risk: RiskDecision
    message: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "order_id": self.order_id,
            "mode": self.mode,
            "side": self.side,
            "status": self.status,
            "quote": self.quote.to_dict(),
            "risk": asdict(self.risk),
            "message": self.message,
        }


class ExecutionAdapter:
    mode = "base"

    def execute(self, conn, request: OrderRequest, quote: QuoteResult, risk_config: RiskConfig | None = None) -> OrderResult:
        raise NotImplementedError


class PaperExecutionAdapter(ExecutionAdapter):
    mode = "paper"

    def execute(self, conn, request: OrderRequest, quote: QuoteResult, risk_config: RiskConfig | None = None) -> OrderResult:
        risk = evaluate_order_risk("paper", request.amount_usdt, request.today_risk_usdt, quote, risk_config)
        quote_id = insert_quote(conn, quote)
        status = "paper_filled" if risk.allowed else "rejected"
        raw = {"request": asdict(request), "quote": quote.to_dict(), "risk": asdict(risk)}
        order_id = insert_order(
            conn,
            "paper",
            request.side,
            status,
            request.market_address,
            request.token_id,
            request.amount_usdt,
            quote_id,
            risk.reasons,
            raw,
        )
        if risk.allowed:
            token_amount = quote.expected_tokens if request.side == "buy" else quote.expected_tokens
            amount_usdt = request.amount_usdt if request.side == "buy" else quote.expected_collateral_usdt
            insert_fill(conn, order_id, "paper", amount_usdt, token_amount, quote.price, quote.to_dict())
        return OrderResult(order_id, "paper", request.side, status, quote, risk, "paper order recorded")


class DryRunExecutionAdapter(ExecutionAdapter):
    mode = "dry-run"

    def execute(self, conn, request: OrderRequest, quote: QuoteResult, risk_config: RiskConfig | None = None) -> OrderResult:
        risk = evaluate_order_risk("dry-run", request.amount_usdt, request.today_risk_usdt, quote, risk_config)
        quote_id = insert_quote(conn, quote)
        status = "planned" if risk.allowed else "rejected"
        raw = {"request": asdict(request), "quote": quote.to_dict(), "risk": asdict(risk)}
        order_id = insert_order(
            conn,
            "dry-run",
            request.side,
            status,
            request.market_address,
            request.token_id,
            request.amount_usdt,
            quote_id,
            risk.reasons,
            raw,
        )
        return OrderResult(order_id, "dry-run", request.side, status, quote, risk, "dry-run plan recorded; no signature sent")


class LiveExecutionAdapter(ExecutionAdapter):
    mode = "live"

    def execute(self, conn, request: OrderRequest, quote: QuoteResult, risk_config: RiskConfig | None = None) -> OrderResult:
        risk = evaluate_order_risk("live", request.amount_usdt, request.today_risk_usdt, quote, risk_config)
        quote_id = insert_quote(conn, quote)
        raw = {"request": asdict(request), "quote": quote.to_dict(), "risk": asdict(risk)}
        order_id = insert_order(
            conn,
            "live",
            request.side,
            "blocked" if not risk.allowed else "not_implemented",
            request.market_address,
            request.token_id,
            request.amount_usdt,
            quote_id,
            risk.reasons or ["live adapter has no signer implementation"],
            raw,
        )
        message = "live order blocked by gate" if not risk.allowed else "live adapter skeleton only; no transaction sent"
        return OrderResult(order_id, "live", request.side, "blocked", quote, risk, message)


def quote_request_from_order(request: OrderRequest) -> QuoteRequest:
    side = "sell" if request.side == "sell" else "buy"
    return QuoteRequest(
        market_address=request.market_address,
        token_id=request.token_id,
        side=side,
        amount_usdt=request.amount_usdt,
    )
