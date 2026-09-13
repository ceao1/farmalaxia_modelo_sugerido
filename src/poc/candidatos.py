"""Conjunto candidato por cliente-mes.

Un candidato es un producto recomendable que el cliente **no está comprando
actualmente**. La distinción importa:

  - habitual   : lo pidió en los últimos `VENTANA_HABITUAL` meses. Se EXCLUYE:
                 lo iba a pedir igual, acertarle infla la métrica sin generar venta.
  - dormido    : lo conoce pero dejó de pedirlo. Se INCLUYE: recordárselo suma
                 un SKU al mes, que es el objetivo del negocio.
  - nunca      : no lo ha comprado jamás. Se INCLUYE: es descubrimiento puro.

Dormido y nunca se marcan en la columna `origen` porque su tasa base difiere
por un factor de ocho: sin el desglose, un modelo que solo reactiva parece
tan bueno como uno que además descubre.
"""
import pandas as pd

from . import datos

VENTANA_HABITUAL = 2   # meses


def meses_previos(mes: str, ventana: int) -> list[str]:
    """Los `ventana` meses de CALENDARIO anteriores a `mes`.

    Calendario y no "los últimos que aparecen en los datos": si un mes viniera
    vacío, esa versión estiraría la ventana sin avisar.
    """
    p = pd.Period(mes, freq="M")
    return [str(p - k) for k in range(1, ventana + 1)]


def candidatos_cliente(habituales: set[str], recom: set[str]) -> list[str]:
    """Recomendables que el cliente no está pidiendo ahora, en orden estable."""
    return sorted(recom - habituales)


def construir(df: pd.DataFrame, mes: str, recom: set[str],
              clientes: set[str] | None = None,
              ventana: int = VENTANA_HABITUAL) -> pd.DataFrame:
    """Filas cliente-mes × candidato con etiqueta `y` y columna `origen`.

    `y = 1` si el cliente compró ese SKU en `mes`.
    `origen` ∈ {"dormido", "nunca"}.
    """
    hist = datos.historia_hasta(df, mes)
    objetivo = df[df.anio_mes == mes]
    if clientes is not None:
        hist = hist[hist.cliente_id.isin(clientes)]
        objetivo = objetivo[objetivo.cliente_id.isin(clientes)]

    reciente = (hist[hist.anio_mes.isin(meses_previos(mes, ventana))]
                .groupby("cliente_id", observed=True).sku.apply(set))
    alguna_vez = hist.groupby("cliente_id", observed=True).sku.apply(set)
    compras_mes = objetivo.groupby("cliente_id", observed=True).sku.apply(set)

    filas = []
    for cli in compras_mes.index:
        if cli not in alguna_vez.index:
            continue                      # sin historia: no hay con qué personalizar
        conocidos = alguna_vez[cli]
        habituales = reciente.get(cli, set())
        cands = candidatos_cliente(habituales, recom)
        comprados_mes = compras_mes[cli]
        for s in cands:
            filas.append((cli, mes, s,
                          1 if s in comprados_mes else 0,
                          "dormido" if s in conocidos else "nunca"))
    return pd.DataFrame(filas, columns=["cliente_id", "anio_mes", "sku", "y", "origen"])
