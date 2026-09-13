"""Ejecuta el POC completo y guarda los resultados.

Uso:  ./.venv/bin/python src/10_ejecutar_poc.py
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

N_TITULAR = 8
UMBRAL_B1 = 47.0          # hit-rate@8 de B1 en política libre, medido antes
MARGEN_EXIGIDO = 5.0
CLIENTES_ENTRENAMIENTO = 8000
MESES_ENTRENAMIENTO = 3
POLITICAS = {"libre": {}, "mixta": {"politica": "mixta", "cuotas": metricas.CUOTAS_MIXTA}}
MODELOS = ["B0", "B1", "P1", "P2", "P3"]

t0 = time.time()
def log(m): print(f"[{time.time()-t0:6.0f}s] {m}", flush=True)

log("cargando datos")
df = datos.cargar_compras()
base_recom = datos.recomendables_base()
dim = pd.read_parquet(DERIVADO / "dim_sku_flags.parquet")[["sku", "marca"]]
rng = np.random.default_rng(datos.SEMILLA)

# Las 24 rutas que abren en jun-2026 tienen <=3 meses de historia: su B1 es
# inestable, así que se reportan aparte en vez de contaminar el promedio.
RUTAS_ESTABLES = set(df.loc[df.anio_mes == datos.MESES_TRAIN[0], "ruta_preventa"].dropna())


def preparar(mes: str, submuestrear: bool) -> pd.DataFrame:
    """Conjunto de un mes con todas las variables, sin fuga."""
    hist = datos.historia_hasta(df, mes)
    clientes = None
    if submuestrear:
        todos = sorted(set(df.loc[df.anio_mes == mes, "cliente_id"]))
        if len(todos) > CLIENTES_ENTRENAMIENTO:
            clientes = set(rng.choice(todos, CLIENTES_ENTRENAMIENTO, replace=False))
    recom = datos.recomendables_al_mes(df, mes, base_recom)
    ds = candidatos.construir(df, mes, recom, clientes)
    if ds.empty:
        return ds
    afin = features.matriz_afinidad(hist)
    ds = features.agregar_ruta(ds, hist)
    ds = features.agregar_marca(ds, hist, dim)
    ds = features.agregar_afinidad(ds, hist, afin)
    ds = features.agregar_cliente(ds, hist)
    ds = features.agregar_producto(ds, hist)
    ds = features.agregar_origen(ds)
    for c in features.COLUMNAS_MODELO:
        ds[c] = ds[c].astype("float32")
    ds["cliente_id"] = ds.cliente_id.astype("category")
    log(f"   {mes}: {len(ds):,} filas, {ds.cliente_id.nunique():,} clientes")
    return ds


log("construyendo entrenamiento")
train = pd.concat([preparar(m, True) for m in datos.MESES_TRAIN[-MESES_ENTRENAMIENTO:]],
                  ignore_index=True)
log(f"entrenamiento: {len(train):,} filas")

log("construyendo validación")
val = preparar(datos.MES_VAL, True)
log("construyendo prueba (todos los clientes)")
test = preparar(datos.MES_TEST, False)

log("puntuando líneas base")
for nombre, fn in baselines.TODAS.items():
    test[nombre] = fn(test)

log("entrenando el ranker")
modelo = ranker.entrenar(train, val, features.COLUMNAS_MODELO, datos.SEMILLA)
test = ranker.ordenar(test)
test["P3"] = ranker.puntuar(modelo, test, features.COLUMNAS_MODELO)
imp = ranker.importancias(modelo, features.COLUMNAS_MODELO)
log(f"   {modelo.num_trees()} árboles | mejor iteración {modelo.best_iteration}")

log("evaluando")
precio = (df.groupby("sku", observed=True)
            .apply(lambda g: g.importe_preventa.sum() / max(g.piezas_preventa.sum(), 1),
                   include_groups=False))
compras_mes = float(df[df.anio_mes == datos.MES_TEST]
                    .groupby("cliente_id", observed=True).fecha.nunique().mean())

OUT = {
    "mes_prueba": datos.MES_TEST,
    "clientes_evaluados": int(test.cliente_id.nunique()),
    "candidatos_por_cliente": int(round(len(test) / test.cliente_id.nunique())),
    "compras_por_cliente_mes": round(compras_mes, 2),
    "positivos_pct": round(float(test.y.mean() * 100), 3),
    "importancias": imp.to_dict("records"),
    "politicas": {},
}

for pol, kw in POLITICAS.items():
    log(f"   política {pol}")
    bloque = {"hit_rate_8": {}, "intervalo_95": {}, "curvas": {}, "negocio": {}, "desglose": {}}
    for m in MODELOS:
        # ordenar diez millones de filas cuesta segundos: se hace UNA vez por
        # modelo y política, y se reutiliza en todas las métricas.
        orden = metricas._ordenado(test, m)
        kwo = kw | {"orden": orden}
        sel8 = metricas.seleccionar(test, m, N_TITULAR, **kwo)
        bloque["hit_rate_8"][m] = round(
            float(sel8.groupby("cliente_id", observed=True).y.max().mean() * 100), 2)
        lo, hi = metricas.bootstrap_ic(test, m, N_TITULAR, **kwo)
        bloque["intervalo_95"][m] = [round(lo, 2), round(hi, 2)]
        bloque["curvas"][m] = metricas.curva(test, m, **kwo).to_dict("records")
        bloque["desglose"][m] = sel8[sel8.y == 1].origen.value_counts().to_dict()
        bloque["negocio"][m] = negocio.resumen(test, m, N_TITULAR, precio, compras_mes, **kwo)
        log(f"      {m}: {bloque['hit_rate_8'][m]:.2f}%")
    mejor = max(MODELOS[2:], key=lambda m: bloque["hit_rate_8"][m])   # entre P1, P2, P3
    b1 = bloque["hit_rate_8"]["B1"]
    bloque["veredicto"] = {
        "mejor_propuesta": mejor,
        "b1": b1,
        "objetivo": round(b1 + MARGEN_EXIGIDO, 2),
        "logrado": bool(bloque["hit_rate_8"][mejor] >= b1 + MARGEN_EXIGIDO),
        "diferencia_pp": round(bloque["hit_rate_8"][mejor] - b1, 2),
    }
    imp_mes = bloque["negocio"][mejor]["importe_por_cliente"]
    bloque["escenarios"] = negocio.tabla_escenarios(
        imp_mes, int(test.cliente_id.nunique())).to_dict("records")
    OUT["politicas"][pol] = bloque

log("desglose por antigüedad de ruta")
ruta_test = datos.ruta_dominante(datos.historia_hasta(df, datos.MES_TEST))
test["ruta_estable"] = test.cliente_id.astype(str).map(ruta_test).isin(RUTAS_ESTABLES)
por_ruta = {}
for etiqueta, sub in (("estables", test[test.ruta_estable]),
                      ("nuevas_jun2026", test[~test.ruta_estable])):
    if sub.cliente_id.nunique() < 100:
        continue
    por_ruta[etiqueta] = {"clientes": int(sub.cliente_id.nunique()),
                          **{m: round(metricas.hit_rate_at_n(sub, m, N_TITULAR), 2)
                             for m in MODELOS}}
OUT["hit_rate_8_por_antiguedad_de_ruta"] = por_ruta

json.dump(OUT, open(RESULTADOS / "poc.json", "w"), indent=2, ensure_ascii=False)

print("\n" + "=" * 72)
for pol in POLITICAS:
    b = OUT["politicas"][pol]
    print(f"\nPOLÍTICA {pol.upper()}")
    for m in MODELOS:
        lo, hi = b["intervalo_95"][m]
        d = b["desglose"][m]
        print(f"  {m}: hit-rate@8 = {b['hit_rate_8'][m]:>5.2f}%  IC95 [{lo:.2f}, {hi:.2f}]  "
              f"dormido {d.get('dormido',0):>6,} / nunca {d.get('nunca',0):>6,}")
    v = b["veredicto"]
    print(f"  -> mejor {v['mejor_propuesta']} contra B1 {v['b1']}%: "
          f"{v['diferencia_pp']:+.2f} pp | objetivo {v['objetivo']}% | "
          f"{'LOGRADO' if v['logrado'] else 'NO LOGRADO'}")
print("\nIMPORTANCIA DE VARIABLES")
for r in OUT["importancias"][:8]:
    print(f"  {r['variable']:<20} {r['pct']:>5.1f}%")
print(f"\nresultados en {RESULTADOS / 'poc.json'}")
