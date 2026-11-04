"""Métricas de referencia: mejores tiempos, clasificaciones y ritmo por piloto."""

from __future__ import annotations

import pandas as pd

# Etiqueta -> columna en segundos
BEST_METRICS = {
    "Mejor vuelta": "LAP_TIME_SECONDS",
    "Mejor sector 1": "S1_SECONDS",
    "Mejor sector 2": "S2_SECONDS",
    "Mejor sector 3": "S3_SECONDS",
}
# Etiqueta -> clave corta (la usan la API y el frontend)
METRIC_KEYS = {
    "Mejor vuelta": "lap",
    "Mejor sector 1": "s1",
    "Mejor sector 2": "s2",
    "Mejor sector 3": "s3",
}
# Clave corta -> columna en segundos
METRIC_COLUMNS = {METRIC_KEYS[label]: column for label, column in BEST_METRICS.items()}


def best_by_driver(car_df: pd.DataFrame) -> pd.DataFrame:
    """Mejor vuelta y mejor sector (S1, S2, S3) de cada piloto del coche.

    Se usan todas las vueltas: un sector válido cuenta aunque la vuelta
    fuese de entrada a boxes. Pilotos en orden de aparición en pista.
    """
    car_df = car_df.sort_values("LAP_NUMBER")
    summary = car_df.groupby("DRIVER_NAME", sort=False).agg(
        LAPS=("LAP_NUMBER", "count"),
        BEST_LAP=("LAP_TIME_SECONDS", "min"),
        BEST_S1=("S1_SECONDS", "min"),
        BEST_S2=("S2_SECONDS", "min"),
        BEST_S3=("S3_SECONDS", "min"),
    )
    return summary.reset_index()


def driver_summary(car_df: pd.DataFrame) -> pd.DataFrame:
    """`best_by_driver` más el ritmo real (mediana y nº de vueltas de ritmo).

    `car_df` viene de `mark_pace_laps` y contiene un único coche.
    """
    best = best_by_driver(car_df)
    pace = (
        car_df[car_df["IS_PACE_LAP"]]
        .groupby("DRIVER_NAME")
        .agg(PACE_LAPS=("LAP_NUMBER", "count"), MEDIAN_PACE=("LAP_TIME_SECONDS", "median"))
    )
    summary = best.merge(pace, how="left", left_on="DRIVER_NAME", right_index=True)
    summary["PACE_LAPS"] = summary["PACE_LAPS"].fillna(0).astype(int)
    return summary


def session_bests(df: pd.DataFrame) -> pd.DataFrame:
    """Mejor vuelta y mejores parciales del conjunto de datos recibido (una
    categoría, normalmente), con coche, piloto, vuelta y hora (del día y de
    sesión) en que se lograron. La hora es la del final de esa vuelta."""
    rows = []
    for label, column in BEST_METRICS.items():
        best = df.loc[df[column].idxmin()]
        rows.append(
            {
                "KEY": METRIC_KEYS[label],
                "METRIC": label,
                "TIME": best[column],
                "CAR": best["NUMBER"],
                "TEAM": best["TEAM"] if "TEAM" in best else "",
                "DRIVER": best["DRIVER_NAME"],
                "LAP": int(best["LAP_NUMBER"]),
                "CLOCK": best["HOUR_SECONDS"],
                "ELAPSED": best["ELAPSED_SECONDS"],
            }
        )
    return pd.DataFrame(rows)


def ranking_by_metric(df: pd.DataFrame, column: str = "LAP_TIME_SECONDS") -> pd.DataFrame:
    """Clasificación de coches por su mejor tiempo en `column` (vuelta o sector).

    Una fila por coche, con el piloto, la vuelta y la hora en que lo logró y la
    diferencia (GAP) con el primero. Más rápido primero.
    """
    valid = df.dropna(subset=[column])
    best = valid.loc[valid.groupby("NUMBER")[column].idxmin()]
    ranking = pd.DataFrame(
        {
            "CAR": best["NUMBER"].to_numpy(),
            "TEAM": best["TEAM"].to_numpy() if "TEAM" in best else "",
            "DRIVER": best["DRIVER_NAME"].to_numpy(),
            "TIME": best[column].to_numpy(),
            "LAP": best["LAP_NUMBER"].astype(int).to_numpy(),
            "CLOCK": best["HOUR_SECONDS"].to_numpy(),
        }
    ).sort_values("TIME", kind="stable").reset_index(drop=True)
    ranking.insert(0, "POSITION", range(1, len(ranking) + 1))
    ranking["GAP"] = ranking["TIME"] - ranking["TIME"].iloc[0]
    return ranking


def pace_by_driver(marked: pd.DataFrame) -> pd.DataFrame:
    """Ritmo real (solo vueltas de ritmo) por piloto y coche.

    `marked` viene de `mark_pace_laps`. La mediana es la medida de ritmo
    más fiable; la desviación típica mide la consistencia.
    Ordenado por categoría y mediana (más rápido primero).
    """
    pace = marked[marked["IS_PACE_LAP"]]
    summary = pace.groupby(["CLASS", "NUMBER", "DRIVER_NAME"], sort=False).agg(
        PACE_LAPS=("LAP_NUMBER", "count"),
        BEST_PACE=("LAP_TIME_SECONDS", "min"),
        MEDIAN_PACE=("LAP_TIME_SECONDS", "median"),
        MEAN_PACE=("LAP_TIME_SECONDS", "mean"),
        PACE_STD=("LAP_TIME_SECONDS", "std"),
    )
    return summary.reset_index().sort_values(["CLASS", "MEDIAN_PACE"]).reset_index(drop=True)