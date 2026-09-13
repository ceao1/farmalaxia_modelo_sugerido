"""Línea base y propuestas simples.

B1 es la vara: reproduce la lógica del modelo que la empresa opera hoy
—popularidad entre clientes de la misma ruta—. P1 y P2 son aportes nuestros.

Todas devuelven una puntuación por fila; el reparto de los 8 espacios entre
dormidos y nunca comprados es una POLÍTICA aparte, en `metricas.seleccionar`.
"""
import pandas as pd


def b0_global(ds: pd.DataFrame) -> pd.Series:
    """Popularidad global. Solo sirve para dimensionar cuánto aporta la ruta."""
    return ds.pop_global.astype(float)


def b1_ruta(ds: pd.DataFrame) -> pd.Series:
    """Popularidad en la ruta del cliente: el modelo actual, reconstruido."""
    return ds.pop_ruta.astype(float)


def p1_ruta_marca(ds: pd.DataFrame) -> pd.Series:
    """B1 pero anteponiendo las marcas que el cliente ya compra.

    El desplazamiento garantiza que cualquier candidato de marca conocida quede
    sobre cualquiera de marca desconocida, conservando el orden de ruta dentro
    de cada grupo.
    """
    desplazamiento = float(ds.pop_ruta.max()) + 1.0
    return ds.pop_ruta.astype(float) + ds.marca_conocida.astype(float) * desplazamiento


def p2_itemitem(ds: pd.DataFrame) -> pd.Series:
    """Afinidad acumulada con lo que el cliente ya lleva."""
    return ds.afin_suma.astype(float)


TODAS = {"B0": b0_global, "B1": b1_ruta, "P1": p1_ruta_marca, "P2": p2_itemitem}
