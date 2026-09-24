"""Charge estimator tests (TDD): time-to-full is estimated from samples —
iOS exposes no ETA API, so the UI must label it as approximate."""
from app.services.battery import ChargeEstimator


def test_no_data_means_no_eta():
    assert ChargeEstimator().record("u", 55, True, now=1000.0) is None


def test_two_samples_give_eta():
    est = ChargeEstimator()
    assert est.record("u", 50, True, now=0.0) is None  # first sample
    assert est.record("u", 60, True, now=600.0) == 40  # 1%/min -> 40 min left


def test_not_charging_means_no_eta():
    est = ChargeEstimator()
    est.record("u", 50, True, now=0.0)
    assert est.record("u", 55, False, now=600.0) is None


def test_full_battery_means_zero():
    est = ChargeEstimator()
    est.record("u", 99, True, now=0.0)
    assert est.record("u", 100, True, now=60.0) == 0


def test_stale_samples_are_pruned():
    est = ChargeEstimator(window_seconds=600.0)
    est.record("u", 10, True, now=0.0)
    assert est.record("u", 11, True, now=3600.0) is None, \
        "a sample from an hour ago must not set the rate"


def test_flatline_means_no_eta():
    est = ChargeEstimator()
    est.record("u", 55, True, now=0.0)
    assert est.record("u", 55, True, now=600.0) is None


def test_devices_are_tracked_independently():
    est = ChargeEstimator()
    est.record("a", 50, True, now=0.0)
    est.record("b", 10, True, now=0.0)
    assert est.record("a", 60, True, now=600.0) == 40
    assert est.record("b", 20, True, now=600.0) == 80
