from __future__ import annotations

import json
from dataclasses import asdict
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import streamlit as st

from forty_two_auto.classifier import classify_market
from forty_two_auto.execution_paths import check_execution_paths
from forty_two_auto.market_data import FortyTwoClient
from forty_two_auto.onchain import OnchainClient, load_onchain_config
from forty_two_auto.storage import audit, connect, latest_report, upsert_markets


DEFAULT_DB = str(Path("data") / "forty_two_auto.sqlite3")
DEFAULT_TOKENS = "1,2,4"


def main() -> None:
    st.set_page_config(page_title="42 Protocol Console", page_icon="42", layout="wide")
    _style()

    st.title("42space Protocol Console")
    st.caption("开源框架本地控制台：看钱包、看盘口、看持仓、生成交易计划。真实发送必须手动解锁。")

    settings = _sidebar()
    conn = connect(settings["db_path"])
    client = _load_onchain(settings["env_path"])

    _status_strip(client, settings)

    tab_wallet, tab_markets, tab_positions, tab_trade, tab_paths, tab_audit = st.tabs(
        ["钱包", "盘口", "持仓", "交易实验室", "执行路径", "审计"]
    )

    with tab_wallet:
        _wallet_tab(client)
    with tab_markets:
        _markets_tab(conn, settings)
    with tab_positions:
        _positions_tab(client, settings)
    with tab_trade:
        _trade_lab_tab(client, settings, conn)
    with tab_paths:
        _paths_tab(settings)
    with tab_audit:
        _audit_tab(conn)


def _sidebar() -> Dict[str, Any]:
    st.sidebar.header("本地配置")
    env_path = st.sidebar.text_input("ENV 文件", ".env")
    db_path = st.sidebar.text_input("SQLite DB", DEFAULT_DB)
    market_address = st.sidebar.text_input(
        "Market Address",
        "",
        placeholder="0x...",
        help="用于持仓和交易实验室。开源用户可以换成任意 42 market 地址。",
    )
    token_ids = st.sidebar.text_input("Token IDs", DEFAULT_TOKENS)
    amount_usdt = st.sidebar.number_input("Buy amount USDT", min_value=0.1, max_value=10000.0, value=1.0, step=0.1)
    amount_tokens = st.sidebar.number_input("Sell amount tokens", min_value=0.1, max_value=1000000.0, value=1.0, step=0.1)
    return {
        "env_path": env_path,
        "db_path": db_path,
        "market_address": market_address.strip(),
        "token_ids": _parse_token_ids(token_ids),
        "amount_usdt": Decimal(str(amount_usdt)),
        "amount_tokens": Decimal(str(amount_tokens)),
    }


def _load_onchain(env_path: str) -> Optional[OnchainClient]:
    try:
        return OnchainClient(load_onchain_config(env_path))
    except Exception as exc:
        st.session_state["onchain_error"] = str(exc)
        return None


def _status_strip(client: Optional[OnchainClient], settings: Dict[str, Any]) -> None:
    cols = st.columns(4)
    if client:
        try:
            check = client.check()
            cols[0].metric("钱包", _short(check.wallet_address))
            cols[1].metric("BNB", _fmt(check.bnb_balance))
            cols[2].metric("BUSDT", _fmt(check.busdt_balance))
            cols[3].metric("Router Allowance", _fmt(check.busdt_allowance_to_router))
            return
        except Exception as exc:
            st.session_state["onchain_error"] = str(exc)
    cols[0].metric("钱包", "未就绪")
    cols[1].metric("BNB", "-")
    cols[2].metric("BUSDT", "-")
    cols[3].metric("Router Allowance", "-")
    st.info(f"当前只读/纸面可用；onchain 未就绪：{st.session_state.get('onchain_error', 'unknown')}")


def _wallet_tab(client: Optional[OnchainClient]) -> None:
    st.subheader("钱包状态")
    if not client:
        st.warning("没有加载到本地私钥钱包。仍可使用扫描、分类、paper 和 dry-run。")
        return
    check = client.check()
    rows = [
        ("Chain ID", str(check.chain_id)),
        ("Wallet", _short(check.wallet_address)),
        ("BNB Balance", _fmt(check.bnb_balance)),
        ("BUSDT Balance", _fmt(check.busdt_balance)),
        ("BUSDT Allowance To Router", _fmt(check.busdt_allowance_to_router)),
    ]
    st.table([{"字段": key, "值": value} for key, value in rows])
    st.caption("页面不会展示或保存私钥；默认也只展示短地址。真实发送仍会用本地 .env 在后端签名。")


