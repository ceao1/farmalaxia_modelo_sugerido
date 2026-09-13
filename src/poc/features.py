"""Variables del modelo. Todas se calculan con historia anterior al mes objetivo.

Quien modifique este módulo debe preservar esa regla: es la diferencia entre un
resultado creíble y uno que solo funciona en el papel.
"""
import numpy as np
import pandas as pd

from . import datos


def popularidad_ruta(hist: pd.DataFrame, ruta_cli: pd.Series) -> pd.Series:
    """Clientes distintos que compraron cada SKU en cada ruta."""
    pares = hist[["cliente_id", "sku"]].drop_duplicates().copy()
    pares["ruta"] = pares.cliente_id.map(ruta_cli)
    pares = pares.dropna(subset=["ruta"])
    return pares.groupby(["ruta", "sku"], observed=True).cliente_id.nunique()


def popularidad_global(hist: pd.DataFrame) -> pd.Series:
    """Clientes distintos que compraron cada SKU, sin distinguir ruta."""
    return hist.groupby("sku", observed=True).cliente_id.nunique()


def agregar_ruta(ds: pd.DataFrame, hist: pd.DataFrame,
                 ruta_forzada: dict[str, str] | None = None) -> pd.DataFrame:
    """Añade `pop_ruta`, `rango_ruta` y `pop_global` al conjunto de candidatos."""
    ruta_cli = datos.ruta_dominante(hist)
    if ruta_forzada:
        ruta_cli = pd.concat([ruta_cli, pd.Series(ruta_forzada)])
        ruta_cli = ruta_cli[~ruta_cli.index.duplicated(keep="last")]

    pop_r = popularidad_ruta(hist, ruta_cli)
    pop_g = popularidad_global(hist)

    # rango dentro de cada ruta: 1 = el más popular
    rango = (pop_r.groupby(level=0).rank(ascending=False, method="min")
                  .rename("rango_ruta"))

    out = ds.copy()
    out["ruta"] = out.cliente_id.map(ruta_cli)
    idx = pd.MultiIndex.from_arrays([out.ruta, out.sku])
    out["pop_ruta"] = pop_r.reindex(idx).to_numpy()
    out["rango_ruta"] = rango.reindex(idx).to_numpy()
    out["pop_global"] = out.sku.map(pop_g)

    out["pop_ruta"] = out.pop_ruta.fillna(0)
    out["pop_global"] = out.pop_global.fillna(0)
    # sin rango = nadie lo compró en la ruta: se le da el peor rango posible
    out["rango_ruta"] = out.rango_ruta.fillna(9999)
    return out.drop(columns="ruta")


def agregar_marca(ds: pd.DataFrame, hist: pd.DataFrame, dim: pd.DataFrame) -> pd.DataFrame:
    """Variables de marca. El EDA mostró que 79,8 % de lo nuevo es de marca conocida."""
    mrc = dict(zip(dim.sku, dim.marca))
    h = hist.copy()
    h["marca"] = h.sku.map(mrc)
    h = h.dropna(subset=["marca"])

    marcas_cli = h.groupby("cliente_id", observed=True).marca.apply(set)
    peso = (h.groupby(["cliente_id", "marca"], observed=True).size()
              / h.groupby("cliente_id", observed=True).size())
    skus_marca = h.groupby(["cliente_id", "marca"], observed=True).sku.nunique()

    out = ds.copy()
    out["marca"] = out.sku.map(mrc)
    out["marca_conocida"] = [
        1 if (c in marcas_cli.index and m in marcas_cli[c]) else 0
        for c, m in zip(out.cliente_id, out.marca)]
    idx = pd.MultiIndex.from_arrays([out.cliente_id, out.marca])
    out["peso_marca"] = peso.reindex(idx).to_numpy()
    out["skus_de_la_marca"] = skus_marca.reindex(idx).to_numpy()
    out["peso_marca"] = out.peso_marca.fillna(0.0)
    out["skus_de_la_marca"] = out.skus_de_la_marca.fillna(0)
    return out.drop(columns="marca")


def matriz_afinidad(hist: pd.DataFrame, minimo: int = 50) -> pd.Series:
    """Co-ocurrencias entre SKU dentro de una misma canasta (cliente + fecha).

    Se exige un piso de `minimo` canastas: sin él, los pares raros dominan y
    parecen señal cuando son ruido.
    """
    h = hist.copy()
    h["canasta"] = h.cliente_id.astype(str) + "|" + h.fecha.dt.strftime("%Y%m%d")
    b = h[["canasta", "sku"]].drop_duplicates()
    par = b.merge(b, on="canasta")
    par = par[par.sku_x != par.sku_y]
    co = par.groupby(["sku_x", "sku_y"], observed=True).canasta.nunique()
    return co[co >= minimo]


