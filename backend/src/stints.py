"""Stints: tramos de un coche entre paradas en boxes (y relevos de piloto)."""

from __future__ import annotations

import numpy as np
import pandas as pd

from laps import mark_pace_laps

STINT_KEYS = ["NUMBER", "STINT"]


def _pit_seconds(df: pd.DataFrame) -> pd.Series:
    if "PIT_TIME_SECONDS" in df.columns:
        return df["PIT_TIME_SECONDS"]
    return pd.Series(np.nan, index=df.index)


def mark_stints(df: pd.DataFrame) -> pd.DataFrame:
    """Añade STINT (1, 2, 3... por coche) y STINT_LAP (1 = vuelta de salida).

    Un stint nuevo empieza en la primera vuelta del coche, en cada vuelta de
    salida de boxes y cuando cambia el piloto. Si `df` no viene de
    `mark_pace_laps` se aplica automáticamente.
    """
    if "STINT" in df.columns:
        return df
    if "IS_OUT_LAP" not in df.columns:
        df = mark_pace_laps(df)

    df = df.sort_values(["NUMBER", "LAP_NUMBER"]).copy()
    previous_driver = df.groupby("NUMBER")["DRIVER_NAME"].shift(1)
    driver_change = (previous_driver.notna() & previous_driver.ne(df["DRIVER_NAME"])).fillna(False).astype(bool)
    first_lap = df.groupby("NUMBER").cumcount().eq(0)

    new_stint = first_lap | df["IS_OUT_LAP"] | driver_change
    df["STINT"] = new_stint.astype(int).groupby(df["NUMBER"]).cumsum()
    df["STINT_LAP"] = df.groupby(STINT_KEYS).cumcount() + 1
    return df


def stint_summary(df: pd.DataFrame) -> pd.DataFrame:
    """Una fila por stint de cada coche.

    DURATION_SECONDS = suma de tiempos de vuelta menos el tiempo en boxes de
    la vuelta de salida (tiempo realmente en pista).
    PIT_BEFORE_SECONDS = tiempo en boxes de la parada que precede al stint
    (en el primer stint, la espera inicial en boxes si la hay).
    """
    marked = mark_stints(df).copy()
    marked["_PIT"] = _pit_seconds(marked)
    marked["_PACE"] = marked["LAP_TIME_SECONDS"].where(marked["IS_PACE_LAP"])

    grouped = marked.groupby(STINT_KEYS)
    summary = grouped.agg(
        START_LAP=("LAP_NUMBER", "min"),
        END_LAP=("LAP_NUMBER", "max"),
        LAPS=("LAP_NUMBER", "count"),
        PACE_LAPS=("IS_PACE_LAP", "sum"),
        TOTAL_TIME=("LAP_TIME_SECONDS", "sum"),
        BEST_LAP=("LAP_TIME_SECONDS", "min"),
        AVG_PACE=("_PACE", "mean"),
        MEDIAN_PACE=("_PACE", "median"),
        PACE_STD=("_PACE", "std"),
    )
    # head/tail devuelven filas completas (first() saltaría los NaN de _PIT).
    firsts = grouped.head(1).set_index(STINT_KEYS)
    lasts = grouped.tail(1).set_index(STINT_KEYS)

    summary["CLASS"] = firsts["CLASS"]
    summary["DRIVER_NAME"] = firsts["DRIVER_NAME"]
    summary["PIT_BEFORE_SECONDS"] = firsts["_PIT"]
    summary["START_ELAPSED_SECONDS"] = firsts["ELAPSED_SECONDS"] - firsts["LAP_TIME_SECONDS"]
    summary["END_ELAPSED_SECONDS"] = lasts["ELAPSED_SECONDS"]
    summary["DURATION_SECONDS"] = summary["TOTAL_TIME"] - firsts["_PIT"].fillna(0)

    columns = [
        "CLASS", "DRIVER_NAME", "START_LAP", "END_LAP", "LAPS", "PACE_LAPS",
        "START_ELAPSED_SECONDS", "END_ELAPSED_SECONDS", "DURATION_SECONDS",
        "PIT_BEFORE_SECONDS", "BEST_LAP", "AVG_PACE", "MEDIAN_PACE", "PACE_STD",
    ]
    return summary[columns].reset_index()