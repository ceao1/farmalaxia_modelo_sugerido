"""
¿Cuánto gana el sistema si los candidatos NO se limitan al top-100 de la ruta?

Mide, sobre jul-2026, qué fracción de las compras NUEVAS de cada cliente
alcanza cada fuente de candidatos. Ese techo es el máximo que el modelo
podría acertar: lo que no entra en la lista de candidatos es inalcanzable.
"""
import json
import numpy as np
import pandas as pd
from comun import DERIVADO, RESULTADOS

TEST = "2026-07"
df = pd.read_parquet(DERIVADO / "ventas.parquet"); df["anio_mes"] = df["anio_mes"].astype(str)
if "es_pack" not in df.columns:
    df["es_pack"] = df.sku.fillna("").str.upper().str.startswith("PP")
flags = pd.read_parquet(DERIVADO / "dim_sku_flags.parquet")
RECOM = set(flags[flags.recomendable].sku)
MRC = dict(zip(flags.sku, flags.marca))

c = df[df.es_compra & ~df.es_pack]
hist = c[c.anio_mes < TEST]
test = c[c.anio_mes == TEST]

ruta_cli = (hist.groupby("cliente_id", observed=True).ruta_preventa
              .agg(lambda s: s.value_counts().index[0]))
hist_sku   = hist.groupby("cliente_id", observed=True).sku.apply(set)
hist_marca = hist.groupby("cliente_id", observed=True).marca.apply(lambda s: set(s.dropna()))

pares = hist[["cliente_id", "sku"]].drop_duplicates().merge(
    ruta_cli.rename("ruta").reset_index(), on="cliente_id")
ruta_pop = pares.groupby(["ruta", "sku"], observed=True).cliente_id.nunique()
glob_pop = pares.groupby("sku", observed=True).cliente_id.nunique()
GLOB = [s for s in glob_pop.sort_values(ascending=False).index if s in RECOM]

# popularidad por marca (para la fuente "marca que ya compra")
marca_pop = (hist[["cliente_id", "sku", "marca"]].dropna(subset=["marca"]).drop_duplicates()
             .groupby(["marca", "sku"], observed=True).cliente_id.nunique())
MARCA_TOP = {m: [s for s in g.sort_values(ascending=False).index.get_level_values("sku") if s in RECOM][:40]
             for m, g in marca_pop.groupby(level=0)}

# ítem-ítem: vecinos por co-ocurrencia
cc = hist.copy(); cc["canasta"] = cc.cliente_id.astype(str) + "|" + cc.fecha.dt.strftime("%Y%m%d")
b = cc[["canasta", "sku"]].drop_duplicates()
pair = b.merge(b, on="canasta"); pair = pair[pair.sku_x != pair.sku_y]
co = pair.groupby(["sku_x", "sku_y"], observed=True).canasta.nunique()
co = co[co >= 50]
VEC = {x: [s for s in g.sort_values(ascending=False).index.get_level_values("sku_y") if s in RECOM][:15]
       for x, g in co.groupby(level=0)}

TOPR = {r: [s for s in g.sort_values(ascending=False).index.get_level_values("sku") if s in RECOM]
        for r, g in ruta_pop.groupby(level=0)}

def cand(cli, modo):
    h = hist_sku.get(cli, set()); r = ruta_cli.get(cli)
    tr = TOPR.get(r, [])
    if modo == "ruta100":
        return [s for s in tr if s not in h][:100]
    if modo == "ruta300":
        return [s for s in tr if s not in h][:300]
    out = [s for s in tr if s not in h][:100]
    vistos = set(out)
    for m in hist_marca.get(cli, set()):                    # marcas que ya compra
        for s in MARCA_TOP.get(m, []):
            if s not in h and s not in vistos: out.append(s); vistos.add(s)
    for s0 in list(h)[:40]:                                  # vecinos de lo que lleva
        for s in VEC.get(s0, []):
            if s not in h and s not in vistos: out.append(s); vistos.add(s)
    for s in GLOB[:50]:
        if s not in h and s not in vistos: out.append(s); vistos.add(s)
    return out

res = {m: {"alcanzados": 0, "total": 0, "tam": []} for m in ("ruta100", "ruta300", "mixto")}
n_cli = 0
for cli, g in test.groupby("cliente_id", observed=True):
    if cli not in hist_sku.index: continue
    nuevos = {s for s in set(g.sku) if s not in hist_sku[cli] and s in RECOM}
    if not nuevos: continue
    n_cli += 1
    for m in res:
        cs = set(cand(cli, m))
        res[m]["alcanzados"] += len(nuevos & cs)
        res[m]["total"] += len(nuevos)
        res[m]["tam"].append(len(cs))

print(f"Clientes evaluados en {TEST}: {n_cli:,}")
print(f"{'fuente':<10} {'techo':>8}  {'candidatos (mediana)':>22}")
OUT = {}
for m, v in res.items():
    techo = v["alcanzados"]/v["total"]*100
    OUT[m] = {"techo_pct": round(techo,1), "cand_mediana": int(np.median(v["tam"]))}
    print(f"{m:<10} {techo:>7.1f}%  {int(np.median(v['tam'])):>22,}")

# valor de los productos nuevos: para traducir a pesos
nuevos_imp = []
for cli, g in test.groupby("cliente_id", observed=True):
    if cli not in hist_sku.index: continue
    gg = g[~g.sku.isin(hist_sku[cli]) & g.sku.isin(RECOM)]
    if len(gg): nuevos_imp.append(gg.importe_preventa.sum())
imp = np.array(nuevos_imp)
comp = test.groupby("cliente_id", observed=True).fecha.nunique()
OUT["valor"] = {
    "importe_medio_productos_nuevos_por_cliente_mes": round(float(imp.mean()), 0),
    "importe_mediano": round(float(np.median(imp)), 0),
    "compras_por_cliente_mes": round(float(comp.mean()), 2),
}
print(f"\nValor de lo NUEVO que ya compran hoy (sin recomendador):")
print(f"  por cliente-mes: media {imp.mean():,.0f}  mediana {np.median(imp):,.0f}")
print(f"  compras por cliente-mes: {comp.mean():.2f}")
json.dump(OUT, open(RESULTADOS / "diag_candidatos.json","w"), indent=2, ensure_ascii=False)
