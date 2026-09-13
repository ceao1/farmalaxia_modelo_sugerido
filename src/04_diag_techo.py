"""
Diagnóstico para el brainstorming de modelos.

A) ¿Cuál es el TECHO del modelo actual? Descomponer la canasta de un mes en
   lo que la popularidad de ruta puede capturar, lo que solo la historia del
   cliente captura, y lo que no captura nada.
B) ¿Hay LOOP de retroalimentación? Si el modelo empuja a todos a lo mismo,
   la concentración debería subir y los clientes parecerse más con el tiempo.
C) ¿Cuánto margen de PERSONALIZACIÓN queda dentro de una misma ruta?
"""
import json
import numpy as np
import pandas as pd
from comun import DERIVADO, RESULTADOS

rng = np.random.default_rng(7)
df = pd.read_parquet(DERIVADO / "ventas.parquet"); df["anio_mes"] = df["anio_mes"].astype(str)
if "es_pack" not in df.columns:
    df["es_pack"] = df.sku.fillna("").str.upper().str.startswith("PP")
c = df[df.es_compra & ~df.es_pack]
MESES = sorted(c.anio_mes.unique())
OUT = {}

ruta_cli = (c.groupby("cliente_id", observed=True).ruta_preventa
              .agg(lambda s: s.value_counts().index[0]).rename("ruta"))

# ---------------------------------------------- A) techo del modelo actual
TEST = MESES[-1]
hist = c[c.anio_mes < TEST]
test = c[c.anio_mes == TEST]

hist_cli = hist.groupby("cliente_id", observed=True).sku.apply(set)
pares_h = hist[["cliente_id", "sku"]].drop_duplicates().merge(ruta_cli.reset_index(), on="cliente_id")
ruta_pop = pares_h.groupby(["ruta", "sku"], observed=True).cliente_id.nunique()
glob_pop = pares_h.groupby("sku", observed=True).cliente_id.nunique()

for N in (20, 50, 100):
    # OJO: groupby(level=0) conserva el MultiIndex -> hay que extraer el nivel "sku"
    top_ruta = {r: set(g.nlargest(N).index.get_level_values("sku"))
                for r, g in ruta_pop.groupby(level=0)}
    top_glob = set(glob_pop.nlargest(N).index)
    en_hist = en_ruta = en_glob = ninguno = total = 0
    solo_ruta = solo_hist = union = 0
    for cli, g in test.groupby("cliente_id", observed=True):
        if cli not in hist_cli.index:
            continue
        h = hist_cli[cli]
        r = top_ruta.get(ruta_cli.get(cli), set())
        for s in set(g.sku):
            total += 1
            in_h, in_r = s in h, s in r
            if in_h: en_hist += 1
            if in_r: en_ruta += 1
            if s in top_glob: en_glob += 1
            if in_r and not in_h: solo_ruta += 1
            if in_h and not in_r: solo_hist += 1
            if in_h or in_r: union += 1
            if not in_h and not in_r: ninguno += 1
    OUT.setdefault("techo", []).append({
        "N": N, "items_test": total,
        "pct_en_historia": round(en_hist / total * 100, 1),
        "pct_en_top_ruta": round(en_ruta / total * 100, 1),
        "pct_en_top_global": round(en_glob / total * 100, 1),
        "pct_solo_ruta_aporta": round(solo_ruta / total * 100, 1),
        "pct_solo_historia_aporta": round(solo_hist / total * 100, 1),
        "pct_union": round(union / total * 100, 1),
        "pct_nadie_captura": round(ninguno / total * 100, 1)})

# ------------------------------------------------- B) ¿hay loop / convergencia?
eq = []
for m in MESES:
    sub = c[c.anio_mes == m]
    imp = sub.groupby("sku", observed=True).importe_preventa.sum().sort_values(ascending=False)
    share50 = imp.head(50).sum() / imp.sum() * 100
    # Gini sobre importe por SKU
    v = np.sort(imp.values); n = len(v)
    gini = (2 * np.sum((np.arange(1, n + 1)) * v) / (n * np.sum(v))) - (n + 1) / n
    eq.append({"mes": m, "share_top50": round(float(share50), 1),
               "gini_sku": round(float(gini), 3),
               "skus_vendidos": int(sub.sku.nunique()),
               "skus_por_cliente": round(float(
                   sub.groupby("cliente_id", observed=True).sku.nunique().mean()), 2)})
