"""
EDA del lado de PRODUCTO — dbventas / tblVentas.

La pregunta que manda: ¿la ZONA explica qué compra un cliente? El modelo actual
recomienda "lo que compran clientes parecidos de la misma zona", así que conviene
medir cuánto aporta realmente la zona antes de proponer algo más sofisticado.

Grano: canasta = (cliente_id, fecha) sobre líneas con piezas > 0.
"""
import json
import numpy as np
import pandas as pd
from comun import DERIVADO, RESULTADOS

OUT = {}
df = pd.read_parquet(DERIVADO / "ventas.parquet")
df["anio_mes"] = df["anio_mes"].astype(str)
if "es_pack" not in df.columns:
    df["es_pack"] = df["sku"].fillna("").str.upper().str.startswith("PP")
# Los SKU PP* son registros de mecánica promocional (importe 0.00 en el 100% de sus
# líneas), no mercancía. Se excluyen: si no, dominan la afinidad y el conteo de catálogo.
PACKS = df[df.es_pack].sku.nunique()
c = df[df.es_compra & ~df.es_pack].copy()
MESES = sorted(df.anio_mes.unique())

# ---------------------------------------------------------- 0. dimensión limpia
dim = pd.read_parquet(DERIVADO / "dim_sku.parquet")
# descripcion varía solo por acentos corruptos; nos quedamos con la más frecuente
desc = (dim.groupby(["sku", "descripcion"]).size().rename("n").reset_index()
          .sort_values("n", ascending=False).drop_duplicates("sku")[["sku", "descripcion"]])
marca = dim.drop_duplicates("sku")[["sku", "marca"]]
DIM = marca.merge(desc, on="sku")
DIM = DIM[~DIM.sku.str.upper().str.startswith("PP")]
DIM["es_exhibidor"] = DIM.descripcion.str.contains(
    "EXHIBIDOR|MUEBLE|RACK|LLENADO", case=False, na=False)
NOM = dict(zip(DIM.sku, DIM.descripcion))
MRC = dict(zip(DIM.sku, DIM.marca))
corruptas = int(DIM.descripcion.str.contains("209;|PINA|A209", regex=True, na=False).sum())

# ------------------------------------------- 1. ¿LA ZONA EXPLICA EL SURTIDO?
# Para cada cliente comparamos su canasta histórica contra el top-N de su ruta
# y contra el top-N global. Se excluye al propio cliente del cálculo de su ruta
# (leave-one-out), si no el test se auto-cumple.
pares = c[["cliente_id", "sku", "ruta_preventa"]].drop_duplicates()
ruta_cli = (c.groupby("cliente_id", observed=True).ruta_preventa
              .agg(lambda s: s.value_counts().index[0]))          # ruta dominante
cedis_cli = (c.groupby("cliente_id", observed=True).cedis
               .agg(lambda s: s.value_counts().index[0]))
pares = pares.drop(columns="ruta_preventa").merge(
    ruta_cli.rename("ruta").reset_index(), on="cliente_id").merge(
    cedis_cli.rename("cedis").reset_index(), on="cliente_id")

glob = pares.groupby("sku", observed=True).cliente_id.nunique()
ruta_sku = pares.groupby(["ruta", "sku"], observed=True).cliente_id.nunique()
tam_ruta = pares.groupby("ruta", observed=True).cliente_id.nunique()
ced_sku = pares.groupby(["cedis", "sku"], observed=True).cliente_id.nunique()

def recall_topN(N):
    """Cobertura del surtido histórico del cliente por el top-N de su ruta,
    de su CEDIS y global. Leave-one-out: se descuenta al propio cliente."""
    top_glob = set(glob.nlargest(N).index)
    res_r, res_c, res_g = [], [], []
    for ruta, sub in pares.groupby("ruta", observed=True):
        if tam_ruta[ruta] < 30:
            continue
        rs = ruta_sku.loc[ruta]
        for cli, g in sub.groupby("cliente_id", observed=True):
            skus = list(set(g.sku))
            loo = rs.copy()
            loo.loc[skus] = loo.loc[skus] - 1
            res_r.append(len(set(skus) & set(loo.nlargest(N).index)) / len(skus))
            cs = ced_sku.loc[g.cedis.iloc[0]].copy()
            cs.loc[skus] = cs.loc[skus] - 1
            res_c.append(len(set(skus) & set(cs.nlargest(N).index)) / len(skus))
            res_g.append(len(set(skus) & top_glob) / len(skus))
    return (float(np.mean(res_r)) * 100, float(np.mean(res_c)) * 100,
            float(np.mean(res_g)) * 100)

