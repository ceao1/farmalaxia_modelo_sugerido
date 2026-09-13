"""Carga de datos y partición temporal del POC.

La partición es fija y está declarada aquí, no como parámetro: cambiarla a
mitad del experimento invalidaría la comparación contra la vara del spec.
"""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from comun import DERIVADO

SEMILLA = 7
MESES_TRAIN = ["2025-09", "2025-10", "2025-11", "2025-12",
               "2026-01", "2026-02", "2026-03", "2026-04"]
MES_VAL = "2026-05"
MES_TEST = "2026-07"   # agosto no: termina en jueves 27, está censurado

# Junio de 2026 queda FUERA de entrenamiento y validación a propósito: es el mes
# de la expansión de 24 rutas, con 3.312 clientes sin historia previa. Validar
# sobre él cortaba el entrenamiento a 54 árboles, porque en ese mes las variables
# de afinidad y marca están vacías y el modelo no puede mostrar mejora.
# Sus datos sí entran como HISTORIA para construir las variables de julio, que es
# lo que ocurriría en producción.
MES_EXCLUIDO = "2026-06"


def cargar_compras() -> pd.DataFrame:
    """Líneas de compra reales: piezas > 0 y sin paquetes promocionales."""
    df = pd.read_parquet(DERIVADO / "ventas.parquet")
    df["anio_mes"] = df["anio_mes"].astype(str)
    if "es_pack" not in df.columns:
        df["es_pack"] = df["sku"].fillna("").str.upper().str.startswith("PP")
    return df[df.es_compra & ~df.es_pack].copy()


def recomendables_base() -> set[str]:
    """SKU que son mercancía real: ni promoción, ni exhibidor.

    NO aplica el filtro de actividad: la bandera `activo_ult2m` del parquet está
    calculada sobre el periodo COMPLETO, así que usarla para un mes de
    entrenamiento metería información del futuro. La actividad se resuelve por
    mes en `recomendables_al_mes`.
    """
    f = pd.read_parquet(DERIVADO / "dim_sku_flags.parquet")
    return set(f.loc[~f.es_pack & ~f.es_exhibidor, "sku"])


def recomendables_al_mes(df: pd.DataFrame, mes: str, base: set[str]) -> set[str]:
    """De `base`, los que tuvieron venta en los dos meses anteriores a `mes`.

    Recomendar un producto que dejó de venderse es un error operativo, pero
    «dejó de venderse» solo puede juzgarse con el pasado de cada mes.
    """
    previos = sorted(m for m in df.anio_mes.unique() if m < mes)[-2:]
    activos = set(df.loc[df.anio_mes.isin(previos), "sku"])
    return base & activos


def historia_hasta(df: pd.DataFrame, mes: str) -> pd.DataFrame:
    """Filas estrictamente anteriores a `mes`. Es la única puerta a datos pasados."""
    return df[df.anio_mes < mes]


def ruta_dominante(hist: pd.DataFrame) -> pd.Series:
    """Ruta de preventa más frecuente por cliente. Un cliente puede cambiar de ruta."""
    return (hist.groupby("cliente_id", observed=True).ruta_preventa
                .agg(lambda s: s.value_counts().index[0]))