def _markets_tab(conn, settings: Dict[str, Any]) -> None:
    st.subheader("Live Markets")
    limit = st.slider("扫描数量", min_value=10, max_value=500, value=80, step=10)
    if st.button("扫描并保存 live markets", type="primary"):
        markets, pagination = FortyTwoClient().markets(status="live", limit=limit)
        count = upsert_markets(conn, markets)
        audit(conn, "console_scan", {"count": count, "pagination": pagination})
        st.success(f"已保存 {count} 个 live markets")
        st.session_state["latest_markets"] = markets

    markets = st.session_state.get("latest_markets")
    if not markets:
        st.info("点击扫描后会显示最新盘口。")
        return
    table = []
    for market in markets[:120]:
        classification = classify_market(market)
        table.append(
            {
                "类型": classification["market_type"],
                "问题": market.get("question"),
                "地址": market.get("address"),
                "Volume": _fmt(market.get("volume")),
                "MCap": _fmt(market.get("totalMarketCap")),
                "结束时间": market.get("endDate"),
            }
        )
    st.dataframe(table, width="stretch", hide_index=True)


def _positions_tab(client: Optional[OnchainClient], settings: Dict[str, Any]) -> None:
    st.subheader("协议层持仓")
    if not client:
        st.warning("onchain 未就绪，无法读取 outcome token 持仓。")
        return
    market = settings["market_address"]
    if not market:
        st.warning("请先填写 Market Address。")
        return
    rows = []
    for token_id in settings["token_ids"]:
        try:
            position = client.outcome_position(market, token_id)
            sell_estimate = "-"
            if position.raw_balance > 0:
                try:
                    raw_out = client.simulate_redeem_collateral_out(market, token_id, position.raw_balance)
                    sell_estimate = _fmt(raw_out / 1_000_000_000_000_000_000)
                except Exception as exc:
                    sell_estimate = f"simulate error: {exc}"
            rows.append(
                {
                    "Token": position.token_id,
                    "Name": position.name,
                    "Balance": _fmt(position.balance),
                    "Allowance": _fmt(position.allowance_to_router),
                    "Sell Estimate BUSDT": sell_estimate,
                }
            )
        except Exception as exc:
            rows.append({"Token": token_id, "Name": "error", "Balance": "-", "Allowance": "-", "Sell Estimate BUSDT": str(exc)})
    st.dataframe(rows, width="stretch", hide_index=True)
    st.caption("这里看的是本地 .env 私钥钱包的链上 outcome token。")


def _trade_lab_tab(client: Optional[OnchainClient], settings: Dict[str, Any], conn) -> None:
    st.subheader("交易实验室")
    st.warning("默认只构造交易。真实发送需要勾选、输入确认词，并点击发送按钮。")
    if not client:
        st.info("onchain 未就绪；可先在 CLI 用 paper/dry-run 或补齐 .env。")
        return

    buy_col, sell_col = st.columns(2)
    with buy_col:
        st.markdown("### Buy / Mint")
        token_id = st.number_input("Buy token id", min_value=0, value=settings["token_ids"][0] if settings["token_ids"] else 1, step=1)
        if st.button("构造 BUSDT APPROVE"):
            _build_approve_busdt_preview(client, settings["amount_usdt"])
        if st.button("构造 BUSDT REVOKE"):
            _build_revoke_busdt_preview(client)
        if st.button("构造 BUY 交易"):
            _build_buy_preview(client, settings["market_address"], int(token_id), settings["amount_usdt"])
        _send_buy_box(client, settings["market_address"], int(token_id), settings["amount_usdt"], conn)

    with sell_col:
        st.markdown("### Sell / Redeem")
        token_id = st.number_input("Sell token id", min_value=0, value=settings["token_ids"][0] if settings["token_ids"] else 1, step=1)
        if st.button("构造 OUTCOME APPROVE"):
            _build_approve_outcome_preview(client, settings["market_address"], int(token_id), settings["amount_tokens"])
        if st.button("构造 OUTCOME REVOKE"):
            _build_revoke_outcome_preview(client, settings["market_address"], int(token_id))
        if st.button("构造 SELL 交易"):
            _build_sell_preview(client, settings["market_address"], int(token_id), settings["amount_tokens"])
        _send_sell_box(client, settings["market_address"], int(token_id), settings["amount_tokens"], conn)


def _build_approve_busdt_preview(client: OnchainClient, amount: Decimal) -> None:
    try:
        tx = client.build_approve_busdt_tx(amount)
        gas = _estimate_cost_or_error(client, tx)
        st.json({"sent": False, "gas_cost": gas, "transaction": _json_safe_tx(tx)})
    except Exception as exc:
        st.error(str(exc))


def _build_revoke_busdt_preview(client: OnchainClient) -> None:
    _build_approve_busdt_preview(client, Decimal("0"))


def _build_approve_outcome_preview(client: OnchainClient, market: str, token_id: int, amount: Decimal) -> None:
    try:
        tx = client.build_approve_outcome_tx(market, token_id, amount)
        gas = _estimate_cost_or_error(client, tx)
        st.json({"sent": False, "gas_cost": gas, "transaction": _json_safe_tx(tx)})
    except Exception as exc:
        st.error(str(exc))


def _build_revoke_outcome_preview(client: OnchainClient, market: str, token_id: int) -> None:
    _build_approve_outcome_preview(client, market, token_id, Decimal("0"))


