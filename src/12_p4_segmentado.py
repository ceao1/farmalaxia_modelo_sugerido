"""P4 — enrutamiento por segmento: un modelo distinto según la historia del cliente.

Método, y el orden importa:
  1. Se mide en MAYO (validación) qué modelo gana en cada tramo de historia.
  2. El umbral se fija ahí.
  3. Se aplica A CIEGAS sobre julio (prueba).

Buscar el umbral sobre julio sería ajustar contra la respuesta: el número
resultante no significaría nada.

Uso:  ./.venv/bin/python src/12_p4_segmentado.py
"""
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from comun import DERIVADO, RESULTADOS
from poc import baselines, candidatos, datos, features, metricas, negocio, ranker

N = 8
MODELOS = ["B0", "B1", "P1", "P2", "P3"]
CORTES = [0, 5, 10, 15, 20, 30, 45]        # sobre n_skus_cliente
CLIENTES_ENTRENAMIENTO = 8000

t0 = time.time()
def log(m): print(f"[{time.time()-t0:6.0f}s] {m}", flush=True)

df = datos.cargar_compras()
base_recom = datos.recomendables_base()
dim = pd.read_parquet(DERIVADO / "dim_sku_flags.parquet")[["sku", "marca"]]
rng = np.random.default_rng(datos.SEMILLA)


def preparar(mes: str, submuestrear: bool) -> pd.DataFrame:
    cache = DERIVADO / f"ds_{mes}{'_sub' if submuestrear else ''}.parquet"
    if cache.exists():
        log(f"   {mes}: leído de caché")
        return pd.read_parquet(cache)
    hist = datos.historia_hasta(df, mes)
    clientes = None
    if submuestrear:
        todos = sorted(set(df.loc[df.anio_mes == mes, "cliente_id"]))
        if len(todos) > CLIENTES_ENTRENAMIENTO:
            clientes = set(rng.choice(todos, CLIENTES_ENTRENAMIENTO, replace=False))
    recom = datos.recomendables_al_mes(df, mes, base_recom)
    ds = candidatos.construir(df, mes, recom, clientes)
    afin = features.matriz_afinidad(hist)
    ds = features.agregar_ruta(ds, hist)
    ds = features.agregar_marca(ds, hist, dim)
    ds = features.agregar_afinidad(ds, hist, afin)
    ds = features.agregar_cliente(ds, hist)
    ds = features.agregar_producto(ds, hist)
    ds = features.agregar_origen(ds)
    for c in features.COLUMNAS_MODELO:
        ds[c] = ds[c].astype("float32")
    ds.to_parquet(cache, index=False)
    log(f"   {mes}: {len(ds):,} filas, {ds.cliente_id.nunique():,} clientes")
    return ds


log("construyendo conjuntos")
train = pd.concat([preparar(m, True) for m in datos.MESES_TRAIN[-3:]], ignore_index=True)
val = preparar(datos.MES_VAL, False)          # TODOS los clientes de mayo
test = preparar(datos.MES_TEST, False)

log("entrenando el ranker (misma semilla y parámetros que el POC)")
val_sub = val[val.cliente_id.isin(
    rng.choice(sorted(val.cliente_id.unique()), CLIENTES_ENTRENAMIENTO, replace=False))]
modelo = ranker.entrenar(train, val_sub, features.COLUMNAS_MODELO, datos.SEMILLA)
log(f"   {modelo.num_trees()} árboles")

for nombre, ds in (("validación", val), ("prueba", test)):
    for m, fn in baselines.TODAS.items():
        ds[m] = fn(ds)
    ds["P3"] = ranker.puntuar(modelo, ds, features.COLUMNAS_MODELO)

# ---------------------------------------------------------------- 1. en MAYO
log("midiendo por tramo de historia sobre MAYO")
val["tramo"] = pd.cut(val.n_skus_cliente, bins=[-1, 4, 9, 14, 19, 29, 44, 10**6],
                      labels=["0-4", "5-9", "10-14", "15-19", "20-29", "30-44", "45+"])
tabla_val = []
for tramo, g in val.groupby("tramo", observed=True):
    fila = {"tramo": str(tramo), "clientes": int(g.cliente_id.nunique())}
    for m in MODELOS:
        fila[m] = round(metricas.hit_rate_at_n(g, m, N), 2)
    fila["mejor"] = max(MODELOS, key=lambda m: fila[m])
    tabla_val.append(fila)

