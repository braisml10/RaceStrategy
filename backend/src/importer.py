"""Importación de datos de tiempos (WEC, LMP2, LMGT3...) desde Excel o CSV."""

from __future__ import annotations

from datetime import time, timedelta
from pathlib import Path

import pandas as pd

EXCEL_EXTENSIONS = {".xlsx", ".xls"}
CSV_EXTENSIONS = {".csv"}
SUPPORTED_EXTENSIONS = EXCEL_EXTENSIONS | CSV_EXTENSIONS

# Columnas que se convertirán a segundos (se crea otra columna *_SECONDS)
TIME_COLUMNS = ["LAP_TIME", "S1", "S2", "S3", "PIT_TIME", "ELAPSED", "HOUR"]

# Columnas que se convertirán a número. El resto se mantiene como texto
# (importante: NUMBER debe seguir siendo texto, "007" != "7").
NUMERIC_COLUMNS = [
    "DRIVER_NUMBER", "LAP_NUMBER", "KPH", "TOP_SPEED",
    "LAP_IMPROVEMENT", "S1_IMPROVEMENT", "S2_IMPROVEMENT", "S3_IMPROVEMENT",
]


# ---------------------------------------------------------------------------
# Validación
# ---------------------------------------------------------------------------
def validate_file(file_path: str | Path) -> Path:
    """Comprueba que el archivo existe y que su formato está soportado."""
    path = Path(file_path)

    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    if not path.is_file():
        raise ValueError(f"Path is not a file: {path}")

    if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
        raise ValueError(
            f"Unsupported file format: {path.suffix}. "
            f"Supported: {sorted(SUPPORTED_EXTENSIONS)}"
        )

    return path


# ---------------------------------------------------------------------------
# Lectura
# ---------------------------------------------------------------------------
def _read_excel(path: Path, sheet_name: str | int) -> pd.DataFrame:
    # Todo como texto: si no, pandas convierte "007" en 7 (igual que en CSV).
    return pd.read_excel(path, sheet_name=sheet_name, dtype=str)


def _read_csv(path: Path) -> pd.DataFrame:
    """Lee un CSV detectando automáticamente el separador (, ; tab)
    y probando varias codificaciones habituales."""
    last_error: Exception | None = None

    for encoding in ("utf-8-sig", "latin-1"):
        try:
            return pd.read_csv(
                path,
                sep=None,
                engine="python",
                encoding=encoding,
                dtype=str,              # evita perder ceros a la izquierda (007)
                skipinitialspace=True,  # "A; B" -> "A", "B"
            )
        except UnicodeDecodeError as error:
            last_error = error

    raise ValueError(f"Could not decode CSV file: {last_error}")


# ---------------------------------------------------------------------------
# Limpieza
# ---------------------------------------------------------------------------
def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Nombres de columna en MAYÚSCULAS, sin espacios sobrantes.
    'Lap Time' -> 'LAP_TIME'."""
    df = df.copy()
    df.columns = (
        df.columns.astype(str)
        .str.strip()
        .str.upper()
        .str.replace(r"\s+", "_", regex=True)
    )
    return df


def clean_data(df: pd.DataFrame) -> pd.DataFrame:
    """Elimina columnas vacías, normaliza el nº de coche y convierte
    a número las columnas numéricas conocidas."""
    df = df.copy()

    # Columnas totalmente vacías (p. ej. la que genera un ';' final)
    df = df.dropna(axis=1, how="all")

    # Espacios sobrantes en textos
    for column in df.select_dtypes(exclude="number").columns:
        df[column] = df[column].astype("string").str.strip()

    # Nº de coche: siempre texto. "007" se mantiene; "7.0" (Excel) -> "7"
    if "NUMBER" in df.columns:
        df["NUMBER"] = (
            df["NUMBER"].astype("string").str.strip().str.replace(r"\.0$", "", regex=True)
        )

    for column in NUMERIC_COLUMNS:
        if column in df.columns and not pd.api.types.is_numeric_dtype(df[column]):
            df[column] = pd.to_numeric(
                df[column].str.replace(",", ".", regex=False), errors="coerce"
            )

    return df


def time_to_seconds(value) -> float | None:
    """
    Convierte un tiempo a segundos. Acepta:
      "1:32.840" / "1:32,840"  -> 92.84
      "1:01:32.840" (h:m:s)    -> 3692.84
      "41.808" / 41.808        -> 41.808
      datetime.time (Excel)    -> segundos
      timedelta / Timedelta    -> segundos
    Devuelve None si no se puede interpretar.
    """
    if value is None or (not isinstance(value, (str, time)) and pd.isna(value)):
        return None

    if isinstance(value, (timedelta, pd.Timedelta)):
        return value.total_seconds()

    if isinstance(value, time):
        return (
            value.hour * 3600
            + value.minute * 60
            + value.second
            + value.microsecond / 1_000_000
        )

    if isinstance(value, (int, float)):
        return float(value)

    text = str(value).strip().replace(",", ".")
    if not text:
        return None

    try:
        total = 0.0
        for part in text.split(":"):
            total = total * 60 + float(part)
        return total
    except ValueError:
        return None


def convert_time_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Añade columnas *_SECONDS para los tiempos de vuelta, sectores y pit."""
    df = df.copy()

    for column in TIME_COLUMNS:
        if column in df.columns:
            df[f"{column}_SECONDS"] = df[column].apply(time_to_seconds)

    return df


