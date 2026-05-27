from __future__ import annotations

from forty_two_auto.strategy import StrategySignal


class ExampleStrategy:
    """A tiny demo strategy. Replace this with your own model logic."""

    def generate(self, markets):
        for market in markets:
            outcomes = market.get("outcomes") or []
            if not outcomes:
                continue
            first = outcomes[0]
            token_id = first.get("tokenId") or first.get("token_id")
            price = float(first.get("price") or 0)
            if token_id and 0 < price <= 0.05:
                yield StrategySignal(
                    market_address=market["address"],
                    token_id=str(token_id),
                    side="buy",
                    amount_usdt=10,
                    reason="example strategy: first outcome price <= 0.05",
                    metadata={"price": price},
                )
