import math

from features.transformers import EntityStats


def test_velocity_and_geo_switch(monkeypatch):
    t0 = 1_000_000.0
    stats = EntityStats()

    # 7 tx over 105s (every 15s)
    for i in range(7):
        stats.record_payment(10.0, "m1", "US", "dev1", now=t0 + i * 15)

    # advance time to t0+120s
    monkeypatch.setattr("features.transformers.time.time", lambda: t0 + 120)
    assert math.isclose(stats.txn_count_1m(), 3.0)  # events at t=60,75,90
    assert stats.txn_count_5m() >= 7.0
    assert stats.txn_count_1h() >= 7.0

    # Geo switches
    stats.record_payment(5.0, "m1", "US", "dev1", now=t0 + 125)
    stats.record_payment(5.0, "m1", "DE", "dev1", now=t0 + 130)
    stats.record_payment(5.0, "m1", "US", "dev1", now=t0 + 140)
    monkeypatch.setattr("features.transformers.time.time", lambda: t0 + 140)
    assert stats.geo_switch_24h() >= 2.0
    # Device switches
    stats.record_payment(5.0, "m1", "US", "dev2", now=t0 + 150)
    stats.record_payment(5.0, "m1", "US", "dev3", now=t0 + 160)
    monkeypatch.setattr("features.transformers.time.time", lambda: t0 + 160)
    assert stats.device_switch_24h() >= 2.0
