from __future__ import annotations

import json
from typing import Any, Dict, Iterable


MARKET_TYPE_LABELS = {
    "FDV_TGE_IPO": "FDV / TGE / IPO",
    "SPORTS": "Sports",
    "LISTING_EVENT": "Listing / Exchange Event",
    "MACRO_DATA": "Macro Data",
    "SOCIAL_COUNT": "Social Count",
    "AI_TECH": "AI / Tech Indicator",
    "TRADING_VOLUME": "Trading Volume",
    "PRICE_RANGE": "Price Range",
    "GAME_CULTURE": "Game / Culture",
    "OTHER": "Other / Needs Review",
}


def market_description_text(market: Dict[str, Any]) -> str:
    raw = market.get("description")
    if not raw:
        return ""
    if isinstance(raw, dict):
        return str(raw.get("description") or "")
    if isinstance(raw, str):
        try:
            decoded = json.loads(raw)
        except json.JSONDecodeError:
            return raw
        if isinstance(decoded, dict):
            return str(decoded.get("description") or raw)
    return str(raw)


def is_price_range_market(market: Dict[str, Any]) -> bool:
    question = str(market.get("question") or "").lower()
    return "price range" in question


def classify_market(market: Dict[str, Any]) -> Dict[str, str]:
    text = _market_search_text(market)
    question = str(market.get("question") or "").lower()

    if is_price_range_market(market) or "price range" in text or _contains_any(
        text,
        [
            "appreciate",
            "depreciate",
            "price move",
            "price change",
            "how much will",
            "above $",
            "below $",
        ],
    ):
        return _result("PRICE_RANGE", "price range wording")
    if _contains_any(
        text,
        [
            "fdv",
            "fully diluted",
            "valuation",
            "market cap",
            "mcap",
            "ipo",
            "tge",
            "token generation",
            "rank higher",
        ],
    ):
        return _result("FDV_TGE_IPO", "valuation/fdv/tge/ipo wording")
    if _contains_any(
        text,
        [
            "listed on binance",
            "binance listing",
            "which token will be listed",
            "will list",
            "exchange listing",
            "coinbase listing",
        ],
    ):
        return _result("LISTING_EVENT", "exchange listing wording")
    if _contains_any(
        text,
        [
            "unemployment",
            "inflation",
            "cpi",
            "hicp",
            "fed",
            "interest rate",
            "nonfarm",
            "gdp",
            "jobless",
        ],
    ):
        return _result("MACRO_DATA", "macro data wording")
    if _contains_any(text, ["tweet", "followers", "likes", "retweets", "posts on x", "x posts"]):
        return _result("SOCIAL_COUNT", "social count wording")
    if _contains_any(
        text,
        [
            "openrouter",
            "deepseek",
            "chatgpt",
            "claude",
            "model usage",
            "ai model",
            "llm",
            "openai",
            "anthropic",
        ],
    ):
        return _result("AI_TECH", "ai/tech metric wording")
    if _contains_any(text, ["volume", "trading volume", "transaction volume", "tx volume"]):
        return _result("TRADING_VOLUME", "volume wording")
    if _contains_any(
        text,
        [
            "vs ",
            " v ",
            "uefa",
            "nba",
            "ipl",
            "f1",
            "grand prix",
            "champion",
            "winner",
            "arsenal",
            "psg",
            "match",
            "game",
            "final",
        ],
    ) and not _contains_any(question, ["fdv", "market cap", "valuation"]):
        return _result("SPORTS", "sports/competition wording")
    if _contains_any(text, ["movie", "box office", "album", "game awards", "steam", "twitch", "youtube", "song"]):
        return _result("GAME_CULTURE", "culture/game wording")
    return _result("OTHER", "no deterministic keyword match")


def _result(market_type: str, reason: str) -> Dict[str, str]:
    return {
        "market_type": market_type,
        "market_type_label": MARKET_TYPE_LABELS[market_type],
        "type_reason": reason,
    }


def _market_search_text(market: Dict[str, Any]) -> str:
    outcomes = " ".join(str(outcome.get("name") or "") for outcome in market.get("outcomes") or [])
    parts = [
        str(market.get("question") or ""),
        str(market.get("slug") or ""),
        market_description_text(market),
        outcomes,
    ]
    return " ".join(parts).lower()


def _contains_any(text: str, keywords: Iterable[str]) -> bool:
    return any(keyword in text for keyword in keywords)