# ---------------------------------------------------------------------------
# API pública
# ---------------------------------------------------------------------------
def import_data(
    file_path: str | Path,
    sheet_name: str | int = 0,
    required_columns: list[str] | None = None,
) -> pd.DataFrame:
    """
    Importa datos de tiempos desde Excel (.xlsx/.xls) o CSV.

    required_columns: columnas que deben existir (tras normalizar nombres).
    Devuelve un DataFrame normalizado con los tiempos convertidos a segundos.
    """
    path = validate_file(file_path)

    try:
        if path.suffix.lower() in EXCEL_EXTENSIONS:
            df = _read_excel(path, sheet_name)
        else:
            df = _read_csv(path)
    except Exception as error:
        raise ValueError(f"Could not import file {path.name}: {error}") from error

    if df.empty:
        raise ValueError("The file contains no data.")

    df = normalize_columns(df)
    df = clean_data(df)

    if required_columns:
        missing = [c.upper() for c in required_columns if c.upper() not in df.columns]
        if missing:
            raise ValueError(
                f"Missing required columns: {missing}. Found: {df.columns.tolist()}"
            )

    return convert_time_columns(df)


def get_data_info(df: pd.DataFrame) -> dict:
    """Resumen básico del DataFrame importado."""
    return {
        "rows": len(df),
        "columns": len(df.columns),
        "column_names": df.columns.tolist(),
        "missing_values": df.isna().sum().to_dict(),
        "data_types": df.dtypes.astype(str).to_dict(),
    }


def separate_shared_numbers(df: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    """Separa coches de equipos distintos que comparten número y detecta duplicados.

    Pasa, por ejemplo, cuando un CSV se guarda con Excel: "007" (Aston Martin)
    se convierte en 7 y se confunde con el 7 de Toyota. Cada coche afectado pasa
    a llamarse "7 (Aston Martin)" / "7 (Toyota)": nunca se adivina cuál era el
    "007". Devuelve (datos, avisos para mostrar al usuario).

    Si tras separar siguen repetidas las vueltas de un mismo coche, el archivo
    trae filas duplicadas y se lanza ValueError.
    """
    notices: list[str] = []
    if {"NUMBER", "TEAM"} <= set(df.columns):
        df = df.copy()
        for number in df["NUMBER"].dropna().unique().tolist():
            rows = df["NUMBER"] == number
            teams = df.loc[rows, "TEAM"].fillna("").unique().tolist()
            if len(teams) < 2:
                continue
            column = "TEAM"
            if "MANUFACTURER" in df.columns:
                makers = df.loc[rows, "MANUFACTURER"].fillna("")
                if makers.nunique() == len(teams):
                    column = "MANUFACTURER"
            labels = df[column].fillna("")
            new_names = []
            for label in labels[rows].unique().tolist():
                name = f"{number} ({label})"
                df.loc[rows & (labels == label), "NUMBER"] = name
                new_names.append(name)
            notices.append(
                f"En el archivo el número {number} corresponde a coches de equipos distintos "
                f"({', '.join(t for t in teams if t)}). Suele pasar al guardar el CSV con Excel, "
                f"que borra los ceros de «007». Se han separado por equipo: {'; '.join(new_names)}."
            )

    repeated = df[df.duplicated(["NUMBER", "LAP_NUMBER"], keep=False)]
    if not repeated.empty:
        cars = sorted(repeated["NUMBER"].unique())
        raise ValueError(
            f"hay vueltas repetidas en los coches {cars}: el archivo trae filas duplicadas "
            "para un mismo coche y equipo."
        )
    return df, notices