OUT["concentracion_mensual"] = eq

# similitud media entre clientes de la MISMA ruta, mes a mes (muestreada)
def jac_intra(mes, n_rutas=25, n_pares=40, solo=None):
    sub = c[c.anio_mes == mes][["cliente_id", "sku"]].drop_duplicates().merge(
        ruta_cli.reset_index(), on="cliente_id")
    vals = []
    rutas = sub.ruta.value_counts()
    rutas = rutas[rutas >= 50].index.tolist()
    if solo is not None:
        rutas = [r for r in rutas if r in solo]
    if not rutas:
        return float("nan"), float("nan")
    for r in rng.choice(rutas, min(n_rutas, len(rutas)), replace=False):
        g = sub[sub.ruta == r].groupby("cliente_id", observed=True).sku.apply(set)
        if len(g) < 6: continue
        idx = g.index.tolist()
        for _ in range(n_pares):
            a, b = rng.choice(len(idx), 2, replace=False)
            A, B = g.iloc[a], g.iloc[b]
            if A and B: vals.append(len(A & B) / len(A | B))
    return float(np.mean(vals)), float(np.std(vals))

# Las 24 rutas que abren en jun-2026 podrían mover la serie; se aíslan.
rutas_ini = set(c[c.anio_mes == MESES[0]].ruta_preventa.dropna().unique())
sim = []
for m in MESES:
    mu, sd = jac_intra(m)
    mu_e, _ = jac_intra(m, solo=rutas_ini)
    sim.append({"mes": m, "jaccard_intra_ruta": round(mu, 4), "sd": round(sd, 4),
                "jaccard_rutas_estables": round(mu_e, 4)})
OUT["similitud_intra_ruta"] = sim

# ------------------------------------------ C) margen de personalización
ult = MESES[-1]
sub = c[c.anio_mes == ult][["cliente_id", "sku"]].drop_duplicates().merge(
    ruta_cli.reset_index(), on="cliente_id")
tam = sub.groupby("cliente_id", observed=True).sku.nunique()
OUT["personalizacion"] = {
    "mes": ult,
    "jaccard_intra_ruta_ult": sim[-1]["jaccard_intra_ruta"],
    "skus_por_cliente_mes": round(float(tam.mean()), 2),
    "interpretacion": "Jaccard bajo entre vecinos = hay señal personal que la ruta no captura",
}

# ------------------------------------- D) ¿la MARCA es una variable útil?
# Para cada cliente-mes: qué fracción de lo que compró es de marcas que ya conocía.
lin = c[["cliente_id", "anio_mes", "sku", "marca"]].dropna(subset=["marca"]).drop_duplicates()
marcas_prev, fid_marca, fid_sku_nuevo = {}, [], []
for m in MESES:
    cur = lin[lin.anio_mes == m]
    for cli, g in cur.groupby("cliente_id", observed=True):
        prev = marcas_prev.get(cli)
        if prev:
            mm = set(g.marca)
            fid_marca.append(len(mm & prev) / len(mm))
            nuevos = g[~g.sku.isin(set())]            # todos los sku del mes
            # de los SKU NUEVOS para el cliente, ¿cuántos son de marca ya conocida?
            fid_sku_nuevo.append((cli, m, prev, set(zip(g.sku, g.marca))))
    for cli, g in cur.groupby("cliente_id", observed=True):
        marcas_prev[cli] = marcas_prev.get(cli, set()) | set(g.marca)

hist_sku = {}
nuevo_marca_conocida, nuevo_total = 0, 0
for cli, m, prev, pares_sm in fid_sku_nuevo:
    hs = hist_sku.get(cli, set())
    for sk, mk in pares_sm:
        if sk not in hs:
            nuevo_total += 1
            if mk in prev:
                nuevo_marca_conocida += 1
    hist_sku[cli] = hs | {sk for sk, _ in pares_sm}

OUT["marca_como_variable"] = {
    "pct_compra_en_marcas_conocidas": round(float(np.mean(fid_marca)) * 100, 1),
    "pct_productos_nuevos_de_marca_conocida": round(nuevo_marca_conocida / nuevo_total * 100, 1),
    "n_productos_nuevos": int(nuevo_total),
}

