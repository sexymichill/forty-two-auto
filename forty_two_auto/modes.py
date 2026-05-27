from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, List


@dataclass(frozen=True)
class AutomationMode:
    name: str
    level: int
    status: str
    sends_transaction: bool
    purpose: str
    next_step: str
    boundary: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def automation_modes() -> List[AutomationMode]:
    return [
        AutomationMode(
            name="scan/read-only",
            level=1,
            status="ready",
            sends_transaction=False,
            purpose="Read markets and wallet-independent data before execution.",
            next_step="Use scan once/loop to find the market address and token id you want to trade.",
            boundary="No trading action.",
        ),
        AutomationMode(
            name="paper",
            level=2,
            status="ready",
            sends_transaction=False,
            purpose="Record simulated buy/sell actions before touching a wallet.",
            next_step="Use paper buy/sell to test execution plumbing.",
            boundary="No signing, no wallet dependency.",
        ),
        AutomationMode(
            name="dry-run/plan",
            level=3,
            status="ready",
            sends_transaction=False,
            purpose="Build a transaction preview, quote, cost estimate, and risk decision without sending.",
            next_step="Inspect gas, fees, allowance, and minOut before any real transaction.",
            boundary="No transaction broadcast.",
        ),
        AutomationMode(
            name="direct_contract",
            level=4,
            status="pilot",
            sends_transaction=True,
            purpose="Use a local private-key wallet to build and explicitly send BNB Chain contract transactions.",
            next_step="Use approve/revoke/buy/sell with explicit confirmation for tests or the unattended live gate for bots.",
            boundary="Private key stays local; real sends require either the per-run flag or all unattended live env gates.",
        ),
    ]
