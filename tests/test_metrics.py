import numpy as np
import pandas as pd

from retail_outlook.metrics import crps, direction, effect_table, pinball, seasonal_scale


def test_metrics_hand_calculation():
    assert crps(1., np.array([0., 2.])) == .5
    assert crps(1., np.array([1., 1.])) == 0
    assert pinball(3, 1, .1) == .2
    assert pinball(1, 3, .1) == 1.8
    assert seasonal_scale(np.arange(36)) == 12.
    assert np.isnan(seasonal_scale(np.ones(36)))
    assert direction(.2, .2) == "unchanged"


def test_identical_forecasts_have_zero_effect_interval():
    rows = []
    for model in ("random_walk", "seasonal_naive", "ets"):
        for i in range(24):
            rows.append(dict(scope="audit", horizon=3, model=model, origin=str(i), mase=1.,
                absolute_error=1., fallback=None, calibration_n=24, mape=1., smape=1., pinball=.2,
                crps=.5, coverage80=1, raw_coverage80=1, width80=2., interval_score80=2., direction_correct=1))
    table = effect_table(pd.DataFrame(rows), repetitions=30)
    assert (table.skill_lower95 == 0).all() and (table.skill_upper95 == 0).all()
    assert (table.mae_reduction_lower95 == 0).all()
