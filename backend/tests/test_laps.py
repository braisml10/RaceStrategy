import pytest

from laps import (
    format_hms, format_lap_time, lap_series, list_cars, list_categories, mark_pace_laps,
)


def car(marked, number):
    return marked[marked["NUMBER"] == number]


def test_format_lap_time():
    assert format_lap_time(92.84) == "01:32.840"
    assert format_lap_time(5.2) == "00:05.200"
    assert format_lap_time(1056.326) == "17:36.326"
    assert format_lap_time(None) == "–"
    assert format_hms(41483.2) == "11:31:23"


def test_car_numbers_keep_leading_zeros(marked):
    assert set(marked["NUMBER"]) == {"007", "7", "99"}
    assert len(car(marked, "007")) == 8 and len(car(marked, "7")) == 2


def test_categories_and_cars(marked):
    assert list_categories(marked) == ["HYPERCAR", "LMGT3"]
    cars = list_cars(marked, "HYPERCAR")
    assert cars["NUMBER"].tolist() == ["007", "7"]  # mismo valor: desempate alfabético
    assert cars.set_index("NUMBER").loc["007", "DRIVERS"] == ["Ana A", "Ben B"]


def test_pace_lap_classification(marked):
    status = car(marked, "007").set_index("LAP_NUMBER")["LAP_STATUS"]
    assert status[1] == "Salida de boxes"      # primera vuelta
    assert status[2] == status[3] == "Vuelta de ritmo"
    assert status[4] == "Entrada a boxes"
    assert status[5] == "Salida de boxes"      # lleva PIT_TIME
    assert status[6] == "Vuelta de ritmo"
    assert status[7] == "Bandera FCY"          # FCY gana a "lenta"
    assert status[8].startswith("Lenta")       # 1:45 > 107 % de 1:34


def test_threshold_is_adjustable(marked):
    relaxed = car(mark_pace_laps(marked, 1.15), "007").set_index("LAP_NUMBER")
    assert relaxed.loc[8, "LAP_STATUS"] == "Vuelta de ritmo"


def test_lap_series(marked):
    series = lap_series(car(marked, "007"))
    assert len(series) == 8
    row = series.set_index("LAP_NUMBER").loc[3]
    assert row["LAP_TIME_TEXT"] == "01:34.000" and row["DRIVER_NAME"] == "Ana A"
    assert row["S1_TEXT"] == "00:29.500"
    pace = lap_series(car(marked, "007"), pace_only=True)
    assert pace["LAP_NUMBER"].tolist() == [2, 3, 6]