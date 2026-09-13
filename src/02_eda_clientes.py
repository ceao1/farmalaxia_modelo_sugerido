"""
EDA de comportamiento de clientes — dbventas / tblVentas.

Grano:
  visita = (fecha, cliente_id)                     -> el preventista pasó
  compra = visita con >=1 linea con piezas > 0     -> el cliente efectivamente pidió

Enfocado en: tendencia de clientes activos, frecuencia intramensual, canasta
y recompra — insumos para un recomendador de SKUs.
"""
import json
import numpy as np
import pandas as pd
from comun import DERIVADO, RESULTADOS

OUT = {}
df = pd.read_parquet(DERIVADO / "ventas.parquet")
if "es_pack" not in df.columns:
    df["es_pack"] = df["sku"].fillna("").str.upper().str.startswith("PP")
df["anio_mes"] = df["anio_mes"].astype(str)
MESES = sorted(df.anio_mes.unique())

# ---------------------------------------------------------------- grano
# Una visita puede abarcar >1 ruta el mismo día: colapsamos, al cliente le da igual.
prod = df[df.es_compra & ~df.es_pack]   # solo mercancía real

visitas = (df.groupby(["cliente_id", "fecha"], observed=True)
             .agg(lineas=("sku", "size"),
                  skus_todo=("sku", lambda s: s.dropna().nunique()),
                  piezas=("piezas_preventa", "sum"),
                  importe=("importe_preventa", "sum"))
             .reset_index())
# SKUs de MERCANCÍA por canasta (los PP* son promoción, no producto)
_sk = (prod.groupby(["cliente_id", "fecha"], observed=True).sku.nunique()
           .rename("skus").reset_index())
visitas = visitas.merge(_sk, on=["cliente_id", "fecha"], how="left")
visitas["skus"] = visitas["skus"].fillna(0).astype(int)
visitas["anio_mes"] = visitas["fecha"].dt.to_period("M").astype(str)
visitas["es_compra"] = visitas["piezas"] > 0
compras = visitas[visitas.es_compra].copy()

OUT["grano"] = {
    "visitas": int(len(visitas)),
    "compras": int(len(compras)),
    "tasa_conversion_visita": round(len(compras) / len(visitas) * 100, 1),
    "clientes_totales": int(df.cliente_id.nunique()),
    "clientes_que_compraron": int(compras.cliente_id.nunique()),
    "skus": int(prod.sku.nunique()),
    "skus_promocion": int(df[df.es_pack].sku.nunique()),
}

# ------------------------------------------------- 1. clientes activos por mes
mensual = []
for m in MESES:
    v = visitas[visitas.anio_mes == m]
    c = compras[compras.anio_mes == m]
    mensual.append({
        "mes": m,
        "clientes_visitados": int(v.cliente_id.nunique()),
        "clientes_compradores": int(c.cliente_id.nunique()),
        "visitas": int(len(v)),
        "compras": int(len(c)),
        "importe": float(c.importe.sum()),
        "dias_habiles": int(v.fecha.nunique()),
    })
mens = pd.DataFrame(mensual)
mens["tasa_conversion"] = (mens.clientes_compradores / mens.clientes_visitados * 100).round(1)
mens["compras_por_cliente"] = (mens.compras / mens.clientes_compradores).round(2)
mens["ticket_promedio"] = (mens.importe / mens.compras).round(0)
mens["visitas_confiables"] = mens.mes != "2025-11"
mens.loc[mens.mes == "2025-11", ["clientes_visitados", "visitas", "tasa_conversion"]] = None
OUT["mensual"] = mens.to_dict("records")

# ------------------------------------------- 2. nuevos / recurrentes / perdidos
primera = compras.groupby("cliente_id", observed=True).anio_mes.min().to_dict()
sets = {m: set(compras[compras.anio_mes == m].cliente_id) for m in MESES}
ciclo = []
vistos = set()
for i, m in enumerate(MESES):
    act = sets[m]
    prev = sets[MESES[i - 1]] if i else set()
    nuevos = {c for c in act if primera[c] == m}
    recurr = act & prev
    react = act - prev - nuevos
    perdidos = prev - act
    ciclo.append({"mes": m, "nuevos": len(nuevos), "recurrentes": len(recurr),
                  "reactivados": len(react), "perdidos": len(perdidos),
                  "retencion": round(len(recurr) / len(prev) * 100, 1) if prev else None})
    vistos |= act
