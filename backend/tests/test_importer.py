import datetime as dt

import pandas as pd
import pytest

from importer import get_data_info, import_data, separate_shared_numbers
from helpers import write_session


def test_csv_semicolon_comma_decimal_and_car_numbers(tmp_path):
    path = write_session(tmp_path / "a.csv", [
        "007; 1; 1; 1:32,840; 28,1; 41,808; 22,9; ; 0:01:32.840; 11:31:32.840; Ana A; T; HYPERCAR; GF; ;",
        "7; 1; 1; 1:33.100; 28.3; 41.9; 22.9; ; 0:01:33.100; 11:31:33.100; Carl C; T; HYPERCAR; GF; ;",
    ])
    df = import_data(path, required_columns=["number", "lap_time"])
    assert df["NUMBER"].tolist() == ["007", "7"]                 # ceros conservados
    assert df["LAP_TIME_SECONDS"].tolist() == pytest.approx([92.84, 93.1])
    assert df["S2_SECONDS"].iloc[0] == pytest.approx(41.808)
    assert df["HOUR_SECONDS"].iloc[0] == pytest.approx(11 * 3600 + 31 * 60 + 32.84)
    assert "UNNAMED: 15" not in df.columns                       # el ';' final no crea columna


def test_excel_with_time_objects(tmp_path):
    pytest.importorskip("openpyxl")
    path = tmp_path / "a.xlsx"
    pd.DataFrame({"Number": ["007", "7"], "Lap Time": [dt.time(0, 1, 32, 840000), "1:33.100"]}).to_excel(path, index=False)
    df = import_data(path)
    assert df["NUMBER"].tolist() == ["007", "7"]
    assert df["LAP_TIME_SECONDS"].tolist() == pytest.approx([92.84, 93.1])


def test_errors(tmp_path):
    with pytest.raises(FileNotFoundError):
        import_data(tmp_path / "no_existe.csv")
    (tmp_path / "a.txt").write_text("x")
    with pytest.raises(ValueError, match="Unsupported"):
        import_data(tmp_path / "a.txt")
    path = write_session(tmp_path / "b.csv", [
        "7; 1; 1; 1:33.100; 1; 1; 1; ; 0:01:33.100; 11:31:33.100; Carl C; T; HYPERCAR; GF; ;"])
    with pytest.raises(ValueError, match="Missing required columns"):
        import_data(path, required_columns=["TYRE"])


def test_data_info(tmp_path):
    path = write_session(tmp_path / "c.csv", [
        "7; 1; 1; 1:33.100; 1; 1; 1; ; 0:01:33.100; 11:31:33.100; Carl C; T; HYPERCAR; GF; ;"])
    info = get_data_info(import_data(path))
    assert info["rows"] == 1 and "NUMBER" in info["column_names"]


def test_shared_number_is_separated_by_team(tmp_path):
    # CSV guardado con Excel: el 007 de Aston y el 7 de Toyota quedan como "7"
    path = write_session(tmp_path / "lost.csv", [
        "7; 1; 1; 1:34.000; 1; 1; 1; ; 0:01:34.000; 11:31:34.000; Ana A; Aston; HYPERCAR; GF; ;",
        "7; 1; 2; 1:35.000; 1; 1; 1; ; 0:03:09.000; 11:33:09.000; Ana A; Aston; HYPERCAR; GF; ;",
        "7; 1; 1; 1:33.000; 1; 1; 1; ; 0:01:33.000; 11:31:33.000; Carl C; Toyota; HYPERCAR; GF; ;",
        "7; 1; 2; 1:33.500; 1; 1; 1; ; 0:03:06.500; 11:33:06.500; Carl C; Toyota; HYPERCAR; GF; ;",
        "99; 1; 1; 1:41.000; 1; 1; 1; ; 0:01:41.000; 11:31:41.000; Dan D; Ford; LMGT3; GF; ;",
    ])
    df, notices = separate_shared_numbers(import_data(path))
    assert sorted(df["NUMBER"].unique()) == ["7 (Aston)", "7 (Toyota)", "99"]
    assert df[df["NUMBER"] == "7 (Aston)"]["DRIVER_NAME"].unique().tolist() == ["Ana A"]
    assert len(notices) == 1 and "Excel" in notices[0] and "7 (Aston); 7 (Toyota)" in notices[0]


def test_correct_numbers_are_left_alone(tmp_path):
    path = write_session(tmp_path / "ok.csv", [
        "007; 1; 1; 1:34.000; 1; 1; 1; ; 0:01:34.000; 11:31:34.000; Ana A; Aston; HYPERCAR; GF; ;",
        "7; 1; 1; 1:33.000; 1; 1; 1; ; 0:01:33.000; 11:31:33.000; Carl C; Toyota; HYPERCAR; GF; ;",
    ])
    df, notices = separate_shared_numbers(import_data(path))
    assert sorted(df["NUMBER"]) == ["007", "7"] and notices == []


def test_duplicate_rows_of_the_same_car_are_an_error(tmp_path):
    row = "7; 1; 1; 1:33.000; 1; 1; 1; ; 0:01:33.000; 11:31:33.000; Carl C; Toyota; HYPERCAR; GF; ;"
    path = write_session(tmp_path / "dup.csv", [row, row])
    with pytest.raises(ValueError, match="vueltas repetidas"):
        separate_shared_numbers(import_data(path))