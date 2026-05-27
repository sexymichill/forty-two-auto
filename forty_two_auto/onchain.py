from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, Optional

try:
    asyncio.get_event_loop()
except RuntimeError:
    asyncio.set_event_loop(asyncio.new_event_loop())

from web3 import Web3

from .http import get_json

BNB_CHAIN_ID = 56
FTRouter_ADDRESS = Web3.to_checksum_address("0x888888886619275d33c00D3BC62DF94D700DCD42")
BUSDT_ADDRESS = Web3.to_checksum_address("0x55d398326f99059ff775485246999027b3197955")
LENS_ADDRESS = Web3.to_checksum_address("0x8aF85927Cb4deBE57C47DDE5cdb4665839f55a32")
INTEGRATOR_ADDRESS = Web3.to_checksum_address("0xc60E3415648684b1D0D0D97e85CB21E6a2bCb620")
INTEGRATOR_FEE_BPS = 40
DEFAULT_MAX_ITERATIONS_SIM = 100
DEFAULT_MAX_ITERATIONS_EXECUTE = 50

FTRouter_ABI = [
    {
        "inputs": [
            {"internalType": "address", "name": "market", "type": "address"},
            {"internalType": "address", "name": "receiver", "type": "address"},
            {"internalType": "uint256", "name": "tokenId", "type": "uint256"},
            {
                "components": [
                    {"internalType": "bool", "name": "isMint", "type": "bool"},
                    {"internalType": "uint256", "name": "amount", "type": "uint256"},
                    {"internalType": "bool", "name": "isExactIn", "type": "bool"},
                    {"internalType": "uint256", "name": "minOutOrMaxIn", "type": "uint256"},
                ],
                "internalType": "struct SwapParams",
                "name": "params",
                "type": "tuple",
            },
            {"internalType": "bytes", "name": "dataSwap", "type": "bytes"},
            {"internalType": "bytes", "name": "dataGuess", "type": "bytes"},
            {"internalType": "address", "name": "integrator", "type": "address"},
            {"internalType": "uint256", "name": "integratorFeeBps", "type": "uint256"},
        ],
        "name": "swap",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
]

LENS_ABI = [
    {
        "inputs": [
            {"internalType": "address", "name": "market", "type": "address"},
            {"internalType": "uint256", "name": "tokenId", "type": "uint256"},
            {"internalType": "uint256", "name": "amount", "type": "uint256"},
            {"internalType": "bool", "name": "isExactIn", "type": "bool"},
            {"internalType": "bytes", "name": "dataSwap", "type": "bytes"},
            {"internalType": "bytes", "name": "dataGuess", "type": "bytes"},
            {"internalType": "uint256", "name": "integratorFeeBps", "type": "uint256"},
        ],
        "name": "simulateMint",
        "outputs": [
            {
                "internalType": "struct OtSnapshot",
                "name": "pre",
                "type": "tuple",
                "components": [
                    {"internalType": "uint256", "name": "tokenId", "type": "uint256"},
                    {"internalType": "uint256", "name": "price", "type": "uint256"},
                    {"internalType": "uint256", "name": "supply", "type": "uint256"},
                    {"internalType": "uint256", "name": "totalMarketCap", "type": "uint256"},
                    {"internalType": "uint256", "name": "payoutPerOt", "type": "uint256"},
                    {"internalType": "uint256", "name": "marketCap", "type": "uint256"},
                ],
            },
            {
                "internalType": "struct OtSnapshot",
                "name": "post",
                "type": "tuple",
                "components": [
                    {"internalType": "uint256", "name": "tokenId", "type": "uint256"},
                    {"internalType": "uint256", "name": "price", "type": "uint256"},
                    {"internalType": "uint256", "name": "supply", "type": "uint256"},
                    {"internalType": "uint256", "name": "totalMarketCap", "type": "uint256"},
                    {"internalType": "uint256", "name": "payoutPerOt", "type": "uint256"},
                    {"internalType": "uint256", "name": "marketCap", "type": "uint256"},
                ],
            },
            {
                "internalType": "struct MintQuote",
                "name": "quote",
                "type": "tuple",
                "components": [
                    {"internalType": "uint256", "name": "collateralFromUser", "type": "uint256"},
                    {"internalType": "uint256", "name": "collateralToTreasury", "type": "uint256"},
                    {"internalType": "uint256", "name": "collateralToIntegrator", "type": "uint256"},
                    {"internalType": "uint256", "name": "otToUser", "type": "uint256"},
                ],
            },
        ],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [
            {"internalType": "address", "name": "market", "type": "address"},
            {"internalType": "uint256", "name": "tokenId", "type": "uint256"},
            {"internalType": "uint256", "name": "amount", "type": "uint256"},
            {"internalType": "bool", "name": "isExactIn", "type": "bool"},
            {"internalType": "bytes", "name": "dataSwap", "type": "bytes"},
            {"internalType": "bytes", "name": "dataGuess", "type": "bytes"},
            {"internalType": "uint256", "name": "integratorFeeBps", "type": "uint256"},
        ],
        "name": "simulateRedeem",
        "outputs": [
            {
                "internalType": "struct OtSnapshot",
                "name": "pre",
                "type": "tuple",
                "components": [
                    {"internalType": "uint256", "name": "tokenId", "type": "uint256"},
                    {"internalType": "uint256", "name": "price", "type": "uint256"},
                    {"internalType": "uint256", "name": "supply", "type": "uint256"},
                    {"internalType": "uint256", "name": "totalMarketCap", "type": "uint256"},
                    {"internalType": "uint256", "name": "payoutPerOt", "type": "uint256"},
                    {"internalType": "uint256", "name": "marketCap", "type": "uint256"},
                ],
            },
            {
                "internalType": "struct OtSnapshot",
                "name": "post",
                "type": "tuple",
                "components": [
                    {"internalType": "uint256", "name": "tokenId", "type": "uint256"},
                    {"internalType": "uint256", "name": "price", "type": "uint256"},
                    {"internalType": "uint256", "name": "supply", "type": "uint256"},
                    {"internalType": "uint256", "name": "totalMarketCap", "type": "uint256"},
                    {"internalType": "uint256", "name": "payoutPerOt", "type": "uint256"},
                    {"internalType": "uint256", "name": "marketCap", "type": "uint256"},
                ],
            },
            {
                "internalType": "struct RedeemQuote",
                "name": "quote",
                "type": "tuple",
                "components": [
                    {"internalType": "uint256", "name": "collateralToUser", "type": "uint256"},
                    {"internalType": "uint256", "name": "collateralToTreasury", "type": "uint256"},
                    {"internalType": "uint256", "name": "collateralToIntegrator", "type": "uint256"},
                    {"internalType": "uint256", "name": "otFromUser", "type": "uint256"},
                    {"internalType": "uint256", "name": "collateralMintValue", "type": "uint256"},
                ],
            },
        ],
        "stateMutability": "nonpayable",
        "type": "function",
    },
]

ERC20_ABI = [
    {
        "constant": True,
        "inputs": [{"name": "_owner", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "balance", "type": "uint256"}],
        "type": "function",
    },
    {
        "constant": True,
        "inputs": [{"name": "_owner", "type": "address"}, {"name": "_spender", "type": "address"}],
        "name": "allowance",
        "outputs": [{"name": "remaining", "type": "uint256"}],
        "type": "function",
    },
    {
        "constant": False,
        "inputs": [{"name": "_spender", "type": "address"}, {"name": "_value", "type": "uint256"}],
        "name": "approve",
        "outputs": [{"name": "success", "type": "bool"}],
        "type": "function",
    },
    {
        "constant": True,
        "inputs": [],
        "name": "decimals",
        "outputs": [{"name": "", "type": "uint8"}],
        "type": "function",
    },
]

MARKET_TOKEN_ABI = [
    {
        "inputs": [{"internalType": "address", "name": "owner", "type": "address"}, {"internalType": "uint256", "name": "id", "type": "uint256"}],
        "name": "balanceOf",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [{"internalType": "uint256", "name": "tokenId", "type": "uint256"}],
        "name": "name",
        "outputs": [{"internalType": "string", "name": "", "type": "string"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [
            {"internalType": "address", "name": "owner", "type": "address"},
            {"internalType": "address", "name": "spender", "type": "address"},
            {"internalType": "uint256", "name": "id", "type": "uint256"},
        ],
        "name": "allowance",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [
            {"internalType": "address", "name": "spender", "type": "address"},
            {"internalType": "uint256", "name": "id", "type": "uint256"},
            {"internalType": "uint256", "name": "amount", "type": "uint256"},
        ],
        "name": "approve",
        "outputs": [{"internalType": "bool", "name": "", "type": "bool"}],
        "stateMutability": "nonpayable",
        "type": "function",
    },
]


@dataclass(frozen=True)
class OnchainConfig:
    rpc_url: str
    private_key: str
    wallet_address: Optional[str] = None


@dataclass(frozen=True)
class OnchainCheck:
    connected: bool
    chain_id: int
    wallet_address: str
    bnb_balance: float
    busdt_balance: float
    busdt_allowance_to_router: float


@dataclass(frozen=True)
class OutcomePosition:
    market_address: str
    token_id: int
    name: str
    raw_balance: int
    balance: float
    raw_allowance_to_router: int
    allowance_to_router: float


@dataclass(frozen=True)
class OnchainTxCost:
    gas_units: int
    gas_price_wei: int
    gas_bnb: float
    bnb_usdt: Optional[float]
    gas_usdt: Optional[float]


@dataclass(frozen=True)
class OnchainSwapCost:
    side: str
    amount_in: float
    expected_out: float
    treasury_fee_usdt: float
    integrator_fee_usdt: float
    protocol_fee_usdt: float
    gas: Optional[OnchainTxCost] = None

    @property
    def total_cost_usdt(self) -> Optional[float]:
        if self.gas is None or self.gas.gas_usdt is None:
            return None
        return self.protocol_fee_usdt + self.gas.gas_usdt


def load_dotenv(path: str | Path = ".env") -> None:
    env_path = Path(path)
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def load_onchain_config(env_path: str | Path = ".env") -> OnchainConfig:
    load_dotenv(env_path)
    return OnchainConfig(
        rpc_url=os.environ.get("FORTY_TWO_BSC_RPC_URL", "https://bsc-dataseed.binance.org"),
        private_key=os.environ.get("FORTY_TWO_PRIVATE_KEY", ""),
        wallet_address=os.environ.get("FORTY_TWO_WALLET_ADDRESS") or None,
    )


class OnchainClient:
    def __init__(self, config: OnchainConfig):
        if not config.private_key:
            raise ValueError("FORTY_TWO_PRIVATE_KEY is required for onchain commands")
        self.config = config
        self.w3 = Web3(Web3.HTTPProvider(config.rpc_url, request_kwargs={"timeout": 20}))
        self.account = self.w3.eth.account.from_key(config.private_key)
        if config.wallet_address and Web3.to_checksum_address(config.wallet_address) != self.account.address:
            raise ValueError("FORTY_TWO_WALLET_ADDRESS does not match FORTY_TWO_PRIVATE_KEY")
        self.router = self.w3.eth.contract(address=FTRouter_ADDRESS, abi=FTRouter_ABI)
        self.lens = self.w3.eth.contract(address=LENS_ADDRESS, abi=LENS_ABI)
        self.busdt = self.w3.eth.contract(address=BUSDT_ADDRESS, abi=ERC20_ABI)

    def check(self) -> OnchainCheck:
        chain_id = int(self.w3.eth.chain_id)
        decimals = int(self.busdt.functions.decimals().call())
        return OnchainCheck(
            connected=self.w3.is_connected(),
            chain_id=chain_id,
            wallet_address=self.account.address,
            bnb_balance=float(self.w3.from_wei(self.w3.eth.get_balance(self.account.address), "ether")),
            busdt_balance=_from_units(self.busdt.functions.balanceOf(self.account.address).call(), decimals),
            busdt_allowance_to_router=_from_units(
                self.busdt.functions.allowance(self.account.address, FTRouter_ADDRESS).call(),
                decimals,
            ),
        )

    def build_approve_busdt_tx(self, amount_usdt: Decimal) -> Dict[str, Any]:
        decimals = int(self.busdt.functions.decimals().call())
        amount = _to_units(amount_usdt, decimals)
        return self.busdt.functions.approve(FTRouter_ADDRESS, amount).build_transaction(self._tx_base())

    def build_buy_tx(
        self,
        market_address: str,
        token_id: int,
        amount_usdt: Decimal,
        min_out: int = 0,
        data_swap: bytes = b"",
        data_guess: bytes = b"",
    ) -> Dict[str, Any]:
        amount = _to_units(amount_usdt, int(self.busdt.functions.decimals().call()))
        market = Web3.to_checksum_address(market_address)
        if not data_guess:
            simulated_ot_out = self.simulate_mint_ot_out(market, token_id, amount, data_swap=data_swap)
            data_guess = _encode_data_guess(
                self.w3,
                simulated_ot_out,
                DEFAULT_MAX_ITERATIONS_EXECUTE,
                _smart_eps(float(amount_usdt)),
            )
            if min_out <= 0:
                min_out = simulated_ot_out * 99 // 100
        params = (True, amount, True, int(min_out))
        return self.router.functions.swap(
            market,
            self.account.address,
            int(token_id),
            params,
            data_swap,
            data_guess,
            INTEGRATOR_ADDRESS,
            INTEGRATOR_FEE_BPS,
        ).build_transaction({**self._tx_base(), "gas": 700000})

    def simulate_mint_cost(
        self,
        market_address: str,
        token_id: int,
        amount_usdt: Decimal,
        tx: Optional[Dict[str, Any]] = None,
        data_swap: bytes = b"",
    ) -> OnchainSwapCost:
        amount = _to_units(amount_usdt, int(self.busdt.functions.decimals().call()))
        result = self._simulate_mint(market_address, token_id, amount, data_swap=data_swap)
        quote = result[2]
        treasury = _from_units(int(quote[1]), 18)
        integrator = _from_units(int(quote[2]), 18)
        gas = self.estimate_tx_cost(tx) if tx is not None else None
        return OnchainSwapCost(
            side="buy",
            amount_in=float(amount_usdt),
            expected_out=_from_units(int(quote[3]), 18),
            treasury_fee_usdt=treasury,
            integrator_fee_usdt=integrator,
            protocol_fee_usdt=treasury + integrator,
            gas=gas,
        )

    def build_approve_outcome_tx(self, market_address: str, token_id: int, amount_tokens: Decimal) -> Dict[str, Any]:
        market = self._market_contract(market_address)
        amount = _to_units(amount_tokens, 18)
        return market.functions.approve(FTRouter_ADDRESS, int(token_id), amount).build_transaction(self._tx_base())

    def build_sell_tx(
        self,
        market_address: str,
        token_id: int,
        amount_tokens: Decimal,
        min_out: int = 0,
        data_swap: bytes = b"",
        data_guess: bytes = b"",
    ) -> Dict[str, Any]:
        amount = _to_units(amount_tokens, 18)
        market = Web3.to_checksum_address(market_address)
        if min_out <= 0:
            simulated_collateral_out = self.simulate_redeem_collateral_out(market, token_id, amount, data_swap=data_swap)
            min_out = simulated_collateral_out * 99 // 100
        params = (False, amount, True, int(min_out))
        return self.router.functions.swap(
            market,
            self.account.address,
            int(token_id),
            params,
            data_swap,
            data_guess,
            INTEGRATOR_ADDRESS,
            INTEGRATOR_FEE_BPS,
        ).build_transaction({**self._tx_base(), "gas": 700000})

    def simulate_redeem_cost(
        self,
        market_address: str,
        token_id: int,
        amount_tokens: Decimal,
        tx: Optional[Dict[str, Any]] = None,
        data_swap: bytes = b"",
        data_guess: bytes = b"",
    ) -> OnchainSwapCost:
        amount = _to_units(amount_tokens, 18)
        result = self._simulate_redeem(market_address, token_id, amount, data_swap=data_swap, data_guess=data_guess)
        quote = result[2]
        treasury = _from_units(int(quote[1]), 18)
        integrator = _from_units(int(quote[2]), 18)
        gas = self.estimate_tx_cost(tx) if tx is not None else None
        return OnchainSwapCost(
            side="sell",
            amount_in=float(amount_tokens),
            expected_out=_from_units(int(quote[0]), 18),
            treasury_fee_usdt=treasury,
            integrator_fee_usdt=integrator,
            protocol_fee_usdt=treasury + integrator,
            gas=gas,
        )

    def simulate_mint_ot_out(
        self,
        market_address: str,
        token_id: int,
        amount: int,
        data_swap: bytes = b"",
    ) -> int:
        data_guess = _encode_data_guess(
            self.w3,
            0,
            DEFAULT_MAX_ITERATIONS_SIM,
            _smart_sim_eps(_from_units_decimal(amount, int(self.busdt.functions.decimals().call()))),
        )
        result = self._simulate_mint(market_address, token_id, amount, data_swap=data_swap, data_guess=data_guess)
        return int(result[2][3])

    def simulate_redeem_collateral_out(
        self,
        market_address: str,
        token_id: int,
        amount: int,
        data_swap: bytes = b"",
        data_guess: bytes = b"",
    ) -> int:
        result = self._simulate_redeem(market_address, token_id, amount, data_swap=data_swap, data_guess=data_guess)
        return int(result[2][0])

    def outcome_position(self, market_address: str, token_id: int) -> OutcomePosition:
        market = self._market_contract(market_address)
        raw_balance = int(market.functions.balanceOf(self.account.address, int(token_id)).call())
        raw_allowance = int(market.functions.allowance(self.account.address, FTRouter_ADDRESS, int(token_id)).call())
        try:
            name = str(market.functions.name(int(token_id)).call())
        except Exception:
            name = str(token_id)
        return OutcomePosition(
            market_address=Web3.to_checksum_address(market_address),
            token_id=int(token_id),
            name=name,
            raw_balance=raw_balance,
            balance=_from_units(raw_balance, 18),
            raw_allowance_to_router=raw_allowance,
            allowance_to_router=_from_units(raw_allowance, 18),
        )

    def estimate_gas(self, tx: Dict[str, Any]) -> int:
        return int(self.w3.eth.estimate_gas(tx))

    def estimate_tx_cost(self, tx: Dict[str, Any], bnb_usdt: Optional[float] = None) -> OnchainTxCost:
        gas_units = self.estimate_gas(tx)
        gas_price_wei = int(tx.get("gasPrice") or self.w3.eth.gas_price)
        gas_bnb = float(self.w3.from_wei(gas_units * gas_price_wei, "ether"))
        if bnb_usdt is None:
            bnb_usdt = fetch_bnb_usdt_price()
        gas_usdt = gas_bnb * bnb_usdt if bnb_usdt is not None else None
        return OnchainTxCost(
            gas_units=gas_units,
            gas_price_wei=gas_price_wei,
            gas_bnb=gas_bnb,
            bnb_usdt=bnb_usdt,
            gas_usdt=gas_usdt,
        )

    def send_transaction(self, tx: Dict[str, Any]) -> str:
        signed = self.w3.eth.account.sign_transaction(tx, self.config.private_key)
        raw_transaction = getattr(signed, "rawTransaction", None) or getattr(signed, "raw_transaction")
        tx_hash = self.w3.eth.send_raw_transaction(raw_transaction)
        return self.w3.to_hex(tx_hash)

    def _tx_base(self) -> Dict[str, Any]:
        return {
            "from": self.account.address,
            "chainId": BNB_CHAIN_ID,
            "nonce": self.w3.eth.get_transaction_count(self.account.address),
            "gasPrice": self.w3.eth.gas_price,
            "value": 0,
        }

    def _market_contract(self, market_address: str):
        return self.w3.eth.contract(address=Web3.to_checksum_address(market_address), abi=MARKET_TOKEN_ABI)

    def _simulate_mint(
        self,
        market_address: str,
        token_id: int,
        amount: int,
        data_swap: bytes = b"",
        data_guess: bytes = b"",
    ):
        if not data_guess:
            data_guess = _encode_data_guess(
                self.w3,
                0,
                DEFAULT_MAX_ITERATIONS_SIM,
                _smart_sim_eps(_from_units_decimal(amount, int(self.busdt.functions.decimals().call()))),
            )
        return self.lens.functions.simulateMint(
            Web3.to_checksum_address(market_address),
            int(token_id),
            int(amount),
            True,
            data_swap,
            data_guess,
            INTEGRATOR_FEE_BPS,
        ).call({"from": self.account.address})

    def _simulate_redeem(
        self,
        market_address: str,
        token_id: int,
        amount: int,
        data_swap: bytes = b"",
        data_guess: bytes = b"",
    ):
        return self.lens.functions.simulateRedeem(
            Web3.to_checksum_address(market_address),
            int(token_id),
            int(amount),
            True,
            data_swap,
            data_guess,
            INTEGRATOR_FEE_BPS,
        ).call({"from": self.account.address})


def _to_units(amount: Decimal, decimals: int) -> int:
    return int(amount * (Decimal(10) ** decimals))


def _from_units(amount: int, decimals: int) -> float:
    return float(Decimal(amount) / (Decimal(10) ** decimals))


def _from_units_decimal(amount: int, decimals: int) -> Decimal:
    return Decimal(amount) / (Decimal(10) ** decimals)


def _encode_data_guess(w3: Web3, ot_delta_guess: int, max_iterations: int, eps: int) -> bytes:
    return w3.codec.encode(["uint256", "uint256", "uint256"], [int(ot_delta_guess), int(max_iterations), int(eps)])


def _smart_sim_eps(amount: Decimal) -> int:
    if amount < Decimal("5"):
        return 50_000_000_000_000_000
    if amount <= Decimal("1000"):
        return 1_000_000_000_000_000
    return int(Decimal(10) ** 18 / amount)


def _smart_eps(amount: float) -> int:
    if amount < 5:
        return 200_000_000_000_000_000
    if amount <= 3000:
        return 1_000_000_000_000_000
    return int(10**18 / amount)


def fetch_bnb_usdt_price() -> Optional[float]:
    try:
        payload = get_json(
            "https://data-api.binance.vision/api/v3/ticker/price",
            params={"symbol": "BNBUSDT"},
            timeout=6.0,
            retries=1,
        )
        return float(payload["price"])
    except Exception:
        return None
