from trading_bot.symbols import SYMBOLS, all_symbols, get


def test_required_symbols_present():
    assert {"US500", "US100", "GOLD", "EURUSD", "GBPUSD", "USDJPY"} <= set(SYMBOLS)


def test_get_is_case_insensitive():
    assert get("us500").internal == "US500"


def test_all_symbols_returns_list():
    assert len(all_symbols()) >= 6


def test_unknown_symbol_raises():
    import pytest

    with pytest.raises(KeyError):
        get("FOOBAR")
