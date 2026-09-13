"""Traducción de las métricas a lenguaje de negocio.

Advertencia que debe acompañar siempre a estos números: los datos dicen si el
modelo ACIERTA qué comprará el cliente, no si la sugerencia lo CAUSÓ. Por eso el
impacto se entrega como escenarios con la tasa de conversión a la vista, nunca
como una cifra única. Solo un piloto con grupo de control mide impacto real.
"""
import pandas as pd

from .metricas import desglose_origen, seleccionar


def aciertos_por_cliente(ds: pd.DataFrame, col: str, n: int, **kw) -> float:
    """Cuántas de las n sugerencias se compraron, en promedio por cliente."""
    t = seleccionar(ds, col, n, **kw)
    return float(t.groupby("cliente_id", observed=True).y.sum().mean())


def sku_extra_por_compra(ds: pd.DataFrame, col: str, n: int,
                         compras_mes: float, **kw) -> float:
    """Aciertos mensuales repartidos entre las compras del mes.

    Es la cifra que pidió el negocio: cuántos SKU adicionales se llevaría el
    cliente en cada visita.
    """
    return round(aciertos_por_cliente(ds, col, n, **kw) / compras_mes, 3)


def importe_de_aciertos(ds: pd.DataFrame, col: str, n: int,
                        precio: pd.Series, **kw) -> float:
    """Importe medio por cliente de los productos acertados."""
    t = seleccionar(ds, col, n, **kw).copy()
    t["imp"] = t.y * t.sku.map(precio).fillna(0.0)
    return float(t.groupby("cliente_id", observed=True).imp.sum().mean())


def tabla_escenarios(importe_mes: float, n_clientes: int,
                     tasas=(0.10, 0.20, 0.30)) -> pd.DataFrame:
    """Impacto anual bajo distintos supuestos de conversión incremental.

    `tasa` = fracción de los aciertos que NO habría ocurrido sin la sugerencia.
    Es un supuesto, no un dato: por eso va como columna y no escondido.
    """
    return pd.DataFrame([{
        "tasa_conversion": t,
        "mensual": round(importe_mes * n_clientes * t, 0),
        "anual": round(importe_mes * n_clientes * t * 12, 0),
    } for t in tasas])


def resumen(ds: pd.DataFrame, col: str, n: int, precio: pd.Series,
            compras_mes: float, **kw) -> dict:
    """Todo lo que el informe necesita de un modelo bajo una política.

    Selecciona UNA vez: cada llamada a `seleccionar` sobre el conjunto completo
    """
    sel = seleccionar(ds, col, n, **kw).copy()
    g = sel.groupby("cliente_id", observed=True)
    aciertos = float(g.y.sum().mean())
    sel["imp"] = sel.y * sel.sku.map(precio).fillna(0.0)
    importe = float(sel.groupby("cliente_id", observed=True).imp.sum().mean())

    d = sel[sel.y == 1].origen.value_counts().to_dict()
    dorm, nunca = d.get("dormido", 0), d.get("nunca", 0)
    total = dorm + nunca
    return {
        "aciertos_por_cliente": round(aciertos, 3),
        "sku_extra_por_compra": round(aciertos / compras_mes, 3),
        "importe_por_cliente": round(importe, 1),
        "aciertos_dormido": int(dorm),
        "aciertos_nunca": int(nunca),
        "pct_descubrimiento": round(nunca / total * 100, 1) if total else 0.0,
    }
