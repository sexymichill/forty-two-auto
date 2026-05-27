# forty-two-auto

大家好，我是 Michill。

这是我给大家随意做的一个 42space 自动买卖开源脚本框架，名字暂定 `forty-two-auto`。它不是一个“稳赚策略”，也不是一个自动送钱机器；它主要是把 42space 直接合约买入、卖出、授权、撤销授权这些基础动作先封装出来。

你可以自己决定买哪个 market / token，然后用这个框架完成 quote、成本估算、approve、buy/mint、sell/redeem、revoke 和审计记录。

当前我自己已经用小额真实链上交易测试过 direct-contract 的 buy/sell 路径；这只说明执行框架能跑，不代表任何策略一定赚钱。

注意：这个框架使用你自己控制的本地私钥钱包，不是 42 页面里的平台钱包。你需要自己给这个钱包充值、授权、签名和交易。

所有路径都必须显式计算或标记成本：42/curve 费用、integrator fee、滑点保护、链上 gas。估不出来时会显示 unknown / null，不把未知成本当成 0。

它只负责自动买卖的执行基础设施：

- 扫描 42space markets
- 获取 market detail、prices、price history、OHLC
- 生成 buy/mint 与 sell/redeem quote
- 记录 paper trade 和 dry-run order plan
- 构造和发送 direct contract buy/sell/revoke
- 本地 Protocol Console，看钱包、盘口、持仓、交易构造和执行路径
- 用 SQLite 保存 markets、outcomes、quotes、orders、fills、audit logs

它不内置信号器、不内置“保证赚钱”的策略，不绕过平台规则、地区限制、KYC、平台钱包或账号限制。

## 安全模型

执行模式：

| 模式 | 用途 | 是否发送链上交易 |
| --- | --- | --- |
| `paper` | 本地模拟买入/卖出并写入 fill | 否 |
| `dry-run` | 生成 quote、风控结果和订单计划 | 否 |
| `live` | 通用策略层真实执行入口 | 当前版本否 |
| `onchain` | 本地私钥钱包直接合约测试 | 显式 `--send` 且通过发送门禁后才会 |

当前分层：

- `live` 命令指的是通用策略层执行适配器，目前只是带风控门禁的骨架，默认 blocked。
- 默认 quote provider 返回 `confidence=estimated` 和 `executable=false`。
- 默认估算 quote 会计算价格侧费用和滑点假设；链上 gas 未估算时显示 `gas_usdt=null`。
- `onchain` 是直接合约路径，可以从本地 `.env` 读取私钥，构造和发送真实链上 approve/buy/sell/revoke；私钥不会写入数据库、日志或输出。
- 未来如果要把“策略自动选择 + 真实执行”接成一条完整流水线，应从策略层拿信号，再调用 direct-contract 执行，并保留金额上限、kill switch、审计日志。
- Protocol Console 也只从本地 `.env` 读取配置，不会在页面展示私钥。

## 安装

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

## 配置

复制示例配置，只在本地 `.env` 填写私有信息。

```bash
cp .env.example .env
```

只有 direct-contract 相关命令会读取 `.env` 里的 `FORTY_TWO_PRIVATE_KEY`，包括 `onchain` 子命令和 `examples/auto_buy_sell.py`。不要把私钥发给任何人，也不要提交 `.env`。

`.env.example` 可以提交，真实 `.env` 不要提交。

## 快速开始

扫描 live markets：

```bash
python -m forty_two_auto.cli scan once --limit 50
```

生成估算 quote：

```bash
python -m forty_two_auto.cli quote \
  --market <MARKET_ADDRESS> \
  --token <TOKEN_ID> \
  --side buy \
  --amount-usdt 10
```

记录 paper buy：

```bash
python -m forty_two_auto.cli paper buy \
  --market <MARKET_ADDRESS> \
  --token <TOKEN_ID> \
  --amount-usdt 10
```

记录 dry-run 订单计划：

```bash
python -m forty_two_auto.cli plan-order buy \
  --market <MARKET_ADDRESS> \
  --token <TOKEN_ID> \
  --amount-usdt 10
```

查看本地报告：

```bash
python -m forty_two_auto.cli report
```

运行示例策略：

```bash
python -m forty_two_auto.cli strategy run \
  --strategy examples.simple_strategy:ExampleStrategy \
  --mode paper \
  --limit 50
```

打开本地控制台：

```bash
streamlit run forty_two_auto/console_app.py
```

最小自动买卖脚本：

```bash
python examples/auto_buy_sell.py \
  --env .env \
  --market <MARKET_ADDRESS> \
  --token <TOKEN_ID> \
  buy \
  --amount-usdt 10
```

