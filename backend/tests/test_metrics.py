import pytest

from laps import format_hms
from metrics import best_by_driver, pace_by_driver, session_bests


def test_best_by_driver(marked):
    best = best_by_driver(marked[marked["NUMBER"] == "007"]).set_index("DRIVER_NAME")
    assert best.loc["Ana A", "BEST_LAP"] == pytest.approx(94.0)
    assert best.loc["Ana A", "BEST_S1"] == pytest.approx(29.5)
    assert best.loc["Ben B", "BEST_LAP"] == pytest.approx(94.5)
    assert best.loc["Ben B", "BEST_S2"] == pytest.approx(34.6)


def test_session_bests_by_category(marked):
    hyper = session_bests(marked[marked["CLASS"] == "HYPERCAR"]).set_index("METRIC")
    lap = hyper.loc["Mejor vuelta"]
    assert (lap["CAR"], lap["DRIVER"], lap["LAP"]) == ("7", "Carl C", 2)
    assert lap["TIME"] == pytest.approx(93.0)
    assert format_hms(lap["CLOCK"]) == "11:33:33"
    assert hyper.loc["Mejor sector 1", "CAR"] == "7"
    gt3 = session_bests(marked[marked["CLASS"] == "LMGT3"])
    assert set(gt3["CAR"]) == {"99"}


def test_pace_by_driver(marked):
    result = pace_by_driver(marked)
    pbd = result.set_index(["NUMBER", "DRIVER_NAME"])
    assert pbd.loc[("007", "Ana A"), "PACE_LAPS"] == 2        # vueltas 2 y 3
    assert pbd.loc[("007", "Ana A"), "BEST_PACE"] == pytest.approx(94.0)
    assert pbd.loc[("007", "Ana A"), "MEDIAN_PACE"] == pytest.approx(94.5)
    assert pbd.loc[("007", "Ben B"), "PACE_LAPS"] == 1        # solo la 6; 5 es salida, 7 FCY, 8 lenta
    assert pbd.loc[("99", "Dan D"), "MEDIAN_PACE"] == pytest.approx(101.5)
    assert set(result["CLASS"].iloc[:3]) == {"HYPERCAR"}      # ordenado por categoría