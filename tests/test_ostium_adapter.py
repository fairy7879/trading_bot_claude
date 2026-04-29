import pytest

from trading_bot.config import Settings
from trading_bot.execution.ostium import OstiumExecutionAdapter


class _FakeOstium:
    def __init__(self):
        self.trades = []
        self.tps = []
        self.sls = []
        self.closed = []

    def perform_trade(self, params, at_price):
        self.trades.append((params, at_price))
        return {"pair_id": 1, "trade_index": len(self.trades)}

    def update_tp(self, pair_id, trade_index, price):
        self.tps.append((pair_id, trade_index, price))

    def update_sl(self, pair_id, trade_index, price):
        self.sls.append((pair_id, trade_index, price))

    def close_trade(self, pair_id, trade_index):
        self.closed.append((pair_id, trade_index))


class _FakeSDK:
    def __init__(self):
        self.ostium = _FakeOstium()


def _settings(network="sepolia", allow_mainnet=False) -> Settings:
    return Settings(
        twelvedata_api_key="x",
        ostium_private_key="0xdead",
        ostium_rpc_url="http://localhost",
        ostium_network=network,
        ostium_allow_mainnet=allow_mainnet,
    )


def test_mainnet_requires_explicit_allow():
    with pytest.raises(RuntimeError):
        OstiumExecutionAdapter(settings=_settings(network="arbitrum", allow_mainnet=False))


def test_mainnet_with_allow_constructs():
    adapter = OstiumExecutionAdapter(
        settings=_settings(network="arbitrum", allow_mainnet=True), sdk=_FakeSDK()
    )
    assert adapter is not None


def test_open_market_calls_sdk_with_tp_and_sl():
    sdk = _FakeSDK()
    adapter = OstiumExecutionAdapter(settings=_settings(), sdk=sdk)
    res = adapter.open_market(
        "US500", side="long", collateral_usd=10, leverage=5,
        price=4500.0, sl=4480.0, tp=4540.0,
    )
    assert res.ok
    assert len(sdk.ostium.trades) == 1
    assert sdk.ostium.tps == [(1, 1, 4540.0)]
    assert sdk.ostium.sls == [(1, 1, 4480.0)]
    assert adapter.position_side("US500") == "long"


def test_close_calls_sdk_close_trade():
    sdk = _FakeSDK()
    adapter = OstiumExecutionAdapter(settings=_settings(), sdk=sdk)
    adapter.open_market("US500", side="long", collateral_usd=10, leverage=5, price=4500.0)
    res = adapter.close("US500", 4520.0)
    assert res.ok
    assert sdk.ostium.closed == [(1, 1)]
    assert adapter.position_side("US500") == "flat"