zona = []
for N in (20, 50, 100):
    r, cd, g = recall_topN(N)
    zona.append({"N": N, "recall_ruta": round(r, 1), "recall_cedis": round(cd, 1),
                 "recall_global": round(g, 1), "ganancia_pp": round(r - g, 1),
                 "ruta_sobre_cedis_pp": round(r - cd, 1)})
OUT["zona_vs_global"] = zona

# Jaccard del top-30 entre rutas: dentro del mismo CEDIS vs entre CEDIS
cedis_ruta = c.groupby("ruta_preventa", observed=True).cedis.agg(
    lambda s: s.value_counts().index[0])
top30 = {r: set(ruta_sku.loc[r].nlargest(30).index)
         for r in tam_ruta[tam_ruta >= 30].index}
rr = sorted(top30)
dentro, entre = [], []
for i in range(len(rr)):
    for j in range(i + 1, len(rr)):
        a, b = top30[rr[i]], top30[rr[j]]
        jac = len(a & b) / len(a | b)
        mismo = cedis_ruta.get(rr[i]) == cedis_ruta.get(rr[j])
        (dentro if mismo else entre).append(jac)
OUT["jaccard_rutas"] = {
    "rutas_comparadas": len(rr),
    "mismo_cedis": round(float(np.mean(dentro)) , 3) if dentro else None,
    "distinto_cedis": round(float(np.mean(entre)), 3) if entre else None,
}

# ------------------------------------------------- 2. afinidad entre productos
c["canasta"] = c.cliente_id.astype(str) + "|" + c.fecha.dt.strftime("%Y%m%d")
b = c[["canasta", "sku"]].drop_duplicates()
n_canastas = b.canasta.nunique()
sop = b.groupby("sku", observed=True).canasta.nunique()           # soporte individual
pair = b.merge(b, on="canasta")
pair = pair[pair.sku_x < pair.sku_y]
co = pair.groupby(["sku_x", "sku_y"], observed=True).canasta.nunique().rename("co").reset_index()
co = co[co.co >= 100].copy()                                       # piso de soporte
co["lift"] = (co.co / n_canastas) / ((sop[co.sku_x].values / n_canastas) *
                                      (sop[co.sku_y].values / n_canastas))
co["conf_xy"] = co.co / sop[co.sku_x].values
top_lift = co.nlargest(10, "lift")
top_co = co.nlargest(12, "co")
OUT["afinidad"] = {
    "canastas": int(n_canastas),
    "pares_con_soporte_100": int(len(co)),
    "top": [{"a": NOM.get(r.sku_x, r.sku_x)[:40], "b": NOM.get(r.sku_y, r.sku_y)[:40],
             "marca_a": MRC.get(r.sku_x, ""), "marca_b": MRC.get(r.sku_y, ""),
             "co": int(r.co), "lift": round(float(r.lift), 1),
             "conf": round(float(r.conf_xy) * 100, 1)}
            for r in top_lift.itertuples()],
    "top_frecuencia": [{"a": NOM.get(r.sku_x, r.sku_x)[:38], "b": NOM.get(r.sku_y, r.sku_y)[:38],
                        "marca_a": MRC.get(r.sku_x, ""), "marca_b": MRC.get(r.sku_y, ""),
                        "co": int(r.co), "lift": round(float(r.lift), 1),
                        "conf": round(float(r.conf_xy) * 100, 1)}
                       for r in top_co.itertuples()],
    "misma_marca_pct": round(float((co.assign(
        m=[MRC.get(x) == MRC.get(y) for x, y in zip(co.sku_x, co.sku_y)]).m).mean() * 100), 1),
}

# ------------------------------------------------------- 3. recompra por SKU
ms = c.groupby(["cliente_id", "sku"], observed=True).anio_mes.nunique().rename("meses").reset_index()
ret = ms.groupby("sku", observed=True).agg(
    compradores=("cliente_id", "size"),
    pct_core=("meses", lambda s: (s >= 3).mean() * 100)).reset_index()
