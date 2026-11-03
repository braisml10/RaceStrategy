"""Todo lo relativo a las vueltas: formato, selección, clasificación y series."""

from __future__ import annotations

import numpy as np
import pandas as pd

from config import (
    CATEGORY_ORDER, MS_SEPARATOR, NEUTRALISED_FLAGS, PACE_STATUS, SLOW_LAP_THRESHOLD,
)


# ---------------------------------------------------------------------------
# Formato (solo para mostrar, nunca para calcular)
# ---------------------------------------------------------------------------
def format_lap_time(seconds) -> str:
    """92.84 -> '01:32.840'. Formato mm:ss.ddd para vueltas y sectores."""
    if seconds is None or pd.isna(seconds):
        return "–"
    total_ms = int(round(float(seconds) * 1000))
    minutes, rest = divmod(total_ms, 60_000)
    secs = f"{rest / 1000:06.3f}".replace(".", MS_SEPARATOR)
    return f"{minutes:02d}:{secs}"


def format_hms(seconds) -> str:
    """41483.2 -> '11:31:23'. Sirve para hora del día y tiempo de sesión."""
    if seconds is None or pd.isna(seconds):
        return "–"
    hours, rest = divmod(int(seconds), 3600)
    minutes, secs = divmod(rest, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}"


# ---------------------------------------------------------------------------
# Selección
# ---------------------------------------------------------------------------
def list_categories(df: pd.DataFrame) -> list[str]:
    """Categorías presentes, en orden habitual (Hypercar, LMP2, LMGT3...)."""
    present = df["CLASS"].dropna().unique().tolist()
    return sorted(
        present,
        key=lambda c: (CATEGORY_ORDER.index(c) if c in CATEGORY_ORDER else len(CATEGORY_ORDER), c),
    )


def _car_sort_key(number: str) -> tuple[int, str]:
    return (int(number) if str(number).isdigit() else 10**6, str(number))


def list_cars(df: pd.DataFrame, category: str | None = None) -> pd.DataFrame:
    """Coches (de una categoría, o de todas): NUMBER, TEAM, MANUFACTURER, DRIVERS.

    DRIVERS es la lista de pilotos en orden de aparición en pista.
    """
    if category is not None:
        df = df[df["CLASS"] == category]
    df = df.sort_values("LAP_NUMBER")

    rows = []
    for number, car in df.groupby("NUMBER", sort=False):
        rows.append(
            {
                "NUMBER": number,
                "TEAM": car["TEAM"].iloc[0] if "TEAM" in car else "",
                "MANUFACTURER": car["MANUFACTURER"].iloc[0] if "MANUFACTURER" in car else "",
                "DRIVERS": car["DRIVER_NAME"].drop_duplicates().tolist(),
            }
        )
    cars = pd.DataFrame(rows, columns=["NUMBER", "TEAM", "MANUFACTURER", "DRIVERS"])
    order = sorted(range(len(cars)), key=lambda i: _car_sort_key(cars["NUMBER"].iloc[i]))
    return cars.iloc[order].reset_index(drop=True)


# ---------------------------------------------------------------------------
# Clasificación de vueltas
# ---------------------------------------------------------------------------
def _text_column(df: pd.DataFrame, name: str) -> pd.Series:
    """Columna como texto; si no existe (p. ej. se eliminó por vacía), todo NA."""
    if name in df.columns:
        return df[name].astype("string")
    return pd.Series(pd.NA, index=df.index, dtype="string")


def mark_pace_laps(
    df: pd.DataFrame, slow_threshold: float = SLOW_LAP_THRESHOLD
) -> pd.DataFrame:
    """Añade IS_IN_LAP, IS_OUT_LAP, LAP_STATUS e IS_PACE_LAP.

    Una vuelta NO es de ritmo si es:
      - entrada a boxes (marcada con 'B'),
      - salida de boxes (la siguiente a una entrada, la que lleva PIT_TIME,
        o la primera vuelta del coche),
      - con bandera FCY/SC/RF al cruzar la meta,
      - más lenta que `slow_threshold` x la mejor vuelta del coche
        (atrapa zonas lentas, tráfico extremo, errores...).
    Si se cumplen varias, LAP_STATUS recoge la primera de esa lista.
    """
    df = df.sort_values(["NUMBER", "LAP_NUMBER"]).copy()
    car = df["NUMBER"]

    in_lap = _text_column(df, "CROSSING_FINISH_LINE_IN_PIT").eq("B").fillna(False).astype(bool)
    has_pit_time = _text_column(df, "PIT_TIME").notna()
    first_lap = df["LAP_NUMBER"].eq(df.groupby("NUMBER")["LAP_NUMBER"].transform("min"))
    after_in_lap = in_lap.groupby(car).shift(1, fill_value=False).astype(bool)
    out_lap = after_in_lap | has_pit_time | first_lap
    neutralised = _text_column(df, "FLAG_AT_FL").isin(NEUTRALISED_FLAGS).astype(bool)

    best_of_car = df.groupby("NUMBER")["LAP_TIME_SECONDS"].transform("min")
    slow = df["LAP_TIME_SECONDS"] > slow_threshold * best_of_car

    pct = round(slow_threshold * 100)
    df["IS_IN_LAP"] = in_lap
    df["IS_OUT_LAP"] = out_lap
    df["LAP_STATUS"] = np.select(
        [in_lap, out_lap, neutralised, slow],
        ["Entrada a boxes", "Salida de boxes", "Bandera FCY", f"Lenta (>{pct} % de la mejor)"],
        default=PACE_STATUS,
    )
    df["IS_PACE_LAP"] = df["LAP_STATUS"].eq(PACE_STATUS)
    return df


# ---------------------------------------------------------------------------
# Serie lista para pintar
# ---------------------------------------------------------------------------
def lap_series(car_df: pd.DataFrame, pace_only: bool = False) -> pd.DataFrame:
    """Una fila por vuelta de un coche, con los textos ya formateados.

    Sirve para las dos gráficas (evolución del coche y comparativa de pilotos:
    basta filtrar o agrupar por DRIVER_NAME) y para su tabla alternativa.
    `car_df` debe venir de `mark_pace_laps` y contener un único coche.
    """
    laps = car_df.sort_values("LAP_NUMBER")
    if pace_only:
        laps = laps[laps["IS_PACE_LAP"]]

    return pd.DataFrame(
        {
            "LAP_NUMBER": laps["LAP_NUMBER"].astype(int),
            "DRIVER_NAME": laps["DRIVER_NAME"],
            "LAP_TIME_SECONDS": laps["LAP_TIME_SECONDS"],
            "LAP_TIME_TEXT": laps["LAP_TIME_SECONDS"].map(format_lap_time),
            "S1_TEXT": laps["S1_SECONDS"].map(format_lap_time),
            "S2_TEXT": laps["S2_SECONDS"].map(format_lap_time),
            "S3_TEXT": laps["S3_SECONDS"].map(format_lap_time),
            "CLOCK_TEXT": laps["HOUR_SECONDS"].map(format_hms),
            "LAP_STATUS": laps["LAP_STATUS"],
            "IS_PACE_LAP": laps["IS_PACE_LAP"],
        }
    ).reset_index(drop=True)