def _build_buy_preview(client: OnchainClient, market: str, token_id: int, amount: Decimal) -> None:
    try:
        tx = client.build_buy_tx(market, token_id, amount)
        cost = client.simulate_mint_cost(market, token_id, amount, tx=tx)
        st.json({"sent": False, "cost": _cost_to_dict(cost), "transaction": _json_safe_tx(tx)})
    except Exception as exc:
        st.error(str(exc))


def _build_sell_preview(client: OnchainClient, market: str, token_id: int, amount: Decimal) -> None:
    try:
        tx = client.build_sell_tx(market, token_id, amount)
        cost = client.simulate_redeem_cost(market, token_id, amount, tx=tx)
        st.json({"sent": False, "cost": _cost_to_dict(cost), "transaction": _json_safe_tx(tx)})
    except Exception as exc:
        st.error(str(exc))


def _send_buy_box(client: OnchainClient, market: str, token_id: int, amount: Decimal, conn) -> None:
    with st.expander("真实发送 BUY", expanded=False):
        enabled = st.checkbox("我确认这是会花真钱的 BUY", key="send_buy_enabled")
        confirm = st.text_input("输入 SEND REAL BUY 解锁", key="send_buy_confirm")
        if st.button("发送真实 BUY", disabled=not (enabled and confirm == "SEND REAL BUY")):
            tx = client.build_buy_tx(market, token_id, amount)
            tx_hash = client.send_transaction(tx)
            audit(conn, "console_live_buy_sent", {"market": market, "token_id": token_id, "amount_usdt": str(amount), "tx_hash": tx_hash})
            st.success(f"BUY sent: {tx_hash}")


def _send_sell_box(client: OnchainClient, market: str, token_id: int, amount: Decimal, conn) -> None:
    with st.expander("真实发送 SELL", expanded=False):
        enabled = st.checkbox("我确认这是会卖出真实持仓的 SELL", key="send_sell_enabled")
        confirm = st.text_input("输入 SEND REAL SELL 解锁", key="send_sell_confirm")
        if st.button("发送真实 SELL", disabled=not (enabled and confirm == "SEND REAL SELL")):
            tx = client.build_sell_tx(market, token_id, amount)
            tx_hash = client.send_transaction(tx)
            audit(conn, "console_live_sell_sent", {"market": market, "token_id": token_id, "amount_tokens": str(amount), "tx_hash": tx_hash})
            st.success(f"SELL sent: {tx_hash}")


def _paths_tab(settings: Dict[str, Any]) -> None:
    st.subheader("执行路径诊断")
    statuses = check_execution_paths(settings["env_path"], include_network=True)
    st.dataframe([status.to_dict() for status in statuses], width="stretch", hide_index=True)
    st.caption("开源框架公开支持 direct_contract；REST 只用于 market-data 读取。")


def _audit_tab(conn) -> None:
    st.subheader("本地审计")
    report = latest_report(conn)
    left, right = st.columns(2)
    left.json(report)
    rows = [
        dict(row)
        for row in conn.execute(
            """
            SELECT created_at, event_type, payload_json
            FROM audit_log
            ORDER BY id DESC
            LIMIT 30
            """
        ).fetchall()
    ]
    right.dataframe(rows, width="stretch", hide_index=True)


def _estimate_cost_or_error(client: OnchainClient, tx: Dict[str, Any]) -> Any:
    try:
        return asdict(client.estimate_tx_cost(tx))
    except Exception as exc:
        return f"cost_error: {exc}"


def _cost_to_dict(cost) -> Dict[str, Any]:
    payload = asdict(cost)
    if payload.get("gas") is None:
        payload["gas"] = {"gas_units": None, "gas_bnb": None, "bnb_usdt": None, "gas_usdt": None}
    return payload


def _parse_token_ids(value: str) -> List[int]:
    token_ids: List[int] = []
    for part in value.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            token_ids.append(int(part))
        except ValueError:
            continue
    return token_ids or [1, 2, 4]


def _short(address: str) -> str:
    return address if len(address) <= 12 else f"{address[:6]}...{address[-4:]}"


def _fmt(value: Any) -> str:
    try:
        return f"{float(value):,.6f}".rstrip("0").rstrip(".")
    except (TypeError, ValueError):
        return str(value)


def _json_safe_tx(tx: Dict[str, Any]) -> Dict[str, Any]:
    safe: Dict[str, Any] = {}
    for key, value in tx.items():
        if isinstance(value, bytes):
            safe[key] = "0x" + value.hex()
        else:
            safe[key] = value
    return safe


def _style() -> None:
    st.markdown(
        """
        <style>
        .block-container {
            padding-top: 1.4rem;
            padding-bottom: 2rem;
            max-width: 1500px;
        }
        div[data-testid="stMetric"] {
            background: #111827;
            border: 1px solid #243044;
            border-radius: 8px;
            padding: 14px 16px;
        }
        div[data-testid="stMetric"] label,
        div[data-testid="stMetric"] div {
            color: #f9fafb;
        }
        .stTabs [data-baseweb="tab-list"] {
            gap: 6px;
        }
        .stTabs [data-baseweb="tab"] {
            border-radius: 7px;
            padding: 8px 14px;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()