# Un SKU que solo existió 2 meses NO PUEDE tener compradores de >=3 meses: comparar
# recompra sin controlar disponibilidad confunde "no lo recompran" con "no estuvo".
meses_disp = c.groupby("sku", observed=True).anio_mes.nunique()
ret["meses_disp"] = ret.sku.map(meses_disp)
EXH = set(DIM[DIM.es_exhibidor].sku)
ret = ret[(ret.compradores >= 200) & (ret.meses_disp == 12) & (~ret.sku.isin(EXH))]
ret["marca"] = ret.sku.map(MRC); ret["nombre"] = ret.sku.map(NOM)
OUT["recompra_sku"] = {
    "evaluados": int(len(ret)),
    "nota": "solo SKUs con >=200 compradores Y disponibles los 12 meses",
    "mediana_pct_core": round(float(ret.pct_core.median()), 1),
    "basicos": [{"n": r.nombre[:42], "m": r.marca, "cli": int(r.compradores),
                 "core": round(float(r.pct_core), 1)}
                for r in ret.nlargest(8, "pct_core").itertuples()],
    "prueba": [{"n": r.nombre[:42], "m": r.marca, "cli": int(r.compradores),
                "core": round(float(r.pct_core), 1)}
               for r in ret.nsmallest(8, "pct_core").itertuples()],
}

# --------------------------------------------------- 4. ciclo de vida catálogo
vida = c.groupby("sku", observed=True).anio_mes.agg(["min", "max", "nunique"])
ultimos2 = set(MESES[-2:])
activos = c[c.anio_mes.isin(ultimos2)].sku.unique()
OUT["ciclo_vida"] = {
    "skus_total": int(c.sku.nunique()),
    "activos_ult2m": int(len(activos)),
    "descontinuados": int(c.sku.nunique() - len(activos)),
    "nacen_por_mes": {str(k): int(v) for k, v in vida["min"].value_counts().sort_index().items()},
    "mueren_por_mes": {str(k): int(v) for k, v in
                       vida[vida["max"] < MESES[-2]]["max"].value_counts().sort_index().items()},
    "vendidos_12m": int((vida["nunique"] == 12).sum()),
}

# ------------------------------------------------ 5. penetración y concentración
buyers = c.groupby("sku", observed=True).cliente_id.nunique().sort_values(ascending=False)
imp = c.groupby("sku", observed=True).importe_preventa.sum().sort_values(ascending=False)
n_cli = c.cliente_id.nunique()
cum = imp.cumsum() / imp.sum()
OUT["concentracion"] = {
    "clientes": int(n_cli),
    "penetracion_mediana_pct": round(float(buyers.median() / n_cli * 100), 2),
    "skus_50pct": int((cum <= .5).sum() + 1), "skus_80pct": int((cum <= .8).sum() + 1),
    "skus_95pct": int((cum <= .95).sum() + 1),
    "pareto": [{"n": int(k), "pct": round(float(cum.iloc[k - 1] * 100), 1)}
               for k in (10, 25, 50, 100, 156, 300, 500)],
    "top_penetracion": [{"n": NOM.get(s, s)[:42], "m": MRC.get(s, ""),
                         "pct": round(float(v / n_cli * 100), 1)}
                        for s, v in buyers.head(8).items()],
}
mk = c.groupby("marca", observed=True).agg(
    imp=("importe_preventa", "sum"), cli=("cliente_id", "nunique"),
    skus=("sku", "nunique")).sort_values("imp", ascending=False)
OUT["marcas"] = [{"marca": m, "imp_pct": round(float(r.imp / imp.sum() * 100), 1),
                  "penetracion": round(float(r.cli / n_cli * 100), 1), "skus": int(r.skus)}
                 for m, r in mk.head(12).iterrows()]

# ------------------------------------------------------------ 6. rechazo por SKU
rz = df[df.piezas_rechazo > 0]
r_sku = rz.groupby("sku", observed=True).agg(
    lineas=("sku", "size"), piezas=("piezas_rechazo", "sum")).sort_values("piezas", ascending=False)
tot_ped = c.groupby("sku", observed=True).piezas_preventa.sum()
r_sku["tasa"] = (r_sku.piezas / tot_ped.reindex(r_sku.index)).fillna(0) * 100
OUT["rechazo"] = {
    "piezas_total": int(df.piezas_rechazo.sum()),
    "clientes_afectados": int(rz.cliente_id.nunique()),
    "skus_afectados": int(len(r_sku)),
    "top10_concentra_pct": round(float(r_sku.piezas.head(10).sum() / r_sku.piezas.sum() * 100), 1),
    "top": [{"n": NOM.get(s, s)[:42], "m": MRC.get(s, ""), "piezas": int(r.piezas),
             "tasa": round(float(r.tasa), 1)} for s, r in r_sku.head(8).iterrows()],
}
OUT["calidad_dim"] = {"descripciones_corruptas": corruptas, "skus_mercancia": int(len(DIM)),
                      "skus_promocion": int(PACKS),
                      "lineas_promocion": int(df.es_pack.sum()),
                      "pct_lineas_promocion": round(float(df[df.es_compra].es_pack.mean() * 100), 1)}

