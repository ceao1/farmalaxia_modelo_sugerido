"""Métricas de recomendación, medidas por cliente y promediadas.

`hit_rate_at_n` es la principal: fracción de clientes en que al menos una de las
N sugerencias se compró. Es la que entiende el equipo comercial.

La selección de los N espacios depende de la POLÍTICA:
  - libre : los N mejor puntuados
  - mixta : cuotas por origen (p. ej. 5 dormidos + 3 nunca comprados)
Comparar un modelo bajo una política contra otro bajo otra le daría a uno el
crédito de la política. Siempre se compara dentro de la misma.
"""
import numpy as np
import pandas as pd

NS_POR_DEFECTO = (3, 5, 8, 16, 24, 40)
CUOTAS_MIXTA = {"dormido": 5, "nunca": 3}


def _ordenado(ds: pd.DataFrame, col: str) -> pd.DataFrame:
    """Desempate estable por `sku` para que el resultado no dependa del orden de entrada."""
    return ds.sort_values([col, "sku"], ascending=[False, True])


def top_n(ds: pd.DataFrame, col: str, n: int) -> pd.DataFrame:
    """Las n filas de mayor puntuación por cliente (política libre)."""
    return _ordenado(ds, col).groupby("cliente_id", observed=True).head(n)


def seleccionar(ds: pd.DataFrame, col: str, n: int = 8,
                politica: str = "libre",
                cuotas: dict[str, int] | None = None,
                orden: pd.DataFrame | None = None) -> pd.DataFrame:
    """Aplica la política de asignación de los n espacios.

    En la mixta, si a un cliente le faltan candidatos de una clase los espacios
    sobrantes se llenan con la otra por puntuación: un cliente sin dormidos no
    debe recibir una lista corta.

    `orden` permite pasar el conjunto YA ordenado por `col`. Ordenar diez
    millones de filas cuesta segundos, y evaluar cinco modelos bajo dos
    políticas lo repetía trescientas veces.
    """
    if orden is None:
        orden = _ordenado(ds, col)
    if politica == "libre":
        return orden.groupby("cliente_id", observed=True).head(n)
    if politica != "mixta":
        raise ValueError(f"política desconocida: {politica}")

    cuotas = cuotas or CUOTAS_MIXTA
    partes = [orden[orden.origen == org].groupby("cliente_id", observed=True).head(k)
              for org, k in cuotas.items()]
    sel = pd.concat(partes) if partes else orden.head(0)

    # rellenar a quien le falten espacios
    faltan = n - sel.groupby("cliente_id", observed=True).size()
    faltan = faltan[faltan > 0]
    if len(faltan):
        resto = orden[~orden.index.isin(sel.index)]
        extra = [g.head(int(faltan[c]))
                 for c, g in resto.groupby("cliente_id", observed=True) if c in faltan.index]
        if extra:
            sel = pd.concat([sel] + extra)

    # nunca más de n por cliente
    return _ordenado(sel, col).groupby("cliente_id", observed=True).head(n)


def hit_rate_at_n(ds: pd.DataFrame, col: str, n: int, **kw) -> float:
    t = seleccionar(ds, col, n, **kw)
    return float(t.groupby("cliente_id", observed=True).y.max().mean() * 100)


def recall_at_n(ds: pd.DataFrame, col: str, n: int, **kw) -> float:
    t = seleccionar(ds, col, n, **kw)
    encontrados = t.groupby("cliente_id", observed=True).y.sum()
    totales = ds.groupby("cliente_id", observed=True).y.sum()
    r = (encontrados / totales.replace(0, np.nan)).dropna()
    return float(r.mean() * 100)


def precision_at_n(ds: pd.DataFrame, col: str, n: int, **kw) -> float:
    t = seleccionar(ds, col, n, **kw)
    return float((t.groupby("cliente_id", observed=True).y.sum() / n).mean() * 100)


def _metricas_de(ds: pd.DataFrame, sel: pd.DataFrame, col: str, n: int) -> dict:
    """Las cuatro métricas a partir de UNA selección ya hecha."""
    g = sel.groupby("cliente_id", observed=True)
    totales = ds.groupby("cliente_id", observed=True).y.sum()
    encontrados = g.y.sum()
    t = sel.copy()
    t["pos"] = g.cumcount() + 1
    t["acum"] = g.y.cumsum()
    aportes = (t[t.y == 1].assign(p=lambda x: x.acum / x.pos)
               .groupby("cliente_id", observed=True).p.sum())
    tope = totales.clip(upper=n)
    ap = (aportes.reindex(tope.index).fillna(0) / tope.replace(0, np.nan)).dropna()
    rec = (encontrados / totales.replace(0, np.nan)).dropna()
    return {"hit_rate": round(float(g.y.max().mean() * 100), 2),
            "recall": round(float(rec.mean() * 100), 2),
            "precision": round(float((encontrados / n).mean() * 100), 2),
            "map": round(float(ap.mean() * 100), 2)}


def map_at_n(ds: pd.DataFrame, col: str, n: int, **kw) -> float:
    """Precisión media en cada posición acertada, promediada por cliente."""
    t = seleccionar(ds, col, n, **kw).copy()
    t = _ordenado(t, col)
    t["pos"] = t.groupby("cliente_id", observed=True).cumcount() + 1
    t["acum"] = t.groupby("cliente_id", observed=True).y.cumsum()
    t["prec_en_pos"] = t.acum / t.pos
    aportes = t[t.y == 1].groupby("cliente_id", observed=True).prec_en_pos.sum()
    totales = ds.groupby("cliente_id", observed=True).y.sum().clip(upper=n)
    ap = (aportes.reindex(totales.index).fillna(0) / totales.replace(0, np.nan)).dropna()
    return float(ap.mean() * 100)


def desglose_origen(ds: pd.DataFrame, col: str, n: int, **kw) -> dict[str, int]:
    """Aciertos separados en reactivación (`dormido`) y descubrimiento (`nunca`).

    Obligatorio en todo informe: con 24 dormidos por cliente y 8 espacios, un
    modelo puede reactivar sin descubrir nada y lucir bien.
    """
    t = seleccionar(ds, col, n, **kw)
    return t[t.y == 1].origen.value_counts().to_dict()


def curva(ds: pd.DataFrame, col: str, ns=NS_POR_DEFECTO, **kw) -> pd.DataFrame:
    """Una selección por cada N, no una por cada métrica de cada N."""
    orden = kw.pop("orden", None)
    if orden is None:
        orden = _ordenado(ds, col)
    filas = []
    for n in ns:
        sel = seleccionar(ds, col, n, orden=orden, **kw)
        filas.append({"N": n, **_metricas_de(ds, sel, col, n)})
    return pd.DataFrame(filas)


def bootstrap_ic(ds: pd.DataFrame, col: str, n: int,
                 reps: int = 200, semilla: int = 7, **kw) -> tuple[float, float]:
    """Intervalo del 95 % remuestreando CLIENTES, no filas.

    Remuestrear filas rompería los grupos y daría un intervalo falsamente estrecho.
    """
    rng = np.random.default_rng(semilla)
    t = seleccionar(ds, col, n, **kw)
    acierta = t.groupby("cliente_id", observed=True).y.max().to_numpy()
    vals = [acierta[rng.integers(0, len(acierta), len(acierta))].mean() * 100
            for _ in range(reps)]
    return float(np.percentile(vals, 2.5)), float(np.percentile(vals, 97.5))
