import pytest

from helpers import STINT_CAR, car_rows, write_session
from importer import import_data
from laps import format_hms, mark_pace_laps
from metrics import best_by_driver, driver_summary, pace_by_driver, ranking_by_metric, session_bests


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


def test_session_bests_have_short_keys(marked):
    keys = session_bests(marked[marked["CLASS"] == "HYPERCAR"])["KEY"].tolist()
    assert keys == ["lap", "s1", "s2", "s3"]


def test_ranking_by_metric(marked):
    hyper = marked[marked["CLASS"] == "HYPERCAR"]
    lap = ranking_by_metric(hyper, "LAP_TIME_SECONDS")
    assert lap["CAR"].tolist() == ["7", "007"]               # una fila por coche, más rápido primero
    assert lap["POSITION"].tolist() == [1, 2]
    assert lap["TIME"].tolist() == pytest.approx([93.0, 94.0])
    assert lap["GAP"].tolist() == pytest.approx([0.0, 1.0])
    assert lap.loc[1, "DRIVER"] == "Ana A" and lap.loc[1, "LAP"] == 3
    s1 = ranking_by_metric(hyper, "S1_SECONDS")
    assert s1["TIME"].tolist() == pytest.approx([29.0, 29.5])


def test_driver_summary(marked):
    summary = driver_summary(marked[marked["NUMBER"] == "007"]).set_index("DRIVER_NAME")
    assert summary.loc["Ana A", "PACE_LAPS"] == 2
    assert summary.loc["Ana A", "MEDIAN_PACE"] == pytest.approx(94.5)
    assert summary.loc["Ben B", "BEST_LAP"] == pytest.approx(94.5)
    assert summary.loc["Ben B", "PACE_LAPS"] == 1


def test_driver_summary_median_gap(tmp_path):
    path = write_session(tmp_path / "s.csv", car_rows("5", STINT_CAR))
    summary = driver_summary(mark_pace_laps(import_data(path))).set_index("DRIVER_NAME")
    assert summary.loc["Ben B", "MEDIAN_PACE"] == pytest.approx(94.2)
    assert summary.loc["Ben B", "MEDIAN_GAP"] == pytest.approx(0.0)      # el más rápido
    assert summary.loc["Ana A", "MEDIAN_GAP"] == pytest.approx(0.95)     # 95.15 - 94.2