OUT["ciclo_vida"] = ciclo

# --------------------------------------- 3. frecuencia intramensual (LA pregunta)
cm = (compras.groupby(["cliente_id", "anio_mes"], observed=True)
             .agg(compras=("fecha", "nunique"), importe=("importe", "sum")).reset_index())
# SKUs DISTINTOS del mes: sumar los conteos por compra duplicaría los recomprados
_lin_mes = df[df.es_compra & ~df.es_pack][["cliente_id", "anio_mes", "sku"]].drop_duplicates()
_skus_mes = (_lin_mes.groupby(["cliente_id", "anio_mes"], observed=True)
                     .sku.nunique().rename("skus").reset_index())
cm = cm.merge(_skus_mes, on=["cliente_id", "anio_mes"], how="left")
vm = (visitas.groupby(["cliente_id", "anio_mes"], observed=True)
             .agg(visitas=("fecha", "nunique")).reset_index())
cm = cm.merge(vm, on=["cliente_id", "anio_mes"], how="left")

# 2025-11 no tiene filas de visita sin venta -> visitas==compras ese mes.
# Las metricas basadas en VISITA lo excluyen; las basadas en COMPRA no se afectan.
cmv = cm[cm.anio_mes != "2025-11"]

bins = [0, 1, 2, 3, 4, 6, 9, 1000]
labels = ["1", "2", "3", "4", "5-6", "7-9", "10+"]
cm["banda"] = pd.cut(cm.compras, bins=bins, labels=labels, right=True)
freq = (cm.banda.value_counts(normalize=True).reindex(labels) * 100).round(1)
freq_n = cm.banda.value_counts().reindex(labels)
OUT["frecuencia_intramensual"] = [
    {"banda": b, "pct": float(freq[b]), "n": int(freq_n[b])} for b in labels]
OUT["frecuencia_resumen"] = {
    "pares_cliente_mes": int(len(cm)),
    "media": round(float(cm.compras.mean()), 2),
    "mediana": float(cm.compras.median()),
    "p75": float(cm.compras.quantile(.75)),
    "p90": float(cm.compras.quantile(.90)),
    "pct_mas_de_una": round(float((cm.compras > 1).mean() * 100), 1),
    "visitas_media": round(float(cmv.visitas.mean()), 2),
    "conversion_visita_compra": round(float((cmv.compras / cmv.visitas).mean() * 100), 1),
    "nota_visitas": "metricas de visita excluyen 2025-11 (sin registro de visitas sin venta)",
}

# --------------------------------------------- 4. intervalo entre compras (días)
compras_ord = compras.sort_values(["cliente_id", "fecha"])
compras_ord["gap"] = compras_ord.groupby("cliente_id", observed=True).fecha.diff().dt.days
gaps = compras_ord.gap.dropna()
gap_hist = gaps[gaps <= 60].value_counts().sort_index()
OUT["intervalo"] = {
    "n": int(len(gaps)),
    "mediana": float(gaps.median()),
    "media": round(float(gaps.mean()), 1),
    "p25": float(gaps.quantile(.25)),
    "p75": float(gaps.quantile(.75)),
    "hist": [{"dias": int(d), "n": int(n)} for d, n in gap_hist.items()],
    "pct_7d": round(float((gaps == 7).mean() * 100), 1),
    "pct_menor_7d": round(float((gaps < 7).mean() * 100), 1),
}

# ----------------------------------------------------------------- 5. canasta
OUT["canasta"] = {
    "skus_por_compra_media": round(float(compras.skus.mean()), 2),
    "skus_por_compra_mediana": float(compras.skus.median()),
    "skus_por_compra_p90": float(compras.skus.quantile(.90)),
    "importe_por_compra_mediana": round(float(compras.importe.median()), 0),
    "skus_por_cliente_mes_media": round(float(cm.skus.mean()), 2),
    "hist_skus": [{"skus": int(k), "n": int(v)} for k, v in
                  compras.skus.clip(upper=25).value_counts().sort_index().items()],
}

