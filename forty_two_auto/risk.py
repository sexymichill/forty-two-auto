from __future__ import annotations

from dataclasses import dataclass
from typing import List

from .quotes import QuoteResult


@dataclass(frozen=True)
class RiskConfig:
    live_enabled: bool = False
    compliance_confirmed: bool = False
    kill_switch_enabled: bool = False
    min_trade_usdt: float = 5.0
    max_trade_usdt: float = 20.0
    daily_risk_cap_usdt: float = 100.0
    require_verified_quote: bool = True


@dataclass(frozen=True)
class RiskDecision:
    allowed: bool
    mode: str
    reasons: List[str]


def evaluate_order_risk(
    mode: str,
    amount_usdt: float,
    today_risk_usdt: float,
    quote: QuoteResult,
    config: RiskConfig | None = None,
) -> RiskDecision:
    cfg = config or RiskConfig()
    reasons: List[str] = []
    if cfg.kill_switch_enabled:
        reasons.append("kill switch enabled")
    if amount_usdt < cfg.min_trade_usdt:
        reasons.append("amount below minimum")
    if amount_usdt > cfg.max_trade_usdt:
        reasons.append("amount above maximum")
    if today_risk_usdt + amount_usdt > cfg.daily_risk_cap_usdt:
        reasons.append("daily risk cap exceeded")

    if mode == "live":
        if not cfg.live_enabled:
            reasons.append("live mode is disabled")
        if not cfg.compliance_confirmed:
            reasons.append("compliance confirmation missing")
        if cfg.require_verified_quote and quote.confidence != "verified":
            reasons.append("verified executable quote is required")
        if not quote.executable:
            reasons.append("quote is not executable")
    elif mode == "dry-run":
        if quote.confidence == "unavailable":
            reasons.append("quote unavailable")
    elif mode == "paper":
        if quote.confidence == "unavailable":
            reasons.append("quote unavailable")
    else:
        reasons.append(f"unsupported mode: {mode}")

    return RiskDecision(allowed=not reasons, mode=mode, reasons=reasons)
