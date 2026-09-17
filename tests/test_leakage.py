import numpy as np
import pandas as pd

from retail_outlook.connectors import assumed_release
from retail_outlook.evaluation import (calibration_correction, forecast_steps, make_distributions,
                                       origin_timestamp, target_month, training_bands, current_forecast)
from retail_outlook.storage import Store


def synthetic_records():
    rng = np.random.default_rng(9)
    records = []
    months = pd.date_range("2015-01-01", periods=84, freq="MS")
    for series, start, vol in [("cpi_cooking_oil", 100, .006), ("palm_oil_usd", 700, .05),
                                ("soy_oil_usd", 800, .04), ("usd_sgd", 1.35, .012)]:
        values = start * np.exp(np.cumsum(rng.normal(0, vol, len(months))))
        for period, value in zip(months, values):
            records.append(dict(series_id=series, period=str(period.date()), value=value, source="synthetic test",
                unit="test", source_url="https://example.test", retrieved_at="2026-09-17T08:00:00Z",
                raw_hash="test", assumed_available_at=assumed_release(period, 28), release_assumption="fixture"))
    return records


def test_future_data_mutations_leave_prior_forecasts_unchanged(tmp_path):
    records = synthetic_records()
    store = Store(tmp_path)
    first = store.ingest(records)
    mutated = [dict(r, value=r["value"] * (9 if r["period"] >= "2020-01-01" else 1)) for r in records]
    second = store.ingest(mutated)
    origin = origin_timestamp(pd.Timestamp("2020-01-01"))
    a = store.panel(origin, "reconstructed", first)
    b = store.panel(origin, "reconstructed", second)
    pd.testing.assert_frame_equal(a, b)
    config = dict(models=["seasonal_naive", "ets", "arima", "distributed_lag"], samples=100,
                  seed=42, horizons=[1, 3, 6], max_driver_lag=3)
    ya, da = make_distributions(a, origin, config)
    yb, db = make_distributions(b, origin, config)
    for key in da:
        np.testing.assert_array_equal(da[key].samples, db[key].samples)
    assert training_bands(ya, [1, 3, 6]) == training_bands(yb, [1, 3, 6])


def test_calibration_ignores_unreleased_labels_even_when_values_are_present():
    rows = [dict(model="ets", horizon=6, origin="2020-01-28T15:59:59Z",
                 actual_available_at="2020-08-28T15:59:59Z", raw_q10=99., raw_q90=101., actual=999.)] * 24
    assert calibration_correction(rows, pd.Timestamp("2020-07-28T15:59:59Z"), "ets", 6) == (0., 0)
    correction, count = calibration_correction(rows, pd.Timestamp("2020-08-28T15:59:59Z"), "ets", 6)
    assert correction > 0 and count == 24


def test_horizons_include_publication_bridge():
    origin = origin_timestamp(pd.Timestamp("2020-01-01"))
    assert target_month(origin, 1) == pd.Timestamp("2020-02-01")
    assert forecast_steps(pd.Timestamp("2019-12-01"), target_month(origin, 6)) == 7


def test_off_cycle_forecast_does_not_use_different_distance_calibration(tmp_path):
    s = Store(tmp_path)
    records = synthetic_records()
    # Test clock: all data were actually retrieved in this fixture before the origin.
    records = [dict(r, retrieved_at="2022-01-01T00:00:00Z") for r in records]
    sid = s.ingest(records)
    config = dict(models=["seasonal_naive"], samples=100, seed=42, horizons=[1, 3, 6],
                  max_driver_lag=3, training_start="2015-01-01", origin_day=28, calibration_minimum=24)
    protocol = dict(config=config, unchanged_band_pct={"1": 1., "3": 2., "6": 3.}, snapshot_id=sid)
    prior = pd.DataFrame([dict(model="seasonal_naive", horizon=h, origin="2020-01-28T15:59:59Z",
                              actual_available_at="2020-08-28T15:59:59Z", raw_q10=99., raw_q90=101., actual=999.)
                          for h in [1, 3, 6] for _ in range(24)])
    forecast = current_forecast(s, protocol, prior, {str(h): "seasonal_naive" for h in [1,3,6]},
                                pd.Timestamp("2022-02-17T00:00:00Z"))
    assert all(row["calibration_n"] == 0 for row in forecast["forecasts"])
    assert all("effective_horizon_differs" in row["calibration_provenance"] for row in forecast["forecasts"])
