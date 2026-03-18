import pandas as pd

from backtest.walk_forward import _month_add, _to_utc_ts


def test_month_add_monotonic():
    t0 = pd.Timestamp("2020-01-01", tz="UTC")
    t1 = _month_add(t0, 3)
    t2 = _month_add(t1, 3)
    assert t2 > t1 > t0


def test_to_utc_ts():
    ts = _to_utc_ts("2022-01-01")
    assert ts.tzinfo is not None
