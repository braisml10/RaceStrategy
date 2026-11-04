"""API HTTP (FastAPI) que expone el backend al frontend.

Arranque (desde la carpeta src):
    uvicorn api:app --reload --port 8000
Documentación interactiva: http://localhost:8000/docs

Los tiempos viajan dos veces: en segundos (para dibujar) y ya formateados en
texto mm:ss.ddd (para mostrar), de modo que el formato vive solo en Python.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from config import (
    CATEGORY_LABELS, CORS_ORIGINS, DATA_DIR, MS_SEPARATOR, SLOW_LAP_THRESHOLD,
)
from importer import SUPPORTED_EXTENSIONS, import_data
from laps import (
    format_gap, format_hms, format_lap_time, lap_series, list_cars, list_categories,
    mark_pace_laps,
)
from metrics import (
    METRIC_COLUMNS, driver_summary, ranking_by_metric, session_bests,
)

REQUIRED_COLUMNS = [
    "NUMBER", "LAP_NUMBER", "LAP_TIME", "S1", "S2", "S3",
    "DRIVER_NAME", "CLASS", "TEAM", "HOUR", "ELAPSED",
]
DEFAULT_SLOW_PCT = round(SLOW_LAP_THRESHOLD * 100)
TOP_CARS = 4

app = FastAPI(title="WEC Strategy API")
app.add_middleware(
    CORSMiddleware, allow_origins=CORS_ORIGINS, allow_methods=["GET"], allow_headers=["*"]
)


# ---------------------------------------------------------------------------
# Carga (con caché: importar un CSV cuesta, consultarlo no)
# ---------------------------------------------------------------------------
def _session_files() -> dict[str, Path]:
    if not DATA_DIR.is_dir():
        return {}
    return {
        p.name: p for p in sorted(DATA_DIR.iterdir()) if p.suffix.lower() in SUPPORTED_EXTENSIONS
    }


@lru_cache(maxsize=8)
def _load(path: str, modified: float) -> pd.DataFrame:
    """`modified` solo invalida la caché cuando el archivo cambia."""
    return import_data(path, required_columns=REQUIRED_COLUMNS)


@lru_cache(maxsize=32)
def _marked(path: str, modified: float, slow_pct: int) -> pd.DataFrame:
    return mark_pace_laps(_load(path, modified), slow_pct / 100)


def _session_data(session: str, slow_pct: int = DEFAULT_SLOW_PCT) -> pd.DataFrame:
    # El nombre se busca entre los archivos de la carpeta: no se puede salir de ella.
    path = _session_files().get(session)
    if path is None:
        raise HTTPException(404, f"No existe la sesión «{session}».")
    try:
        return _marked(str(path), path.stat().st_mtime, slow_pct)
    except Exception as error:  # mensaje legible para la interfaz
        raise HTTPException(422, f"No se pudo importar {session}: {error}") from error


# ---------------------------------------------------------------------------
# Serialización
# ---------------------------------------------------------------------------
def _num(value) -> float | None:
    return None if value is None or pd.isna(value) else float(value)


def _text(value) -> str:
    return "" if value is None or pd.isna(value) else str(value)


def _time(seconds) -> dict:
    return {"seconds": _num(seconds), "text": format_lap_time(seconds)}


def _best(row) -> dict:
    return {
        "key": row.KEY,
        "label": row.METRIC,
        **_time(row.TIME),
        "car": row.CAR,
        "team": _text(row.TEAM),
        "driver": row.DRIVER,
        "lap": int(row.LAP),
        "clock": format_hms(row.CLOCK),
        "elapsed": format_hms(row.ELAPSED),
    }


def _ranking(ranking: pd.DataFrame) -> list[dict]:
    return [
        {
            "position": int(r.POSITION),
            "car": r.CAR,
            "team": _text(r.TEAM),
            "driver": r.DRIVER,
            **_time(r.TIME),
            "gapText": "—" if r.POSITION == 1 else format_gap(r.GAP),
            "lap": int(r.LAP),
            "clock": format_hms(r.CLOCK),
        }
        for r in ranking.itertuples()
    ]


def _pace_points(df: pd.DataFrame, car: str) -> list[dict]:
    laps = df[(df["NUMBER"] == car) & df["IS_PACE_LAP"]].sort_values("LAP_NUMBER")
    return [
        {"lap": int(r.LAP_NUMBER), "seconds": _num(r.LAP_TIME_SECONDS), "driver": r.DRIVER_NAME}
        for r in laps.itertuples()
    ]


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@app.get("/api/sessions")
def sessions() -> dict:
    """Sesiones disponibles y ajustes que necesita el frontend."""
    return {
        "sessions": [{"id": name, "name": Path(name).stem} for name in _session_files()],
        "settings": {"msSeparator": MS_SEPARATOR, "slowThresholdPct": DEFAULT_SLOW_PCT},
        "dataDir": str(DATA_DIR),
    }


@app.get("/api/sessions/{session}/overview")
def overview(session: str) -> dict:
    """Resumen de la sesión y de cada categoría (pantalla de inicio)."""
    df = _session_data(session)
    categories = []
    for category in list_categories(df):
        data = df[df["CLASS"] == category]
        categories.append(
            {
                "id": category,
                "label": CATEGORY_LABELS.get(category, category),
                "cars": int(data["NUMBER"].nunique()),
                "drivers": int(data["DRIVER_NAME"].nunique()),
                "laps": len(data),
                "bestLap": _best(next(session_bests(data).itertuples())),
            }
        )
    return {
        "session": {"id": session, "name": Path(session).stem},
        "laps": len(df),
        "cars": int(df["NUMBER"].nunique()),
        "drivers": int(df["DRIVER_NAME"].nunique()),
        "clockStart": format_hms(df["HOUR_SECONDS"].min()),
        "clockEnd": format_hms(df["HOUR_SECONDS"].max()),
        "categories": categories,
    }


@app.get("/api/sessions/{session}/categories/{category}")
def category_view(
    session: str, category: str, slow: int = Query(DEFAULT_SLOW_PCT, ge=100, le=200)
) -> dict:
    """Todo lo que muestra el panel de una categoría: mejores tiempos, clasificación
    por vuelta y sector, ritmo de los coches más rápidos y lista de coches."""
    df = _session_data(session, slow)
    data = df[df["CLASS"] == category]
    if data.empty:
        raise HTTPException(404, f"No existe la categoría «{category}» en esta sesión.")

    rankings = {key: ranking_by_metric(data, column) for key, column in METRIC_COLUMNS.items()}
    top = rankings["lap"].head(TOP_CARS)
    cars = list_cars(df, category)

    return {
        "category": {"id": category, "label": CATEGORY_LABELS.get(category, category)},
        "counts": {
            "laps": len(data),
            "paceLaps": int(data["IS_PACE_LAP"].sum()),
            "cars": int(data["NUMBER"].nunique()),
            "drivers": int(data["DRIVER_NAME"].nunique()),
        },
        "bests": [_best(row) for row in session_bests(data).itertuples()],
        "rankings": {key: _ranking(ranking) for key, ranking in rankings.items()},
        "topCars": [
            {"car": r.CAR, "team": _text(r.TEAM), "laps": _pace_points(data, r.CAR)}
            for r in top.itertuples()
        ],
        "cars": [
            {
                "number": r.NUMBER,
                "team": _text(r.TEAM),
                "manufacturer": _text(r.MANUFACTURER),
                "drivers": list(r.DRIVERS),
            }
            for r in cars.itertuples()
        ],
    }


@app.get("/api/sessions/{session}/cars/{number}")
def car_view(
    session: str, number: str, slow: int = Query(DEFAULT_SLOW_PCT, ge=100, le=200)
) -> dict:
    """Un coche: KPIs por piloto y todas sus vueltas (con su estado)."""
    df = _session_data(session, slow)
    car = df[df["NUMBER"] == number]
    if car.empty:
        raise HTTPException(404, f"No existe el coche «{number}» en esta sesión.")

    drivers = driver_summary(car)
    fastest = drivers["BEST_LAP"].min()
    series = lap_series(car)

    return {
        "car": {
            "number": number,
            "team": _text(car["TEAM"].iloc[0]),
            "manufacturer": _text(car["MANUFACTURER"].iloc[0]) if "MANUFACTURER" in car else "",
            "category": car["CLASS"].iloc[0],
        },
        "counts": {"laps": len(car), "paceLaps": int(car["IS_PACE_LAP"].sum())},
        "drivers": [
            {
                "name": r.DRIVER_NAME,
                "laps": int(r.LAPS),
                "paceLaps": int(r.PACE_LAPS),
                "best": _time(r.BEST_LAP),
                "s1": _time(r.BEST_S1),
                "s2": _time(r.BEST_S2),
                "s3": _time(r.BEST_S3),
                "median": _time(r.MEDIAN_PACE),
                "deltaText": (
                    "Referencia"
                    if r.BEST_LAP == fastest
                    else f"{format_gap(r.BEST_LAP - fastest)} s"
                ),
            }
            for r in drivers.itertuples()
        ],
        "laps": [
            {
                "lap": int(r.LAP_NUMBER),
                "driver": r.DRIVER_NAME,
                **_time(r.LAP_TIME_SECONDS),
                "s1": r.S1_TEXT,
                "s2": r.S2_TEXT,
                "s3": r.S3_TEXT,
                "clock": r.CLOCK_TEXT,
                "status": r.LAP_STATUS,
                "isPace": bool(r.IS_PACE_LAP),
            }
            for r in series.itertuples()
        ],
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("api:app", host="127.0.0.1", port=8000)