# ------------------------ E) ¿cuándo dentro del mes adopta el cliente lo nuevo?
# Si toda la adopción ocurriera en la primera visita, recalcular la recomendación
# en cada visita no serviría de nada. Se mide para saberlo.
flags = pd.read_parquet(DERIVADO / "dim_sku_flags.parquet")
RECOM = set(flags[flags.recomendable].sku)
# Julio y no agosto: agosto termina en jueves 27 y le faltan viernes y sábado,
# lo que cortaría las últimas visitas del mes y sesgaría el reparto por visita.
MES_E = MESES[-2]
hist_e = c[c.anio_mes < MES_E].groupby("cliente_id", observed=True).sku.apply(set)
test_e = c[c.anio_mes == MES_E]

por_visita, n_cli_e, tot_nuevos = {}, 0, 0
for cli, g in test_e.groupby("cliente_id", observed=True):
    if cli not in hist_e.index:
        continue
    vs = sorted(g.fecha.unique())
    if len(vs) < 2:
        continue
    n_cli_e += 1
    vistos = set(hist_e[cli])
    for i, f in enumerate(vs, 1):
        sk = {x for x in g[g.fecha == f].sku if x in RECOM}
        nuevos = sk - vistos
        d = por_visita.setdefault(i, {"nuevos": 0, "visitas": 0})
        d["nuevos"] += len(nuevos); d["visitas"] += 1
        tot_nuevos += len(nuevos)
        vistos |= sk

OUT["adopcion_por_visita"] = {
    "mes": MES_E, "clientes_2plus_visitas": n_cli_e, "productos_nuevos": tot_nuevos,
    "pct_tras_primera_visita": round((tot_nuevos - por_visita[1]["nuevos"]) / tot_nuevos * 100, 1),
    "detalle": [{"visita": i, "clientes": v["visitas"], "nuevos": v["nuevos"],
                 "pct": round(v["nuevos"] / tot_nuevos * 100, 1),
                 "nuevos_por_visita": round(v["nuevos"] / v["visitas"], 2)}
                for i, v in sorted(por_visita.items()) if i <= 5],
}

# ------- F) ¿de qué está hecha la canasta del mes? nunca / dormido / habitual
# Un producto que el cliente compró hace meses y dejó de pedir NO es lo mismo
# que uno que pide cada semana: al primero recordárselo suma un SKU al mes,
# al segundo no, porque lo iba a pedir igual.
def _previos(mes, k):
    per = pd.Period(mes, freq="M")
    return [str(per - j) for j in range(1, k + 1)]

alguna_vez = hist_e.copy()                       # ya calculado en (E): historia < MES_E
canasta_mes = test_e.groupby("cliente_id", observed=True).sku.apply(set)
composicion = {}
for v in (1, 2, 3):
    rec = (c[c.anio_mes.isin(_previos(MES_E, v))]
           .groupby("cliente_id", observed=True).sku.apply(set))
    nunca = dormido = habitual = 0
    for cli, sk in canasta_mes.items():
        if cli not in alguna_vez.index:
            continue
        prev, reci = alguna_vez[cli], rec.get(cli, set())
        for s in sk & RECOM:
            if s not in prev:
                nunca += 1
            elif s in reci:
                habitual += 1
            else:
                dormido += 1
    tot = nunca + dormido + habitual
    composicion[v] = {"nunca": round(nunca / tot * 100, 1),
                      "dormido": round(dormido / tot * 100, 1),
                      "habitual": round(habitual / tot * 100, 1)}

# tasa base: ¿cuánto más probable es que vuelva un dormido que se adopte uno nuevo?
rec2 = (c[c.anio_mes.isin(_previos(MES_E, 2))]
        .groupby("cliente_id", observed=True).sku.apply(set))
n_d = n_n = h_d = h_n = 0
tam_dorm = []
for cli, sk in canasta_mes.items():
    if cli not in alguna_vez.index:
        continue
    prev, reci = alguna_vez[cli], rec2.get(cli, set())
    dormidos = (prev - reci) & RECOM
    nuncas = RECOM - prev
    tam_dorm.append(len(dormidos))
    n_d += len(dormidos); n_n += len(nuncas)
    h_d += len(sk & dormidos); h_n += len(sk & nuncas)