# ------------------------------------- 6. recompra mes a mes (clave p/ recomendador)
# OJO: los SKU PP* son registros de promoción (importe 0), no productos. Se excluyen
# de toda métrica de SURTIDO (ver 'prod' arriba).
lineas = prod[["cliente_id", "anio_mes", "sku"]].drop_duplicates()
rec = []
for i in range(1, len(MESES)):
    prev = lineas[lineas.anio_mes == MESES[i - 1]]
    cur = lineas[lineas.anio_mes == MESES[i]]
    comunes = set(prev.cliente_id) & set(cur.cliente_id)
    if not comunes:
        continue
    p = prev[prev.cliente_id.isin(comunes)].groupby("cliente_id", observed=True).sku.apply(set)
    c = cur[cur.cliente_id.isin(comunes)].groupby("cliente_id", observed=True).sku.apply(set)
    j = pd.DataFrame({"prev": p, "cur": c}).dropna()
    inter = j.apply(lambda r: len(r.prev & r.cur), axis=1)
    rec.append({"mes": MESES[i],
                "clientes": int(len(j)),
                "pct_skus_repetidos": round(float((inter / j.cur.apply(len)).mean() * 100), 1),
                "skus_nuevos_media": round(float((j.cur.apply(len) - inter).mean()), 2)})
OUT["recompra"] = rec

# ---------- 6b. recompra ACUMULADA: ¿nuevo vs TODA la historia previa del cliente?
hist, rec_acum, repertorio = {}, [], []
for i, m in enumerate(MESES):
    cur = lineas[lineas.anio_mes == m].groupby("cliente_id", observed=True).sku.apply(set)
    if i >= 1:
        ya = {c: hist[c] for c in cur.index if c in hist}
        if ya:
            r = np.array([len(cur[c] & ya[c]) / len(cur[c]) for c in ya])
            nv = np.array([len(cur[c] - ya[c]) for c in ya])
            rec_acum.append({"mes": m, "clientes": len(ya),
                             "pct_ya_comprado": round(float(r.mean() * 100), 1),
                             "skus_nunca_comprados": round(float(nv.mean()), 2)})
    for c, sk in cur.items():
        hist[c] = hist.get(c, set()) | sk
    coh = [c for c in hist if primera.get(c) == MESES[0]]
    if coh:
        tam = np.array([len(hist[c]) for c in coh])
        repertorio.append({"mes_antiguedad": i + 1, "clientes": len(coh),
                           "skus_acum_media": round(float(tam.mean()), 1),
                           "skus_acum_mediana": float(np.median(tam))})
OUT["recompra_acumulada"] = rec_acum
OUT["repertorio"] = repertorio

# estabilidad: SKUs "core" (comprados en >=3 meses) vs one-off (1 solo mes)
mes_por_sku = lineas.groupby(["cliente_id", "sku"], observed=True).anio_mes.nunique()
OUT["estabilidad_repertorio"] = {
    "pct_core_3plus": round(float((mes_por_sku >= 3).mean() * 100), 1),
    "pct_2_meses": round(float((mes_por_sku == 2).mean() * 100), 1),
    "pct_one_off": round(float((mes_por_sku == 1).mean() * 100), 1),
}

# --------------------------------------------- 7. sparsity y cola larga de SKUs
pares = lineas[["cliente_id", "sku"]].drop_duplicates()
n_cli, n_sku = lineas.cliente_id.nunique(), lineas.sku.nunique()
sku_pop = lineas.groupby("sku", observed=True).cliente_id.nunique().sort_values(ascending=False)
imp_sku = (prod.groupby("sku", observed=True).importe_preventa.sum()
             .sort_values(ascending=False))
cum = imp_sku.cumsum() / imp_sku.sum()
skus_por_cliente = pares.groupby("cliente_id", observed=True).sku.nunique()
OUT["sparsity"] = {
    "clientes": int(n_cli), "skus": int(n_sku),
    "pares_observados": int(len(pares)),
    "densidad_pct": round(len(pares) / (n_cli * n_sku) * 100, 3),
    "skus_por_cliente_mediana": float(skus_por_cliente.median()),
    "skus_por_cliente_media": round(float(skus_por_cliente.mean()), 1),
    "skus_por_cliente_p90": float(skus_por_cliente.quantile(.90)),
    "skus_80pct_importe": int((cum <= 0.8).sum() + 1),
    "top10_pct_importe": round(float(cum.iloc[9] * 100), 1),
    "hist_skus_cliente": [{"skus": int(k), "n": int(v)} for k, v in
                          skus_por_cliente.clip(upper=60).value_counts().sort_index().items()],
}

