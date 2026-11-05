"""Constantes del análisis. Se ajustan aquí sin tocar la lógica."""

# Separador entre segundos y milésimas: '01:32.840'. Usar ":" para mm:ss:ddd.
MS_SEPARATOR = "."

# Una vuelta es "lenta" si supera este múltiplo de la mejor del coche.
SLOW_LAP_THRESHOLD = 1.07

# Banderas al cruzar la meta que indican vuelta neutralizada.
# (FF = bandera final: la vuelta es normal y NO se excluye.)
NEUTRALISED_FLAGS = {"FCY", "SC", "RF"}

PACE_STATUS = "Vuelta de ritmo"

CATEGORY_ORDER = ["HYPERCAR", "LMP2", "LMGT3"]

# ---------------------------------------------------------------------------
# Datos y API
# ---------------------------------------------------------------------------
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Carpeta con los CSV/Excel. Se puede cambiar sin tocar código:
#   WEC_DATA_DIR=/otra/carpeta uvicorn api:app
DATA_DIR = Path(
    os.environ.get("WEC_DATA_DIR", PROJECT_ROOT / "data" / "raw" / "WEC" / "2026" / "Barcelona")
)

CATEGORY_LABELS = {"HYPERCAR": "Hypercar", "LMP2": "LMP2", "LMGT3": "LMGT3"}

# Orígenes del frontend (Vite) autorizados a llamar a la API.
CORS_ORIGINS = os.environ.get(
    "WEC_CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
).split(",")

# Mínimo de vueltas de ritmo en un stint para ajustar su tendencia (degradación).
MIN_PACE_LAPS_FOR_DEGRADATION = 5