# Dimensión enriquecida: lo que el recomendador necesitará para no sugerir basura
dimfull = pd.read_parquet(DERIVADO / "dim_sku.parquet").drop_duplicates("sku")[["sku", "marca"]]
dimfull = dimfull.merge(desc, on="sku", how="left")
dimfull["es_pack"] = dimfull.sku.str.upper().str.startswith("PP")
dimfull["es_exhibidor"] = dimfull.descripcion.str.contains(
    "EXHIBIDOR|MUEBLE|RACK|LLENADO", case=False, na=False)
dimfull["activo_ult2m"] = dimfull.sku.isin(activos)
dimfull["recomendable"] = ~dimfull.es_pack & ~dimfull.es_exhibidor & dimfull.activo_ult2m
dimfull.to_parquet(DERIVADO / "dim_sku_flags.parquet", index=False)
OUT["recomendables"] = int(dimfull.recomendable.sum())
OUT["exhibidores"] = int(dimfull.es_exhibidor.sum())

json.dump(OUT, open(RESULTADOS / "eda_productos.json", "w"), indent=2, ensure_ascii=False)

# ---------------------------------------------------------------------- resumen
print(f"=== CATÁLOGO REAL: {len(DIM)} productos (excluidos {PACKS} SKUs de promoción con importe 0)")
print("=== ¿LA ZONA EXPLICA EL SURTIDO? (recall de la canasta del cliente) ===")
for z in zona:
    print(f"  top-{z['N']:<4} ruta {z['recall_ruta']:>5}%  CEDIS {z['recall_cedis']:>5}%  "
          f"global {z['recall_global']:>5}%   |  ruta sobre CEDIS: {z['ruta_sobre_cedis_pp']:+.1f} pp")
j = OUT["jaccard_rutas"]
print(f"  Jaccard top-30 entre rutas: mismo CEDIS {j['mismo_cedis']}  |  distinto {j['distinto_cedis']}")
a = OUT["afinidad"]
print(f"\n=== AFINIDAD ({a['canastas']:,} canastas, {a['pares_con_soporte_100']:,} pares con soporte>=100) ===")
print(f"  pares de la MISMA marca: {a['misma_marca_pct']}%")
for p in a["top"][:5]:
    print(f"  lift {p['lift']:>5}  {p['a'][:32]:<32} + {p['b'][:32]:<32} (n={p['co']:,})")
r = OUT["recompra_sku"]
print(f"\n=== RECOMPRA POR SKU (mediana {r['mediana_pct_core']}% de compradores lo vuelven básico) ===")
print("  BÁSICOS:"); [print(f"    {x['core']:>5}%  {x['n'][:40]:<40} {x['m']}") for x in r["basicos"][:4]]
print("  DE PRUEBA:"); [print(f"    {x['core']:>5}%  {x['n'][:40]:<40} {x['m']}") for x in r["prueba"][:4]]
v = OUT["ciclo_vida"]
print(f"\n=== CATÁLOGO: {v['skus_total']} SKUs, {v['activos_ult2m']} activos, "
      f"{v['descontinuados']} sin venta en los últimos 2 meses ({v['vendidos_12m']} vendidos los 12 meses)")
cc = OUT["concentracion"]
print(f"\n=== CONCENTRACIÓN: {cc['skus_50pct']} SKUs = 50% del importe | {cc['skus_80pct']} = 80% | {cc['skus_95pct']} = 95%")
print(f"  penetración mediana de un SKU: {cc['penetracion_mediana_pct']}% de los clientes")
rr_ = OUT["rechazo"]
print(f"\n=== RECOMENDABLES: {OUT['recomendables']} de {len(dimfull)} SKUs "
      f"(se excluyen {int(dimfull.es_pack.sum())} packs, {OUT['exhibidores']} exhibidores, "
      f"{int((~dimfull.activo_ult2m & ~dimfull.es_pack).sum())} sin venta reciente)")
print("\nAFINIDAD por FRECUENCIA (lo que de verdad va junto):")
for x in OUT["afinidad"]["top_frecuencia"][:6]:
    print(f"  {x['co']:>6,} canastas  lift {x['lift']:>6}  {x['a'][:34]:<34} + {x['b'][:34]}")
print(f"\n=== RECHAZO: {rr_['piezas_total']:,} piezas, top-10 SKUs concentra {rr_['top10_concentra_pct']}%")