# ------------------------------------------------------------ 8. segmentación
perfil = cm.groupby("cliente_id", observed=True).agg(
    meses_activo=("anio_mes", "nunique"),
    compras_mes=("compras", "mean"),
    skus_mes=("skus", "mean"),
    importe_mes=("importe", "mean")).reset_index()

def seg(r):
    if r.meses_activo <= 2:
        return "Esporádico / abandonó"
    if r.compras_mes >= 4:
        return "Alta frecuencia (semanal)"
    if r.compras_mes >= 2:
        return "Media (quincenal)"
    return "Baja (mensual)"

# Quien llegó en jul/ago-2026 NO puede tener >2 meses: es censura, no baja.
perfil["primera_compra"] = perfil.cliente_id.map(primera)
perfil["censurado"] = perfil.primera_compra >= "2026-07"
perfil["segmento"] = perfil.apply(seg, axis=1)
perfil.loc[perfil.censurado, "segmento"] = "Sin historia suficiente"
OUT["censurados"] = int(perfil.censurado.sum())
sg = perfil.groupby("segmento").agg(
    clientes=("cliente_id", "size"), compras_mes=("compras_mes", "mean"),
    skus_mes=("skus_mes", "mean"), importe_mes=("importe_mes", "mean"),
    meses=("meses_activo", "mean")).round(2).reset_index()
sg["pct"] = (sg.clientes / sg.clientes.sum() * 100).round(1)
# peso economico e integridad de la regla (para poder explicarla, no solo aplicarla)
perfil["importe_anual"] = perfil.importe_mes * perfil.meses_activo
pe = perfil.groupby("segmento").agg(cli=("cliente_id", "size"),
                                    imp=("importe_anual", "sum"),
                                    meses=("meses_activo", "mean")).reset_index()
pe["pct_cli"] = (pe.cli / pe.cli.sum() * 100).round(1)
pe["pct_imp"] = (pe.imp / pe.imp.sum() * 100).round(1)
pe["imp_cli"] = (pe.imp / pe.cli).round(0)
pe["meses"] = pe.meses.round(1)
sg = sg.merge(pe[["segmento", "pct_imp", "imp_cli", "meses"]].rename(columns={"meses": "meses_prom"}),
              on="segmento", how="left")
OUT["segmentos"] = sg.to_dict("records")

# ¿cuántos clientes quedan pegados a un umbral? (mide qué tan frágil es el corte)
_act = perfil[~perfil.censurado]
OUT["segmentacion_regla"] = {
    "clasificados": int(len(_act)),
    "censurados": int(perfil.censurado.sum()),
    "frontera_alta_media": round(float(((_act.compras_mes >= 3.75) & (_act.compras_mes < 4.25)).mean() * 100), 1),
    "frontera_media_baja": round(float(((_act.compras_mes >= 1.75) & (_act.compras_mes < 2.25)).mean() * 100), 1),
    "pct_12_meses": round(float((_act.meses_activo == 12).mean() * 100), 1),
    "alta_activos_12m": round(float((_act[(_act.meses_activo > 2) & (_act.compras_mes >= 4)]
                                     .meses_activo == 12).mean() * 100), 1),
}

# ---- 8b. peso economico de cada clase de par cliente-SKU (decide el recomendador)
pares_cs = (prod.groupby(["cliente_id", "sku"], observed=True)
              .agg(meses=("anio_mes", "nunique"), importe=("importe_preventa", "sum"))
              .reset_index())
pares_cs["clase"] = np.where(pares_cs.meses >= 3, "core", 
                     np.where(pares_cs.meses == 2, "dos_meses", "one_off"))
tc = pares_cs.groupby("clase").agg(pares=("sku", "size"), importe=("importe", "sum")).reset_index()
tc["pct_pares"] = (tc.pares / tc.pares.sum() * 100).round(1)
tc["pct_importe"] = (tc.importe / tc.importe.sum() * 100).round(1)
tc["importe_medio"] = (tc.importe / tc.pares).round(0)
OUT["peso_clases"] = tc.to_dict("records")

