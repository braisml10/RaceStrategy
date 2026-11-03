"""Constantes del análisis. Se ajustan aquí sin tocar la lógica."""

# Separador entre segundos y milésimas: '01:32:840'. Usar "," para mm:ss,ddd.
MS_SEPARATOR = ":"

# Una vuelta es "lenta" si supera este múltiplo de la mejor del coche.
SLOW_LAP_THRESHOLD = 1.07

# Banderas al cruzar la meta que indican vuelta neutralizada.
# (FF = bandera final: la vuelta es normal y NO se excluye.)
NEUTRALISED_FLAGS = {"FCY", "SC", "RF"}

PACE_STATUS = "Vuelta de ritmo"

CATEGORY_ORDER = ["HYPERCAR", "LMP2", "LMP3", "LMGT3"]