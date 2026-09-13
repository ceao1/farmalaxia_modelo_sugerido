"""
¿Cuánto cambia el resultado según cuántas sugerencias se emitan?

Calcula el desempeño de B1 (popularidad de ruta = modelo actual reconstruido)
para distintos N sobre jul-2026. Sirve para dos cosas:
  - saber la vara real antes de construir nada
  - responder si "8 por visita" vs "8 por periodo" cambia las conclusiones
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

c = df[df.es_compra & ~df.es_pack]
hist, test = c[c.anio_mes < TEST], c[c.anio_mes == TEST]

ruta_cli = (hist.groupby("cliente_id", observed=True).ruta_preventa
              .agg(lambda s: s.value_counts().index[0]))
hist_sku = hist.groupby("cliente_id", observed=True).sku.apply(set)
pares = hist[["cliente_id", "sku"]].drop_duplicates().merge(
    ruta_cli.rename("ruta").reset_index(), on="cliente_id")
ruta_pop = pares.groupby(["ruta", "sku"], observed=True).cliente_id.nunique()
TOPR = {r: [s for s in g.sort_values(ascending=False).index.get_level_values("sku") if s in RECOM]
        for r, g in ruta_pop.groupby(level=0)}

# precio medio por SKU, para traducir a pesos
precio = c.groupby("sku", observed=True).apply(
    lambda g: g.importe_preventa.sum() / max(g.piezas_preventa.sum(), 1), include_groups=False)

NS = [3, 5, 8, 16, 24, 40]
acc = {n: {"hit": 0, "aciertos": 0, "imp": 0.0} for n in NS}
clientes = 0
nuevos_tot = 0
for cli, g in test.groupby("cliente_id", observed=True):
    if cli not in hist_sku.index: continue
    h = hist_sku[cli]
    nuevos = {s for s in set(g.sku) if s not in h and s in RECOM}
    if not nuevos: continue
    clientes += 1; nuevos_tot += len(nuevos)
    lista = [s for s in TOPR.get(ruta_cli.get(cli), []) if s not in h]
    for n in NS:
        top = set(lista[:n])
        ac = nuevos & top
        if ac: acc[n]["hit"] += 1
        acc[n]["aciertos"] += len(ac)
        acc[n]["imp"] += float(sum(precio.get(s, 0) for s in ac))

compras_mes = test.groupby("cliente_id", observed=True).fecha.nunique().mean()
print(f"B1 (popularidad de ruta) sobre {TEST} — {clientes:,} clientes con alguna compra nueva")
print(f"Productos nuevos que realmente compraron: {nuevos_tot:,} "
      f"({nuevos_tot/clientes:.2f} por cliente)\n")
print(f"{'N':>4} {'hit-rate':>10} {'aciertos/cliente':>18} {'SKU extra/compra':>18} {'precisión':>11}")
OUT = {}
for n in NS:
    a = acc[n]
    hr = a["hit"]/clientes*100
    ac_cli = a["aciertos"]/clientes
    OUT[n] = {"hit_rate": round(hr,1), "aciertos_por_cliente": round(ac_cli,3),
              "sku_extra_por_compra": round(ac_cli/compras_mes,3),
              "precision": round(a["aciertos"]/(clientes*n)*100,2)}
    print(f"{n:>4} {hr:>9.1f}% {ac_cli:>18.3f} {ac_cli/compras_mes:>18.3f} {a['aciertos']/(clientes*n)*100:>10.2f}%")
print(f"\n  (compras por cliente en el mes: {compras_mes:.2f})")
print(f"\nDe 8 a 40 sugerencias: hit-rate {OUT[8]['hit_rate']}% -> {OUT[40]['hit_rate']}%  "
      f"(x{OUT[40]['hit_rate']/OUT[8]['hit_rate']:.2f}), pero precisión "
      f"{OUT[8]['precision']}% -> {OUT[40]['precision']}%")
json.dump({str(k): v for k, v in OUT.items()} | {"compras_mes": round(float(compras_mes),2)},
          open(RESULTADOS / "diag_n_sugerencias.json","w"), indent=2, ensure_ascii=False)