# el catalogo es estable? SKUs que debutan cada mes
OUT["skus_nuevos_catalogo"] = {str(k): int(v) for k, v in
    prod.groupby("sku", observed=True).anio_mes.min().value_counts().sort_index().items()}

json.dump(OUT, open(RESULTADOS / "eda_resultados.json", "w"), indent=2, ensure_ascii=False)
perfil.to_parquet(DERIVADO / "perfil_clientes.parquet", index=False)
cm.to_parquet(DERIVADO / "cliente_mes.parquet", index=False)

# ------------------------------------------------------------------ resumen
g = OUT["grano"]; f = OUT["frecuencia_resumen"]; s = OUT["sparsity"]
print(f"""
GRANO
  visitas (fecha+cliente)      {g['visitas']:>12,}
  compras (piezas>0)           {g['compras']:>12,}   conversión {g['tasa_conversion_visita']}%
  clientes que compraron       {g['clientes_que_compraron']:>12,} de {g['clientes_totales']:,}

FRECUENCIA INTRAMENSUAL  ({f['pares_cliente_mes']:,} pares cliente-mes)
  compras/mes  media {f['media']}  mediana {f['mediana']:.0f}  p75 {f['p75']:.0f}  p90 {f['p90']:.0f}
  compran >1 vez al mes: {f['pct_mas_de_una']}%
  visitas/mes media {f['visitas_media']}  -> conversión {f['conversion_visita_compra']}%""")
for b in OUT["frecuencia_intramensual"]:
    print(f"    {b['banda']:>4} compras/mes  {b['pct']:>5}%  ({b['n']:,})")
i = OUT["intervalo"]
print(f"""
INTERVALO ENTRE COMPRAS
  mediana {i['mediana']:.0f} días  p25 {i['p25']:.0f}  p75 {i['p75']:.0f}
  exactamente 7 días: {i['pct_7d']}%   menos de 7: {i['pct_menor_7d']}%

CANASTA
  SKUs por compra: media {OUT['canasta']['skus_por_compra_media']}  mediana {OUT['canasta']['skus_por_compra_mediana']:.0f}  p90 {OUT['canasta']['skus_por_compra_p90']:.0f}

SPARSITY (matriz cliente x SKU)
  {s['clientes']:,} x {s['skus']:,} = densidad {s['densidad_pct']}%
  SKUs distintos por cliente: mediana {s['skus_por_cliente_mediana']:.0f}  media {s['skus_por_cliente_media']}
  {s['skus_80pct_importe']} SKUs concentran el 80% del importe; top-10 = {s['top10_pct_importe']}%

RECOMPRA mes a mes (últimos 3)""")
for r in OUT["recompra"][-3:]:
    print(f"  {r['mes']}: {r['pct_skus_repetidos']}% de la canasta repite mes anterior, {r['skus_nuevos_media']} SKUs nuevos")
ra = OUT["recompra_acumulada"][-1]; est = OUT["estabilidad_repertorio"]
print(f"""
RECOMPRA ACUMULADA (vs toda la historia previa) — ultimo mes {ra['mes']}
  {ra['pct_ya_comprado']}% de la canasta YA se habia comprado antes
  solo {ra['skus_nunca_comprados']} SKUs realmente nuevos por cliente
REPERTORIO (cohorte sep-2025, SKUs acumulados por antiguedad)
  """ + "  ".join(f"m{r['mes_antiguedad']}:{r['skus_acum_mediana']:.0f}" for r in OUT["repertorio"]) + f"""
ESTABILIDAD: core(>=3 meses) {est['pct_core_3plus']}%  2 meses {est['pct_2_meses']}%  one-off {est['pct_one_off']}%""")
print("\nPESO ECONOMICO POR CLASE DE PAR CLIENTE-SKU")
for r in OUT["peso_clases"]:
    print(f"  {r['clase']:<10} {r['pct_pares']:>5}% de los pares  ->  {r['pct_importe']:>5}% del importe  (medio {r['importe_medio']:.0f})")
print("\nSEGMENTOS")
for r in OUT["segmentos"]:
    print(f"  {r['segmento']:<26} {r['clientes']:>7,} ({r['pct']:>4}%)  {r['compras_mes']:>5} compras/mes  {r['skus_mes']:>6} SKUs/mes")
