"""Punto de entrada: importa archivos de tiempos y muestra las métricas.

    python src/main.py                           # todos los archivos de DATA_DIR
    python src/main.py archivo.CSV               # un archivo concreto
    python src/main.py archivo.CSV --category HYPERCAR --car 007
"""

import argparse
from pathlib import Path

import pandas as pd

from config import DATA_DIR
from importer import SUPPORTED_EXTENSIONS, import_data
from laps import format_hms, format_lap_time, list_cars, list_categories, mark_pace_laps
from metrics import best_by_driver, pace_by_driver, session_bests


def with_times(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    """Copia con las columnas indicadas (segundos) formateadas como mm:ss.ddd."""
    df = df.copy()
    for column in columns:
        df[column] = df[column].map(format_lap_time)
    return df


def report(path: Path, category: str | None, car: str | None) -> None:
    print(f"\n######## {path.stem} ########")
    df = mark_pace_laps(import_data(path))
    print(f"{len(df)} vueltas · {df['NUMBER'].nunique()} coches")

    for cat in [category] if category else list_categories(df):
        data = df[df["CLASS"] == cat]
        print(f"\n===== {cat}: {len(list_cars(df, cat))} coches =====")
        bests = session_bests(data)
        bests["TIME"] = bests["TIME"].map(format_lap_time)
        bests["CLOCK"] = bests["CLOCK"].map(format_hms)
        print(bests.drop(columns=["KEY", "ELAPSED"]).to_string(index=False))

        print("\nRitmo real (10 mejores pilotos, mediana de vueltas de ritmo):")
        pace = pace_by_driver(data).head(10)
        print(with_times(pace, ["BEST_PACE", "MEDIAN_PACE", "MEAN_PACE"]).round(3).to_string(index=False))

    if car:
        print(f"\n===== Coche #{car} =====")
        drivers = best_by_driver(df[df["NUMBER"] == car])
        print(with_times(drivers, ["BEST_LAP", "BEST_S1", "BEST_S2", "BEST_S3"]).to_string(index=False))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("file", nargs="?", help="archivo CSV/Excel (por defecto, toda la carpeta de datos)")
    parser.add_argument("--category")
    parser.add_argument("--car")
    args = parser.parse_args()

    if args.file:
        files = [Path(args.file)]
    else:
        files = sorted(p for p in DATA_DIR.glob("*") if p.suffix.lower() in SUPPORTED_EXTENSIONS)
        if not files:
            raise SystemExit(f"No hay archivos CSV/Excel en {DATA_DIR}")

    for file in files:
        report(file, args.category, args.car)


if __name__ == "__main__":
    main()