# ------------------------------------------------ 2. barrido del umbral en MAYO
log("barriendo umbrales sobre MAYO")
def hibrido(ds: pd.DataFrame, corte: int, bajo: str, alto: str) -> pd.Series:
    """Cada cliente usa UN solo modelo, así que no hace falta que las
    puntuaciones sean comparables entre modelos: el orden es intra-cliente."""
    return np.where(ds.n_skus_cliente < corte, ds[bajo], ds[alto])

barrido = []
for corte in CORTES:
    for bajo in ["B1", "P1", "P2"]:
        val["P4"] = hibrido(val, corte, bajo, "P3")
        barrido.append({"corte": corte, "bajo": bajo,
                        "hit_rate_val": round(metricas.hit_rate_at_n(val, "P4", N), 3)})
mejor = max(barrido, key=lambda r: r["hit_rate_val"])
base_val = round(metricas.hit_rate_at_n(val, "P3", N), 3)
log(f"   mejor en validación: corte={mejor['corte']} bajo={mejor['bajo']} "
    f"-> {mejor['hit_rate_val']}% (P3 solo: {base_val}%)")

# -------------------------------------------------- 3. aplicar A CIEGAS en JULIO
log("aplicando el umbral elegido sobre JULIO")
test["P4"] = hibrido(test, mejor["corte"], mejor["bajo"], "P3")
precio = (df.groupby("sku", observed=True)
            .apply(lambda g: g.importe_preventa.sum() / max(g.piezas_preventa.sum(), 1),
                   include_groups=False))
compras_mes = float(df[df.anio_mes == datos.MES_TEST]
                    .groupby("cliente_id", observed=True).fecha.nunique().mean())

OUT = {"corte_elegido": mejor, "hit_rate_val_p3": base_val,
       "barrido_validacion": barrido, "por_tramo_validacion": tabla_val,
       "prueba": {}}
for pol, kw in (("libre", {}), ("mixta", {"politica": "mixta"})):
    b = {}
    for m in MODELOS + ["P4"]:
        orden = metricas._ordenado(test, m)
        kwo = kw | {"orden": orden}
        sel = metricas.seleccionar(test, m, N, **kwo)
        b[m] = {"hit_rate": round(float(sel.groupby("cliente_id", observed=True)
                                        .y.max().mean() * 100), 2),
                "desglose": sel[sel.y == 1].origen.value_counts().to_dict(),
                "negocio": negocio.resumen(test, m, N, precio, compras_mes, **kwo)}
        log(f"   {pol} {m}: {b[m]['hit_rate']}%")
    OUT["prueba"][pol] = b

json.dump(OUT, open(RESULTADOS / "p4.json", "w"), indent=2, ensure_ascii=False)

print("\n" + "=" * 76)
print("QUÉ MODELO GANA EN CADA TRAMO (validación = mayo)")
print(f"{'tramo':<8} {'clientes':>9} " + " ".join(f"{m:>7}" for m in MODELOS) + "   mejor")
for f in tabla_val:
    print(f"{f['tramo']:<8} {f['clientes']:>9,} " +
          " ".join(f"{f[m]:>6.1f}%" for m in MODELOS) + f"   {f['mejor']}")
print(f"\nUMBRAL ELEGIDO EN VALIDACIÓN: n_skus_cliente < {mejor['corte']} -> {mejor['bajo']}, "
      f"resto -> P3")
print("\n" + "=" * 76)
print("RESULTADO SOBRE JULIO (el umbral se aplicó a ciegas)")
for pol in ("libre", "mixta"):
    print(f"\n  {pol.upper()}")
    b = OUT["prueba"][pol]
    for m in MODELOS + ["P4"]:
        g = b[m]["desglose"]; n = b[m]["negocio"]
        dif = b[m]["hit_rate"] - b["B1"]["hit_rate"]
        print(f"    {m:<4} {b[m]['hit_rate']:>6.2f}%  vs B1 {dif:>+6.2f}  "
              f"dormido {g.get('dormido',0):>6,} nunca {g.get('nunca',0):>6,}  "
              f"desc {n['pct_descubrimiento']:>5.1f}%")
