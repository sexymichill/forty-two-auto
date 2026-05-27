from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from .http import get_json


@dataclass(frozen=True)
class FortyTwoConfig:
    rest_base: str = "https://rest.ft.42.space"
    timeout_seconds: float = 12.0
    retries: int = 3


class FortyTwoClient:
    def __init__(self, config: FortyTwoConfig | None = None):
        self.config = config or FortyTwoConfig()

    def markets(
        self,
        status: str = "live",
        limit: int = 500,
        offset: int = 0,
        order: str = "created_at",
        ascending: bool = False,
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        payload = self._get(
            "/api/v1/markets",
            {
                "status": status,
                "limit": limit,
                "offset": offset,
                "order": order,
                "ascending": str(ascending).lower(),
            },
        )
        data = payload.get("data", []) if isinstance(payload, dict) else []
        pagination = payload.get("pagination", {}) if isinstance(payload, dict) else {}
        return data if isinstance(data, list) else [], pagination if isinstance(pagination, dict) else {}

    def market(self, market_address: str) -> Dict[str, Any]:
        payload = self._get(f"/api/v1/markets/{market_address}", None)
        return payload if isinstance(payload, dict) else {}

    def prices(self, market_address: str) -> List[Dict[str, Any]]:
        payload = self._get("/api/v1/market-data/prices", {"market": market_address})
        return payload if isinstance(payload, list) else []

    def price_history(
        self,
        market_address: str,
        token_id: Optional[str] = None,
        outcome_index: Optional[int] = None,
        duration: Optional[str] = None,
        start_ts: Optional[int] = None,
        end_ts: Optional[int] = None,
        fidelity: int = 5000,
    ) -> Dict[str, Any]:
        params: Dict[str, Any] = {"market": market_address, "fidelity": fidelity}
        if token_id is not None:
            params["token_id"] = token_id
        elif outcome_index is not None:
            params["outcome_index"] = outcome_index
        else:
            raise ValueError("token_id or outcome_index is required")
        if duration is not None:
            params["duration"] = duration
        if start_ts is not None:
            params["start_ts"] = start_ts
        if end_ts is not None:
            params["end_ts"] = end_ts
        payload = self._get("/api/v1/market-data/prices/history", params)
        return payload if isinstance(payload, dict) else {}

    def ohlc(
        self,
        market_address: str,
        token_id: Optional[str] = None,
        outcome_index: Optional[int] = None,
        interval: str = "1m",
        start_ts: Optional[int] = None,
        end_ts: Optional[int] = None,
        limit: int = 5000,
    ) -> Dict[str, Any]:
        params: Dict[str, Any] = {"market": market_address, "interval": interval, "limit": limit}
        if token_id is not None:
            params["token_id"] = token_id
        elif outcome_index is not None:
            params["outcome_index"] = outcome_index
        else:
            raise ValueError("token_id or outcome_index is required")
        if start_ts is not None:
            params["start_ts"] = start_ts
        if end_ts is not None:
            params["end_ts"] = end_ts
        payload = self._get("/api/v1/market-data/ohlc", params)
        return payload if isinstance(payload, dict) else {}

    def _get(self, path: str, params: Optional[Dict[str, Any]]) -> Any:
        return get_json(
            f"{self.config.rest_base}{path}",
            params=params,
            timeout=self.config.timeout_seconds,
            retries=self.config.retries,
        )
