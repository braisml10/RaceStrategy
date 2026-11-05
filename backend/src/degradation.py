"""Degradación neta de ritmo por stint (tendencia del tiempo de vuelta)."""

from __future__ import annotations

import numpy as np
import pandas as pd

from stints import STINT_KEYS, mark_stints
from config import MIN_PACE_LAPS_FOR_DEGRADATION

_COLUMNS = [
    "NUMBER", "STINT", "CLASS", "DRIVER_NAME", "PACE_LAPS",
    "NET_SLOPE", "ADJUSTED_SLOPE", "INTERCEPT", "R2",
]


def stint_degradation(
    df: pd.DataFrame,
    min_laps: int = MIN_PACE_LAPS_FOR_DEGRADATION,
    fuel_effect_s_per_lap: float = 0.0,
) -> pd.DataFrame:
    """Ajuste lineal tiempo de vuelta ~ vuelta del stint, solo con vueltas de ritmo.

    NET_SLOPE (s/vuelta) es la pérdida neta de ritmo: positiva = el coche se
    vuelve más lento. Mezcla desgaste de neumáticos (empeora) y combustible
    consumido (mejora), además de tráfico y evolución de la pista; los datos
    no permiten separarlos.

    `fuel_effect_s_per_lap` es un SUPUESTO que aporta el usuario: segundos que
    gana el coche por vuelta al aligerarse. ADJUSTED_SLOPE = NET_SLOPE + ese
    valor, una aproximación a la degradación solo de neumáticos. Con 0 (por
    defecto) coincide con NET_SLOPE.

    Solo se devuelven stints con al menos `min_laps` vueltas de ritmo.
    R2 indica cuánto de la variación explica la tendencia lineal.
    """
    if min_laps < 2:
        raise ValueError("min_laps debe ser al menos 2 para ajustar una recta.")

    marked = mark_stints(df)
    pace = marked[marked["IS_PACE_LAP"]]

    rows = []
    for (number, stint), laps in pace.groupby(STINT_KEYS):
        if len(laps) < min_laps or laps["STINT_LAP"].nunique() < 2:
            continue
        x = laps["STINT_LAP"].to_numpy(dtype=float)
        y = laps["LAP_TIME_SECONDS"].to_numpy(dtype=float)
        slope, intercept = np.polyfit(x, y, 1)
        residual = ((y - (slope * x + intercept)) ** 2).sum()
        total = ((y - y.mean()) ** 2).sum()
        rows.append(
            {
                "NUMBER": number,
                "STINT": stint,
                "CLASS": laps["CLASS"].iloc[0],
                "DRIVER_NAME": laps["DRIVER_NAME"].iloc[0],
                "PACE_LAPS": len(laps),
                "NET_SLOPE": slope,
                "ADJUSTED_SLOPE": slope + fuel_effect_s_per_lap,
                "INTERCEPT": intercept,
                "R2": 1 - residual / total if total > 0 else np.nan,
            }
        )
    return pd.DataFrame(rows, columns=_COLUMNS)