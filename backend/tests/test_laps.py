import pytest

from laps import (
    format_gap, format_hms, format_lap_time, lap_series, list_cars, list_categories, mark_pace_laps,
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


def test_laps_under_a_flag_are_not_confused_with_slow_laps(tmp_path):
    from helpers import car_rows, pace, write_session
    from importer import import_data
    rows = car_rows("5", [
        (120.0, "Ana A", None, False, "GF"),     # 1 salida
        pace(95.0, "Ana A"),                     # 2 ritmo
        (95.2, "Ana A", None, False, "VSC"),     # 3 bajo VSC aunque el tiempo sea normal
        (110.0, "Ana A", None, False, "GF"),     # 4 lenta de verdad (sin bandera)
        (112.0, "Ana A", None, False, "SC"),     # 5 lenta, pero bajo Safety Car
        (130.0, "Ana A", None, True, "FCY"),     # 6 entrada a boxes bajo FCY
        (140.0, "Ana A", None, False, "RF"),     # 7 salida tras bandera roja
        (95.1, "Ana A", None, False, "FF"),      # 8 bandera final: vuelta normal
    ])
    df = mark_pace_laps(import_data(write_session(tmp_path / "f.csv", rows))).set_index("LAP_NUMBER")
    assert df["LAP_STATUS"].tolist() == [
        "Salida de boxes", "Vuelta de ritmo", "Bandera VSC", "Lenta (>107 % de la mejor)",
        "Bandera SC", "Bandera FCY", "Bandera RF", "Vuelta de ritmo",
    ]
    assert df["FLAG"].tolist() == ["", "", "VSC", "", "SC", "FCY", "RF", ""]
    assert df["IS_FLAG_LAP"].tolist() == [False, False, True, False, True, True, True, False]
    assert df.loc[6, "IS_IN_LAP"] and df.loc[7, "IS_OUT_LAP"]       # la bandera no borra lo de boxes
    assert df.index[df["IS_PACE_LAP"]].tolist() == [2, 8]


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


def test_format_gap():
    assert format_gap(0.328) == "+0.328"
    assert format_gap(12.0) == "+12.000"
    assert format_gap(None) == "–"