OUT["composicion_canasta"] = {
    "mes": MES_E, "por_ventana": composicion,
    "dormidos_por_cliente": round(float(np.mean(tam_dorm)), 1),
    "tasa_reactivacion_pct": round(h_d / n_d * 100, 2),
    "tasa_descubrimiento_pct": round(h_n / n_n * 100, 2),
    "veces_mas_probable": round((h_d / n_d) / (h_n / n_n), 1),
}

json.dump(OUT, open(RESULTADOS / "diag_techo.json", "w"), indent=2, ensure_ascii=False)

print(f"=== A) TECHO DEL MODELO ACTUAL (mes de prueba {TEST}) ===")
print("   De todo lo que el cliente compró ese mes, qué fracción estaba en...")
for t in OUT["techo"]:
    print(f"   top-{t['N']:<4} su historia {t['pct_en_historia']:>5}% | "
          f"top-ruta {t['pct_en_top_ruta']:>5}% | top-global {t['pct_en_top_global']:>5}%"
          f"  ->  la ruta aporta {t['pct_solo_ruta_aporta']:>4}% que la historia no tiene | "
          f"NADIE captura {t['pct_nadie_captura']:>5}%")

print("\n   Descomposición (top-50): la UNIÓN de historia + ruta cubre "
      f"{OUT['techo'][1]['pct_union']}%")
print(f"     solo la historia aporta {OUT['techo'][1]['pct_solo_historia_aporta']}% "
      f"que la ruta no tiene")
print(f"     solo la ruta aporta     {OUT['techo'][1]['pct_solo_ruta_aporta']}% "
      f"que la historia no tiene")
mm = OUT["marca_como_variable"]
print(f"\n=== D) ¿SIRVE LA MARCA? ===")
print(f"   {mm['pct_compra_en_marcas_conocidas']}% de lo que compra un cliente es de marcas que ya conocía")
print(f"   de los {mm['n_productos_nuevos']:,} productos NUEVOS para un cliente, "
      f"{mm['pct_productos_nuevos_de_marca_conocida']}% son de una marca que YA compraba")

av = OUT["adopcion_por_visita"]
print(f"\n=== E) ADOPCIÓN DENTRO DEL MES ({av['clientes_2plus_visitas']:,} clientes con 2+ visitas) ===")
for d in av["detalle"]:
    print(f"   visita {d['visita']}: {d['nuevos']:>7,} productos nuevos ({d['pct']:>4}%)  "
          f"{d['nuevos_por_visita']} por visita")
print(f"   -> {av['pct_tras_primera_visita']}% de la adopción ocurre DESPUÉS de la primera visita")

cc_ = OUT["composicion_canasta"]
print(f"\n=== F) COMPOSICIÓN DE LA CANASTA ({cc_['mes']}) ===")
print(f"   {'ventana':<10} {'nunca':>8} {'dormido':>9} {'habitual':>10}")
for v, d in cc_["por_ventana"].items():
    print(f"   {str(v)+' mes(es)':<10} {d['nunca']:>7}% {d['dormido']:>8}% {d['habitual']:>9}%")
print(f"   dormidos por cliente: {cc_['dormidos_por_cliente']}")
print(f"   tasa de reactivación {cc_['tasa_reactivacion_pct']}% vs descubrimiento "
      f"{cc_['tasa_descubrimiento_pct']}%  ->  {cc_['veces_mas_probable']}x más probable")

print(f"\n=== B) ¿HAY LOOP? (si lo hubiera, concentración subiría) ===")
print("   mes      top50%   gini   SKUs vendidos   SKUs/cliente   Jac.todas  Jac.estables")
for e, s in zip(eq, sim):
    print(f"   {e['mes']}  {e['share_top50']:>6}  {e['gini_sku']:>6}  "
          f"{e['skus_vendidos']:>10}  {e['skus_por_cliente']:>12}  {s['jaccard_intra_ruta']:>10}  {s['jaccard_rutas_estables']:>10}")
a, b = eq[0], eq[-1]
print(f"\n   Cambio sep-25 -> ago-26:  top50 {a['share_top50']}% -> {b['share_top50']}%  |  "
      f"gini {a['gini_sku']} -> {b['gini_sku']}  |  "
      f"Jaccard {sim[0]['jaccard_intra_ruta']} -> {sim[-1]['jaccard_intra_ruta']}  |  "
      f"solo rutas estables {sim[0]['jaccard_rutas_estables']} -> {sim[-1]['jaccard_rutas_estables']}")