默认只预览，不发交易。确认要真实发送时加：

```bash
python examples/auto_buy_sell.py \
  --env .env \
  --market <MARKET_ADDRESS> \
  --token <TOKEN_ID> \
  --send \
  --i-understand-real-money \
  buy \
  --amount-usdt 10 \
  --auto-approve
```

如果是机器人或定时任务，不应该每一笔 approve/buy/sell 都人工确认。可以在 `.env` 里一次性打开 unattended live gate：

```bash
FORTY_TWO_ENABLE_LIVE=true
FORTY_TWO_CONFIRM_COMPLIANCE=true
FORTY_TWO_KILL_SWITCH=false
FORTY_TWO_UNATTENDED_LIVE=true
FORTY_TWO_MAX_TRADE_USDT=20
FORTY_TWO_MAX_AUTO_APPROVE_USDT=20
```

然后脚本可以非交互发送：

```bash
python examples/auto_buy_sell.py \
  --env .env \
  --market <MARKET_ADDRESS> \
  --token <TOKEN_ID> \
  --send \
  buy \
  --amount-usdt 10 \
  --auto-approve
```

这里的 `--auto-approve` 不是无限授权，只会按本次交易需要的额度构造精确 approve。超过 `.env` 里的最大金额会直接拒绝。

## CLI 命令

```bash
python -m forty_two_auto.cli scan once --limit 50
python -m forty_two_auto.cli scan loop --interval 10
python -m forty_two_auto.cli quote --market <MARKET_ADDRESS> --token <TOKEN_ID> --side buy --amount-usdt 10
python -m forty_two_auto.cli paper buy --market <MARKET_ADDRESS> --token <TOKEN_ID> --amount-usdt 10
python -m forty_two_auto.cli paper sell --market <MARKET_ADDRESS> --token <TOKEN_ID> --amount-usdt 10
python -m forty_two_auto.cli plan-order buy --market <MARKET_ADDRESS> --token <TOKEN_ID> --amount-usdt 10
python -m forty_two_auto.cli live buy --market <MARKET_ADDRESS> --token <TOKEN_ID> --amount-usdt 10
python -m forty_two_auto.cli strategy run --strategy examples.simple_strategy:ExampleStrategy --mode paper --limit 50
python -m forty_two_auto.cli onchain check --env .env
python -m forty_two_auto.cli onchain build-buy --env .env --market <MARKET_ADDRESS> --token <TOKEN_ID> --amount-usdt 10
python -m forty_two_auto.cli onchain positions --env .env --market <MARKET_ADDRESS> --tokens 1,2,4
python -m forty_two_auto.cli onchain build-sell --env .env --market <MARKET_ADDRESS> --token <TOKEN_ID> --amount-tokens 1
python -m forty_two_auto.cli onchain revoke-busdt --env .env
python -m forty_two_auto.cli onchain revoke-outcome --env .env --market <MARKET_ADDRESS> --token <TOKEN_ID>
python -m forty_two_auto.cli modes
python -m forty_two_auto.cli paths --env .env
python -m forty_two_auto.cli report --json
python examples/auto_buy_sell.py --env .env --market <MARKET_ADDRESS> --token <TOKEN_ID> buy --amount-usdt 10
python examples/auto_buy_sell.py --env .env --market <MARKET_ADDRESS> --token <TOKEN_ID> sell --amount-tokens 1
```

当前版本的 `live` 命令应该返回 blocked，因为 verified executable quote 和 signer integration 还没有实现。

## Protocol Console

本地可视化控制台适合给开源用户检查自己的接入是否跑通：

```bash
streamlit run forty_two_auto/console_app.py
```

它包含：

- 钱包：BNB、BUSDT、router allowance。
- 盘口：扫描 live markets、分类并写入 SQLite。
- 持仓：按 market/token 读取本地私钥钱包的 outcome token。
- 交易实验室：构造 BUSDT approve/revoke、buy/mint、outcome approve/revoke、sell/redeem 交易，显示 protocol fee、integrator fee、gas 和总成本。
- 执行路径：检查直接合约和 REST market-data 两条公开路径。
- 审计：展示本地 orders/fills/audit log。

注意：Console 看的是 `.env` 对应钱包的链上持仓。

## 接入自己的策略

如果你已经有自己的策略，只需要实现一个 `generate(markets)` 方法并返回 `StrategySignal`。

框架会负责：

- 写入 market 和 outcome 快照
- 生成 quote
- 执行风险检查
- 跑 paper / dry-run / live-gated execution
- 写入 orders、fills 和 audit logs

最小示例：

