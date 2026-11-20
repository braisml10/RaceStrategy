"""API HTTP (FastAPI) que expone el backend al frontend.

Arranque (desde la carpeta src):
    uvicorn api:app --reload --port 8000
Documentación interactiva: http://localhost:8000/docs

Los tiempos viajan dos veces: en segundos (para dibujar) y ya formateados en
texto mm:ss.ddd (para mostrar), de modo que el formato vive solo en Python.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path, PurePosixPath

import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from config import (
    CATEGORY_LABELS, CORS_ORIGINS, DATA_DIR, MS_SEPARATOR, SLOW_LAP_THRESHOLD,
)
from degradation import stint_degradation
from importer import SUPPORTED_EXTENSIONS, import_data, read_categories, separate_shared_numbers
from laps import (
    format_gap, format_hms, format_lap_time, lap_series, list_cars, list_categories,
    mark_pace_laps,
)
from metrics import (
    METRIC_COLUMNS, driver_summary, ranking_by_metric, session_bests,
)
from stints import mark_stints, stint_summary

REQUIRED_COLUMNS = [
    "NUMBER", "LAP_NUMBER", "LAP_TIME", "S1", "S2", "S3",
    "DRIVER_NAME", "CLASS", "TEAM", "HOUR", "ELAPSED",
]
DEFAULT_SLOW_PCT = round(SLOW_LAP_THRESHOLD * 100)

# Sesión virtual que junta todas las sesiones de la carpeta (p. ej. FP1 + FP2 + FP3).
OVERALL_ID = "__all__"
OVERALL_NAME = "Todas las sesiones"
TREND_MIN_LAPS = 3  # vueltas de ritmo mínimas para dibujar la tendencia de un stint

app = FastAPI(title="WEC Strategy API")
app.add_middleware(
    CORSMiddleware, allow_origins=CORS_ORIGINS, allow_methods=["GET"], allow_headers=["*"]
)


# ---------------------------------------------------------------------------
# Carga (con caché: importar un CSV cuesta, consultarlo no)
# ---------------------------------------------------------------------------
def _session_files() -> dict[str, Path]:
    """Todas las sesiones de todas las carpetas. El id es la ruta relativa a DATA_DIR
    (con "/"), p. ej. "WEC/2026/Barcelona/FP1.CSV". Se ignoran los temporales de Excel
    ("~$archivo.xlsx", que existen mientras el archivo está abierto) y los ocultos."""
    if not DATA_DIR.is_dir():
        return {}
    found = sorted(
        p for p in DATA_DIR.rglob("*")
        if p.is_file()
        and p.suffix.lower() in SUPPORTED_EXTENSIONS
        and not p.name.startswith(("~$", "."))
    )
    return {p.relative_to(DATA_DIR).as_posix(): p for p in found}


def _event_of(session_id: str) -> str:
    """Carpeta (evento) de una sesión; "." si el archivo está en la raíz."""
    return PurePosixPath(session_id).parent.as_posix()


def _event_name(event: str) -> str:
    """'ALMS/paul-ricard' -> 'ALMS · Paul Ricard'."""
    if event == ".":
        return DATA_DIR.name
    def pretty(part: str) -> str:
        text = part.replace("-", " ").replace("_", " ")
        return text.title() if text.islower() else text
    return " · ".join(pretty(part) for part in event.split("/"))


def _overall_id(event: str) -> str:
    return OVERALL_ID if event == "." else f"{event}/{OVERALL_ID}"


def _overall_event(session: str) -> str | None:
    """Evento al que pertenece una sesión 'todas las sesiones'; None si es una sesión normal."""
    if session == OVERALL_ID:
        return "."
    if session.endswith("/" + OVERALL_ID):
        return session[: -len(OVERALL_ID) - 1]
    return None


def _event_files(event: str) -> list[Path]:
    return [p for sid, p in _session_files().items() if _event_of(sid) == event]


@lru_cache(maxsize=8)
def _load(path: str, modified: float) -> tuple[pd.DataFrame, list[str]]:
    """Datos de la sesión y avisos para el usuario. `modified` solo invalida la
    caché cuando el archivo cambia."""
    df = import_data(path, required_columns=REQUIRED_COLUMNS)
    return separate_shared_numbers(df)


@lru_cache(maxsize=32)
def _marked(path: str, modified: float, slow_pct: int) -> pd.DataFrame:
    df = mark_pace_laps(_load(path, modified)[0], slow_pct / 100)
    df["SESSION"] = Path(path).stem
    df["SESSION_LAP"] = df["LAP_NUMBER"]
    return df


@lru_cache(maxsize=8)
def _overall(signature: tuple[tuple[str, float], ...], slow_pct: int) -> pd.DataFrame:
    """Todas las sesiones juntas. Cada sesión se clasifica por separado (la vuelta
    lenta se mide contra la mejor del coche en ESA sesión). Como cada sesión
    empieza en la vuelta 1, LAP_NUMBER pasa a ser la vuelta acumulada del coche
    (FP1, luego FP2...) y SESSION_LAP conserva la vuelta dentro de su sesión."""
    frames = []
    for path, modified in signature:
        try:
            frames.append(_marked(path, modified, slow_pct))
        except Exception as error:
            raise ValueError(f"{Path(path).name}: {error}") from error
    df = pd.concat(frames, ignore_index=True)
    order = {name: i for i, name in enumerate(dict.fromkeys(df["SESSION"]))}
    df["_ORDER"] = df["SESSION"].map(order)
    df = df.sort_values(["NUMBER", "_ORDER", "SESSION_LAP"]).reset_index(drop=True)
    df["LAP_NUMBER"] = df.groupby("NUMBER").cumcount() + 1
    return df.drop(columns="_ORDER")


def _session_data(session: str, slow_pct: int = DEFAULT_SLOW_PCT) -> pd.DataFrame:
    event = _overall_event(session)
    if event is not None:
        files = _event_files(event)
        if len(files) < 2:
            raise HTTPException(404, "Para ver todas las sesiones hace falta más de un archivo.")
        signature = tuple((str(p), p.stat().st_mtime) for p in files)
        try:
            return _overall(signature, slow_pct)
        except Exception as error:
            raise HTTPException(422, f"No se pudieron juntar las sesiones: {error}") from error
    # El nombre se busca entre los archivos de la carpeta: no se puede salir de ella.
    path = _session_files().get(session)
    if path is None:
        raise HTTPException(404, f"No existe la sesión «{session}».")
    try:
        return _marked(str(path), path.stat().st_mtime, slow_pct)
    except Exception as error:  # mensaje legible para la interfaz
        raise HTTPException(422, f"No se pudo importar {session}: {error}") from error


@lru_cache(maxsize=64)
def _categories(path: str, modified: float) -> tuple[str, ...] | None:
    """Categorías de un archivo (solo lee la columna CLASS). None si no se sabe."""
    found = read_categories(path)
    return None if found is None else tuple(found)


def _session_categories(path: Path) -> list[str] | None:
    found = _categories(str(path), path.stat().st_mtime)
    if found is None:
        return None
    return list_categories(pd.DataFrame({"CLASS": list(found)}))


def _session_notices(session: str) -> list[str]:
    event = _overall_event(session)
    paths = _event_files(event) if event is not None else [_session_files()[session]]
    return [n for p in paths for n in _load(str(p), p.stat().st_mtime)[1]]


# ---------------------------------------------------------------------------
# Serialización
# ---------------------------------------------------------------------------
def _num(value) -> float | None:
    return None if value is None or pd.isna(value) else float(value)


def _text(value) -> str:
    return "" if value is None or pd.isna(value) else str(value)


def _time(seconds) -> dict:
    return {"seconds": _num(seconds), "text": format_lap_time(seconds)}


def _median_gap_text(gap) -> str:
    if gap is None or pd.isna(gap):
        return "Sin vueltas de ritmo"
    return "Referencia" if gap == 0 else f"{format_gap(gap)} s"


def _best(row) -> dict:
    return {
        "key": row.KEY,
        "label": row.METRIC,
        **_time(row.TIME),
        "car": row.CAR,
        "team": _text(row.TEAM),
        "session": _text(row.SESSION),
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
            "session": _text(r.SESSION),
            **_time(r.TIME),
            "gapText": "—" if r.POSITION == 1 else format_gap(r.GAP),
            "lap": int(r.LAP),
            "clock": format_hms(r.CLOCK),
        }
        for r in ranking.itertuples()
    ]


def _stints(car: pd.DataFrame) -> list[dict]:
    """Stints del coche con su tendencia de ritmo (None si hay pocas vueltas)."""
    trends = stint_degradation(car, min_laps=TREND_MIN_LAPS).set_index("STINT")
    stints = []
    for r in stint_summary(car).itertuples():
        trend = None
        if r.STINT in trends.index:
            fit = trends.loc[r.STINT]
            trend = {
                "slope": float(fit["NET_SLOPE"]),
                "intercept": float(fit["INTERCEPT"]),
                "r2": _num(fit["R2"]),
            }
        stints.append(
            {
                "stint": int(r.STINT),
                "driver": r.DRIVER_NAME,
                "startLap": int(r.START_LAP),
                "endLap": int(r.END_LAP),
                "laps": int(r.LAPS),
                "paceLaps": int(r.PACE_LAPS),
                "best": _time(r.BEST_LAP),
                "median": _time(r.MEDIAN_PACE),
                "trend": trend,
            }
        )
    return stints


def _pit_stops(car: pd.DataFrame) -> list[dict]:
    """Paradas en boxes del coche: el paso de un stint al siguiente.

    Sale el piloto del stint que termina y entra el del que empieza (si es el mismo,
    no hay relevo). La duración es el tiempo en boxes de la vuelta de salida. Ni la
    espera inicial del primer stint ni el cambio de una sesión a otra en "todas las
    sesiones" cuentan como parada.
    """
    stints = stint_summary(car).sort_values("STINT")
    session_of = car.set_index("LAP_NUMBER")["SESSION"]
    stops: list[dict] = []
    previous = None
    for r in stints.itertuples():
        if previous is not None and session_of[previous.END_LAP] == session_of[r.START_LAP]:
            stops.append(
                {
                    "fromLap": int(previous.END_LAP),   # vuelta de entrada a boxes
                    "toLap": int(r.START_LAP),          # vuelta de salida
                    "driverOut": previous.DRIVER_NAME,
                    "driverIn": r.DRIVER_NAME,
                    "driverChange": bool(previous.DRIVER_NAME != r.DRIVER_NAME),
                    "pit": _time(r.PIT_BEFORE_SECONDS),
                }
            )
        previous = r
    return stops


def _pit_group(stops: list[dict]) -> dict:
    """Nº de paradas con tiempo, media, mejor y peor. Las paradas sin tiempo registrado
    no entran en la media."""
    times = [s["pit"]["seconds"] for s in stops if s["pit"]["seconds"] is not None]
    if not times:
        return {"count": 0, "mean": _time(None), "best": _time(None), "worst": _time(None)}
    return {
        "count": len(times),
        "mean": _time(sum(times) / len(times)),
        "best": _time(min(times)),
        "worst": _time(max(times)),
    }


def _pit_summary(stops: list[dict]) -> dict:
    """Tiempo de parada con cambio de piloto y sin él."""
    return {
        "withChange": _pit_group([s for s in stops if s["driverChange"]]),
        "withoutChange": _pit_group([s for s in stops if not s["driverChange"]]),
    }


def _pace_points(df: pd.DataFrame, car: str) -> list[dict]:
    laps = df[(df["NUMBER"] == car) & df["IS_PACE_LAP"]].sort_values("LAP_NUMBER")
    return [
        {
            "lap": int(r.LAP_NUMBER),
            "seconds": _num(r.LAP_TIME_SECONDS),
            "driver": r.DRIVER_NAME,
            "session": r.SESSION,
            "sessionLap": int(r.SESSION_LAP),
        }
        for r in laps.itertuples()
    ]


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@app.get("/api/sessions")
def sessions() -> dict:
    """Sesiones disponibles y ajustes que necesita el frontend."""
    by_event: dict[str, list[dict]] = {}
    for name, path in _session_files().items():
        event = _event_of(name)
        by_event.setdefault(event, []).append(
            {
                "id": name,
                "name": Path(name).stem,
                "overall": False,
                "event": event,
                "eventName": _event_name(event),
                "categories": _session_categories(path),
            }
        )
    items: list[dict] = []
    for event, group in by_event.items():
        items.extend(group)
        if len(group) >= 2:  # la sesión que junta las de ese evento, al final de su grupo
            known = [item["categories"] for item in group]
            union = None
            if all(c is not None for c in known):
                union = list_categories(pd.DataFrame({"CLASS": sorted({c for cs in known for c in cs})}))
            items.append(
                {
                    "id": _overall_id(event), "name": OVERALL_NAME, "overall": True,
                    "event": event, "eventName": _event_name(event), "categories": union,
                }
            )
    return {
        "sessions": items,
        "settings": {"msSeparator": MS_SEPARATOR, "slowThresholdPct": DEFAULT_SLOW_PCT},
        "dataDir": str(DATA_DIR),
    }


@app.get("/api/sessions/{session:path}/overview")
def overview(session: str) -> dict:
    """Resumen de la sesión y de cada categoría (pantalla de inicio)."""
    df = _session_data(session)
    overall = _overall_event(session) is not None
    event = _overall_event(session) if overall else _event_of(session)
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
        "session": {
            "id": session,
            "name": OVERALL_NAME if overall else Path(session).stem,
            "event": event,
            "eventName": _event_name(event),
        },
        "overall": overall,
        "sessionCount": int(df["SESSION"].nunique()),
        "notices": _session_notices(session),
        "laps": len(df),
        "cars": int(df["NUMBER"].nunique()),
        "drivers": int(df["DRIVER_NAME"].nunique()),
        # la hora del día solo tiene sentido dentro de una sesión
        "clockStart": "" if overall else format_hms(df["HOUR_SECONDS"].min()),
        "clockEnd": "" if overall else format_hms(df["HOUR_SECONDS"].max()),
        "categories": categories,
    }


@app.get("/api/sessions/{session:path}/categories/{category}")
def category_view(
    session: str, category: str, slow: int = Query(DEFAULT_SLOW_PCT, ge=100, le=200)
) -> dict:
    """Todo lo que muestra el panel de una categoría: mejores tiempos, clasificación
    por vuelta y sector, ritmo por vuelta de cada coche (del más rápido al más lento) y lista de coches."""
    df = _session_data(session, slow)
    data = df[df["CLASS"] == category]
    if data.empty:
        raise HTTPException(404, f"No existe la categoría «{category}» en esta sesión.")

    rankings = {key: ranking_by_metric(data, column) for key, column in METRIC_COLUMNS.items()}
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
        "pace": [
            {"car": r.CAR, "team": _text(r.TEAM), "laps": _pace_points(data, r.CAR)}
            for r in rankings["lap"].itertuples()
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


@app.get("/api/sessions/{session:path}/cars/{number}")
def car_view(
    session: str, number: str, slow: int = Query(DEFAULT_SLOW_PCT, ge=100, le=200)
) -> dict:
    """Un coche: KPIs por piloto, paradas en boxes y todas sus vueltas (con su estado)."""
    df = _session_data(session, slow)
    car = df[df["NUMBER"] == number]
    if car.empty:
        raise HTTPException(404, f"No existe el coche «{number}» en esta sesión.")
    car = mark_stints(car)

    drivers = driver_summary(car)
    fastest = drivers["BEST_LAP"].min()
    series = lap_series(car)
    stops = _pit_stops(car)

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
                "mean": _time(r.MEAN_PACE),
                "meanGap": {"seconds": _num(r.MEAN_GAP), "text": _median_gap_text(r.MEAN_GAP)},
                "medianGap": {"seconds": _num(r.MEDIAN_GAP), "text": _median_gap_text(r.MEDIAN_GAP)},
                "deltaText": (
                    "Referencia"
                    if r.BEST_LAP == fastest
                    else f"{format_gap(r.BEST_LAP - fastest)} s"
                ),
            }
            for r in drivers.itertuples()
        ],
        "stints": _stints(car),
        "pitStops": stops,
        "pitSummary": _pit_summary(stops),
        "laps": [
            {
                "lap": int(r.LAP_NUMBER),
                "stint": int(r.STINT),
                "stintLap": int(r.STINT_LAP),
                "session": r.SESSION,
                "sessionLap": int(r.SESSION_LAP),
                "driver": r.DRIVER_NAME,
                **_time(r.LAP_TIME_SECONDS),
                "s1": r.S1_TEXT,
                "s2": r.S2_TEXT,
                "s3": r.S3_TEXT,
                "clock": r.CLOCK_TEXT,
                "status": r.LAP_STATUS,
                "flag": r.FLAG,
                "pit": "in" if r.IS_IN_LAP else "out" if r.IS_OUT_LAP else "",
                "isPace": bool(r.IS_PACE_LAP),
            }
            for r in series.itertuples()
        ],
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("api:app", host="127.0.0.1", port=8000)