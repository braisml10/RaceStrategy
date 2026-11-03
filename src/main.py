
from pathlib import Path

from data_import.importer import import_data, get_data_info

# Ruta raíz del proyecto
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Carpeta de datos de Barcelona 2026
DATA_DIR = (
    PROJECT_ROOT
    / "data"
    / "raw"
    / "WEC"
    / "2026"
    / "Barcelona"
)

# Mostrar los CSV disponibles
csv_files = list(DATA_DIR.glob("*.csv"))

print(f"Carpeta de datos: {DATA_DIR}")
print(f"CSV encontrados: {len(csv_files)}")

if not csv_files:
    raise FileNotFoundError("No se han encontrado archivos CSV.")

# Importar todos los CSV encontrados
dataframes = {}

for file in csv_files:
    print(f"\nImportando: {file.name}")

    df = import_data(file)
    dataframes[file.stem] = df

    info = get_data_info(df)

    print(f"Filas: {info['rows']}")
    print(f"Columnas: {info['columns']}")
    print(f"Nombres: {info['column_names']}")

    print("\nPrimeras 5 filas:")
    print(df.head())

    print("\nValores vacíos:")
    print(df.isna().sum())

print("\nImportación completada correctamente.")

print("\n")
print("\n")
print("\n")
print("\n")
print("Práctica pandas")

bar_fp1 = list(dataframes.values())[0]
print(bar_fp1.head())


# Acceso a los DataFrames:
print(bar_fp1.columns.tolist())
bar_007 = bar_fp1[bar_fp1["NUMBER"] == "007"]
print(bar_007[["NUMBER", "LAP_NUMBER", "LAP_TIME"]])

spec_time = 0.0
valid_laps = 0

for lap in bar_007["LAP_TIME_SECONDS"]:
    if (lap < 100):
        spec_time = lap + spec_time
        valid_laps += 1

print("Tiempo medio por vuelta: ", (spec_time / valid_laps)/60)