def agregar_afinidad(ds: pd.DataFrame, hist: pd.DataFrame, afin: pd.Series) -> pd.DataFrame:
    """Afinidad del candidato con lo que el cliente ya lleva: máximo y suma.

    Se acumula POR CLIENTE, no por fila: un cliente tiene ~400 candidatos y ~42
    productos comprados, así que recorrer fila por fila multiplica el trabajo por
    cuatrocientos. Con el conjunto de prueba completo la diferencia es de minutos
    a horas.
    """
    comprados = hist.groupby("cliente_id", observed=True).sku.apply(set)
    # vecinos[sku] = {sku_vecino: co-ocurrencias}
    vecinos: dict[str, dict[str, float]] = {}
    for (x, y), v in afin.items():
        vecinos.setdefault(x, {})[y] = float(v)

    partes = []
    for cli, g in ds.groupby("cliente_id", observed=True, sort=False):
        acum_max: dict[str, float] = {}
        acum_sum: dict[str, float] = {}
        for s0 in comprados.get(cli, ()):
            for y, v in vecinos.get(s0, {}).items():
                if v > acum_max.get(y, 0.0):
                    acum_max[y] = v
                acum_sum[y] = acum_sum.get(y, 0.0) + v
        # se alinea por ÍNDICE, no por posición: las filas de un cliente no tienen
        # por qué venir contiguas y un relleno posicional fallaría en silencio.
        partes.append(pd.DataFrame(
            {"afin_max": [acum_max.get(s, 0.0) for s in g.sku],
             "afin_suma": [acum_sum.get(s, 0.0) for s in g.sku]},
            index=g.index))

    res = pd.concat(partes) if partes else pd.DataFrame(columns=["afin_max", "afin_suma"])
    out = ds.copy()
    out["afin_max"] = res.afin_max.reindex(ds.index).fillna(0.0).astype("float32")
    out["afin_suma"] = res.afin_suma.reindex(ds.index).fillna(0.0).astype("float32")
    return out


def agregar_cliente(ds: pd.DataFrame, hist: pd.DataFrame) -> pd.DataFrame:
    """Variables del cliente: amplitud de surtido, frecuencia y ticket."""
    g = hist.groupby("cliente_id", observed=True)
    n_skus = g.sku.nunique()
    n_compras = g.fecha.nunique()
    ticket = g.importe_preventa.sum() / n_compras.replace(0, 1)

    out = ds.copy()
    out["n_skus_cliente"] = out.cliente_id.map(n_skus).fillna(0)
    out["n_compras_cliente"] = out.cliente_id.map(n_compras).fillna(0)
    out["ticket_medio"] = out.cliente_id.map(ticket).fillna(0.0)
    return out


def agregar_producto(ds: pd.DataFrame, hist: pd.DataFrame) -> pd.DataFrame:
    """Variables del producto: precio unitario, cuánto retiene y hace cuánto existe.

    `pct_core` = fracción de sus compradores que lo pidieron en 3 meses o más.
    Separa los básicos (se recuerdan) de los de prueba (se introducen).
    """
    g = hist.groupby("sku", observed=True)
    precio = g.importe_preventa.sum() / g.piezas_preventa.sum().replace(0, 1)
    meses = g.anio_mes.nunique()
    por_par = hist.groupby(["sku", "cliente_id"], observed=True).anio_mes.nunique()
    pct_core = por_par.groupby(level=0).apply(lambda x: (x >= 3).mean() * 100)

    out = ds.copy()
    out["precio"] = out.sku.map(precio).fillna(0.0)
    out["meses_disponible"] = out.sku.map(meses).fillna(0)
    out["pct_core"] = out.sku.map(pct_core).fillna(0.0)
    return out


def agregar_origen(ds: pd.DataFrame) -> pd.DataFrame:
    """Convierte `origen` en variable numérica.

    Es la variable con más señal cruda del conjunto: un dormido tiene 8,6 veces
    más probabilidad de comprarse que uno nunca comprado.
    """
    out = ds.copy()
    out["es_dormido"] = (out.origen == "dormido").astype(int)
    return out


COLUMNAS_MODELO = [
    "pop_ruta", "rango_ruta", "pop_global",
    "marca_conocida", "peso_marca", "skus_de_la_marca",
    "afin_max", "afin_suma",
    "n_skus_cliente", "n_compras_cliente", "ticket_medio",
    "precio", "pct_core", "meses_disponible",
    "es_dormido",
]
