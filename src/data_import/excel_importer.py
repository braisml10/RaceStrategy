
from pathlib import Path
import pandas as pd


SUPPORTED_EXTENSIONS = {".xlsx", ".xls"}


def validate_excel_file(file_path: str | Path) -> Path:
    """Validate the Excel file."""

    path = Path(file_path)

    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    if not path.is_file():
        raise ValueError(f"Path is not a file: {path}")

    if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
        raise ValueError(
            f"Unsupported file format: {path.suffix}"
        )

    return path


def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize column names."""

    df = df.copy()

    df.columns = (
        df.columns
        .astype(str)
        .str.strip()
        .str.upper()
    )

    return df


def time_to_seconds(value):
    """
    Convert a time value such as:
    1:32.840 -> 92.840
    41.808   -> 41.808
    """

    if pd.isna(value):
        return None

    value = str(value).strip()

    if not value:
        return None

    try:
        parts = value.split(":")

        if len(parts) == 2:
            minutes = float(parts[0])
            seconds = float(parts[1])

            return minutes * 60 + seconds

        return float(value)

    except ValueError:
        return None


def convert_time_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Convert lap and sector times to seconds."""

    df = df.copy()

    time_columns = [
        "LAP_TIME",
        "S1",
        "S2",
        "S3",
        "PIT_TIME"
    ]

    for column in time_columns:
        if column in df.columns:
            df[f"{column}_SECONDS"] = (
                df[column].apply(time_to_seconds)
            )

    return df


def import_excel(
    file_path: str | Path,
    sheet_name: str | int = 0
) -> pd.DataFrame:
    """
    Import WEC timing data from an Excel file.

    Returns a normalized Pandas DataFrame.
    """

    path = validate_excel_file(file_path)

    try:
        df = pd.read_excel(
            path,
            sheet_name=sheet_name
        )

    except Exception as error:
        raise ValueError(
            f"Could not import Excel file: {error}"
        ) from error

    if df.empty:
        raise ValueError("The Excel sheet is empty.")

    df = normalize_columns(df)

    df = convert_time_columns(df)

    return df


def get_excel_info(df: pd.DataFrame) -> dict:
    """Return basic information about imported data."""

    return {
        "rows": len(df),
        "columns": len(df.columns),
        "column_names": df.columns.tolist(),
        "missing_values": df.isna().sum().to_dict(),
        "data_types": df.dtypes.astype(str).to_dict()
    }