```python
from forty_two_auto.market_data import FortyTwoClient
from forty_two_auto.storage import connect
from forty_two_auto.strategy import StrategySignal, run_strategy


class MyStrategy:
    def generate(self, markets):
        for market in markets:
            if "FDV" in market["question"]:
                yield StrategySignal(
                    market_address=market["address"],
                    token_id=market["outcomes"][0]["tokenId"],
                    side="buy",
                    amount_usdt=10,
                    reason="my model says this outcome is mispriced",
                    metadata={"edge": 0.12},
                )


client = FortyTwoClient()
markets, _ = client.markets(status="live", limit=50)

conn = connect("data/forty_two_auto.sqlite3")
results = run_strategy(conn, markets, MyStrategy(), mode="paper")
```

同一套策略也可以跑 dry-run：

```python
results = run_strategy(conn, markets, MyStrategy(), mode="dry-run")
```

`mode="live"` 也使用同一套接口，但当前版本默认会被风控拦住。

也可以通过 CLI 直接运行一个策略类：

```bash
python -m forty_two_auto.cli strategy run \
  --strategy examples.simple_strategy:ExampleStrategy \
  --mode dry-run \
  --limit 50
```

如果未来要测试 live，也仍然走同一条命令，但当前版本会被拦住：

```bash
python -m forty_two_auto.cli strategy run \
  --strategy examples.simple_strategy:ExampleStrategy \
  --mode live \
  --enable-live \
  --confirm-compliance \
  --limit 50
```

这不是 bug，而是安全门禁：当前还没有 verified quote/redeem route 和 signer integration。

## 执行路径

查看自动化模式：

```bash
python -m forty_two_auto.cli modes
```

当前有 4 个模式：

| 模式 | 状态 | 是否发交易 | 用途 |
| --- | --- | --- | --- |
| `scan/read-only` | ready | 否 | 扫描、分类、保存盘口 |
| `paper` | ready | 否 | 本地模拟成交 |
| `dry-run/plan` | ready | 否 | 生成 quote、风控结果和订单计划 |
| `direct_contract` | pilot | 是 | 本地私钥钱包直接合约执行 |

框架现在把公开执行分成两条路径：

| 路径 | 当前状态 | 开源框架怎么处理 |
| --- | --- | --- |
| 直接合约 | 已接入本地私钥钱包构造 approve/buy/sell | P0，适合做自动化执行适配器 |
| 官方 REST / 内部 API | 只确认 market-data 读取 | 只读，不假设可以下单 |

诊断命令：

```bash
python -m forty_two_auto.cli paths --env .env
```

## 链上真实交易检查

42 官方部署在 BNB Chain。真实交易使用的是你自己的本地私钥钱包，不是 42 页面里的平台钱包。开始前先检查钱包、BNB gas 和 BUSDT 状态：

```bash
python -m forty_two_auto.cli onchain check --env .env
```

构造一笔 FTRouter `swap` buy 交易：

```bash
python -m forty_two_auto.cli onchain build-buy \
  --env .env \
  --market <MARKET_ADDRESS> \
  --token <TOKEN_ID> \
  --amount-usdt 10 \
  --min-out <MIN_OUT_TOKEN_UNITS>
```

默认只构造、模拟 quote、估算 gas 和费用，不发送交易。`--min-out` 不传或为 0 时，框架会先用 Lens simulation 估算输出，再自动填一个 99% 的保护值。

如果 BUSDT allowance 不够，先构造或发送授权交易：

```bash
python -m forty_two_auto.cli onchain approve-busdt \
  --env .env \
  --amount-usdt 10
```

确认无误后可以用逐次确认方式发送授权：

```bash
python -m forty_two_auto.cli onchain approve-busdt \
  --env .env \
  --amount-usdt 10 \
  --send \
  --i-understand-real-money
```

如果你已经确认自己符合法律、平台规则、市场规则、资金风险，并且确认该 market/token/amount 都正确，可以用逐次确认方式显式发送：

```bash
python -m forty_two_auto.cli onchain build-buy \
  --env .env \
  --market <MARKET_ADDRESS> \
  --token <TOKEN_ID> \
  --amount-usdt 10 \
  --min-out <MIN_OUT_TOKEN_UNITS> \
  --send \
  --i-understand-real-money
```

查看持仓：

```bash
python -m forty_two_auto.cli onchain positions \
  --env .env \
  --market <MARKET_ADDRESS> \
  --tokens 1,2,4
```

构造 outcome token 授权：

```bash
python -m forty_two_auto.cli onchain approve-outcome \
  --env .env \
  --market <MARKET_ADDRESS> \
  --token <TOKEN_ID> \
  --amount-tokens 1
```

