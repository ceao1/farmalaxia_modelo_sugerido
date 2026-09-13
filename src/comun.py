"""Rutas del proyecto. Cada script las resuelve desde su propia ubicación,
así que la tubería funciona sin importar desde dónde se invoque."""
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
CRUDO = RAIZ / "datos" / "crudo"          # dbventas.bak
DERIVADO = RAIZ / "datos" / "derivado"    # parquet y tsv intermedios
RESULTADOS = RAIZ / "resultados"          # métricas en JSON
INFORMES = RAIZ / "informes"              # entregables
SRC = RAIZ / "src"

for _d in (CRUDO, DERIVADO, RESULTADOS, INFORMES):
    _d.mkdir(parents=True, exist_ok=True)