撤销 BUSDT 授权：

```bash
python -m forty_two_auto.cli onchain revoke-busdt --env .env
```

发送撤销 BUSDT 授权：

```bash
python -m forty_two_auto.cli onchain revoke-busdt \
  --env .env \
  --send \
  --i-understand-real-money
```

所有 `onchain ... --send` 命令也支持同一套 unattended live gate。`.env` 同时满足 `FORTY_TWO_UNATTENDED_LIVE=true`、`FORTY_TWO_ENABLE_LIVE=true`、`FORTY_TWO_CONFIRM_COMPLIANCE=true`、`FORTY_TWO_KILL_SWITCH=false` 时，可以不带 `--i-understand-real-money`，适合机器人或定时任务调用。

撤销 outcome token 授权：

```bash
python -m forty_two_auto.cli onchain revoke-outcome \
  --env .env \
  --market <MARKET_ADDRESS> \
  --token <TOKEN_ID>
```

构造 sell/redeem：

```bash
python -m forty_two_auto.cli onchain build-sell \
  --env .env \
  --market <MARKET_ADDRESS> \
  --token <TOKEN_ID> \
  --amount-tokens 1
```

发送 sell/redeem，逐次确认版本：

```bash
python -m forty_two_auto.cli onchain build-sell \
  --env .env \
  --market <MARKET_ADDRESS> \
  --token <TOKEN_ID> \
  --amount-tokens 1 \
  --send \
  --i-understand-real-money
```

注意：任何带 `--send` 的命令都会使用 `.env` 中的私钥签名并发送真实链上交易。不要在聊天、日志、截图或代码仓库里暴露私钥。无人值守模式不是放开风控，只是把“每笔人工确认”升级成“一次性 live gate + 金额上限 + kill switch”。

## 项目结构

```text
forty_two_auto/
  market_data.py   # 42 REST API client
  classifier.py    # market type classifier
  quotes.py        # buy/sell quote request/result objects
  strategy.py      # third-party strategy signal hook
  risk.py          # paper/dry-run/live risk gates
  execution.py     # paper, dry-run, and live adapter skeletons
  execution_paths.py # execution path diagnostics
  onchain.py       # BNB Chain direct contract adapter
  storage.py       # SQLite schema and persistence helpers
  console_app.py   # local Streamlit Protocol Console
  cli.py           # command-line interface
```

## 数据存储

默认 SQLite 路径：

```text
data/forty_two_auto.sqlite3
```

数据库保存：

- markets
- outcomes
- market snapshots
- outcome snapshots
- quotes
- orders
- fills
- audit logs

`data/` 默认不提交。

## 环境变量

用 `.env.example` 作为模板。

```bash
FORTY_TWO_REST_BASE=https://rest.ft.42.space
FORTY_TWO_BSC_RPC_URL=https://bsc-dataseed.binance.org
FORTY_TWO_DEFAULT_MODE=paper
FORTY_TWO_ENABLE_LIVE=false
FORTY_TWO_CONFIRM_COMPLIANCE=false
FORTY_TWO_KILL_SWITCH=true
FORTY_TWO_UNATTENDED_LIVE=false
FORTY_TWO_WALLET_ADDRESS=
FORTY_TWO_PRIVATE_KEY=
FORTY_TWO_MAX_TRADE_USDT=20
FORTY_TWO_DAILY_RISK_CAP_USDT=100
FORTY_TWO_MAX_AUTO_APPROVE_USDT=20
FORTY_TWO_MAX_AUTO_APPROVE_TOKENS=1000000
FORTY_TWO_RECEIPT_TIMEOUT_SECONDS=120
```

`FORTY_TWO_PRIVATE_KEY` 在提交文件里必须保持为空。以后如果接入个人版或 live adapter，也应该从本地环境变量或外部 signer 读取。

## 测试

运行框架测试：

```bash
python -m unittest tests/test_forty_two_auto.py -v
```

编译检查开源框架：

```bash
python -m compileall forty_two_auto tests/test_forty_two_auto.py
```

## 限制

- 当前 quote 是保守估算。
- 通用 `live` 策略层还没有接入 verified executable quote。
- `onchain` 是直接合约路径，本地私钥模式已经支持构造和发送 approve/buy/sell；开源用户仍需自己确认 market、token、金额、地区、平台规则和资金风险。
- 非 direct_contract 的网页会话自动化、信号器和策略雷达不包含在开源版里。
- 没有内置任何保证盈利的策略。
- 未完成平台规则、verified quotes、fees、slippage、gas、signer safety 和 risk limits 前，不应启用 live execution。
