"""Genera dashboard.html a partir de eda_resultados.json. Geometría SVG calculada, no a ojo."""
import json
from comun import INFORMES, RESULTADOS, SRC
d = json.load(open(RESULTADOS / "eda_resultados.json"))
P = json.load(open(RESULTADOS / "eda_productos.json"))
T = json.load(open(RESULTADOS / "diag_techo.json"))

W, ML, MR, MT = 1000, 58, 22, 18

def esc(s): return str(s).replace("&","&amp;").replace("<","&lt;").replace(">","&gt;").replace('"',"&quot;")

def ES(n, dec=0):
    """Formato español: miles con punto, decimales con coma."""
    t = f"{n:,.{dec}f}"
    return t.replace(",", "\u0000").replace(".", ",").replace("\u0000", ".")

def axes(h, mb, ticks, ymax, fmt=lambda v: f"{v:,.0f}"):
    """Rejilla horizontal + etiquetas del eje Y."""
    out, iw, ih = [], W-ML-MR, h-MT-mb
    for t in ticks:
        y = MT + ih - (t/ymax)*ih
        out.append(f'<line x1="{ML}" y1="{y:.1f}" x2="{W-MR}" y2="{y:.1f}" class="grid"/>')
        out.append(f'<text x="{ML-10}" y="{y+4:.1f}" class="ytick">{fmt(t)}</text>')
    return "".join(out)

# ---------------------------------------------------------------- 1. mensual
def chart_mensual():
    h, mb = 300, 40
    m = d["mensual"]; iw, ih = W-ML-MR, h-MT-mb
    ymax = 34000; ticks = [0,10000,20000,30000]
    n = len(m); step = iw/(n-1)
    X = lambda i: ML + i*step
    Y = lambda v: MT + ih - (v/ymax)*ih
    s = [axes(h, mb, ticks, ymax, lambda v: f"{v/1000:.0f}k" if v else "0")]
    # marca de expansión (junio 2026 = índice 9)
    xe = X(9)
    s.append(f'<rect x="{xe:.1f}" y="{MT}" width="{W-MR-xe:.1f}" height="{ih:.1f}" class="band"/>')
    s.append(f'<text x="{xe+10:.1f}" y="{MT+18}" class="annot">95 rutas (antes 71)</text>')
    for key, cls, lbl in [("clientes_visitados","s2","Visitados"),("clientes_compradores","s1","Compradores")]:
        pts, seg = [], []
        for i, r in enumerate(m):
            v = r[key]
            if v is None: 
                if len(seg)>1: pts.append(seg)
                seg = []; continue
            seg.append(f"{X(i):.1f},{Y(v):.1f}")
        if len(seg)>1: pts.append(seg)
        for p in pts:
            s.append(f'<polyline points="{" ".join(p)}" class="line {cls}"/>')
        for i, r in enumerate(m):
            v = r[key]
            if v is None: continue
            s.append(f'<circle cx="{X(i):.1f}" cy="{Y(v):.1f}" r="4.5" class="dot {cls}" '
                     f'data-tip="{esc(r["mes"])} · {lbl}: {ES(v)}"/>')
    for i, r in enumerate(m):
        s.append(f'<text x="{X(i):.1f}" y="{h-mb+22}" class="xtick">{r["mes"][2:]}</text>')
    s.append(f'<text x="{X(0)+6:.1f}" y="{Y(m[0]["clientes_visitados"])-12:.1f}" class="dlabel c2">Visitados</text>')
    s.append(f'<text x="{X(0)+6:.1f}" y="{Y(m[0]["clientes_compradores"])+20:.1f}" class="dlabel c1">Compradores</text>')
    return f'<svg viewBox="0 0 {W} {h}" class="chart" role="img" aria-label="Clientes visitados y compradores por mes">{"".join(s)}</svg>'

# ------------------------------------------------------- 2. intervalo (la clave)
def chart_intervalo():
    h, mb = 330, 46
    hist = {x["dias"]: x["n"] for x in d["intervalo"]["hist"]}
    days = list(range(1, 36))
    iw, ih = W-ML-MR, h-MT-mb
    ymax = 440000; ticks = [0,100000,200000,300000,400000]
    bw = iw/len(days)
    s = [axes(h, mb, ticks, ymax, lambda v: f"{v/1000:.0f}k" if v else "0")]
    tot = d["intervalo"]["n"]
    for i, dd in enumerate(days):
        v = hist.get(dd, 0)
        bh = (v/ymax)*ih
        x = ML + i*bw + 1
        y = MT + ih - bh
        semanal = dd % 7 == 0
        s.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{bw-2:.1f}" height="{max(bh,0.6):.1f}" rx="2" '
                 f'class="bar {"acc" if semanal else "mut"}" '
                 f'data-tip="{dd} días: {ES(v)} ({ES(v/tot*100,1)} %)"/>')
        if semanal:
            s.append(f'<text x="{x+(bw-2)/2:.1f}" y="{y-7:.1f}" class="blabel">{v/1000:.0f}k</text>')
    for i, dd in enumerate(days):
        if dd % 7 == 0 or dd == 1:
            s.append(f'<text x="{ML+i*bw+bw/2:.1f}" y="{h-mb+22}" class="xtick str">{dd}</text>')
        elif dd % 7 in (3,4) and dd < 7:
            pass
    s.append(f'<text x="{ML+iw/2:.1f}" y="{h-8}" class="axlabel">días entre una compra y la siguiente</text>')
    return f'<svg viewBox="0 0 {W} {h}" class="chart" role="img" aria-label="Histograma de días entre compras, con picos en múltiplos de 7">{"".join(s)}</svg>'

# ---------------------------------------------------------------- 3. frecuencia
def chart_freq():
    h, mb = 250, 48
    f = d["frecuencia_intramensual"]
    iw, ih = W-ML-MR, h-MT-mb
    ymax = 25; ticks = [0,5,10,15,20,25]
    bw = iw/len(f)
    s = [axes(h, mb, ticks, ymax, lambda v: f"{v:.0f}%")]
    for i, r in enumerate(f):
        bh = (r["pct"]/ymax)*ih
        x = ML + i*bw + 8; y = MT + ih - bh
        s.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{bw-16:.1f}" height="{max(bh,1):.1f}" rx="3" '
                 f'class="bar {"mut" if i==0 else "acc"}" data-tip="{r["banda"]} compra(s)/mes: {ES(r["pct"],1)} % · {ES(r["n"])} pares"/>')
        s.append(f'<text x="{x+(bw-16)/2:.1f}" y="{y-8:.1f}" class="blabel">{ES(r["pct"],1)} %</text>')
        s.append(f'<text x="{x+(bw-16)/2:.1f}" y="{h-mb+22}" class="xtick str">{r["banda"]}</text>')
    s.append(f'<text x="{ML+iw/2:.1f}" y="{h-8}" class="axlabel">compras por cliente en el mes</text>')
    return f'<svg viewBox="0 0 {W} {h}" class="chart" role="img" aria-label="Distribución de compras por cliente-mes">{"".join(s)}</svg>'

# --------------------------------------------------------------- 4. repertorio
def chart_repertorio():
    h, mb = 260, 42
    rep = d["repertorio"]; rec = d["recompra_acumulada"]
    iw, ih = W-ML-MR, h-MT-mb
    ymax = 60; ticks=[0,15,30,45,60]
    n=len(rep); step=iw/(n-1)
    X=lambda i: ML+i*step; Y=lambda v: MT+ih-(v/ymax)*ih
    s=[axes(h,mb,ticks,ymax,lambda v:f"{v:.0f}")]
    pts=" ".join(f"{X(i):.1f},{Y(r['skus_acum_mediana']):.1f}" for i,r in enumerate(rep))
    s.append(f'<polyline points="{pts}" class="line s1"/>')
    # referencia: si no hubiera recompra, crecería ~12.7/mes
    _pend = d["canasta"]["skus_por_cliente_mes_media"]   # sin recompra crecería así
    ref=" ".join(f"{X(i):.1f},{Y((i+1)*_pend):.1f}" for i in range(n) if (i+1)*_pend <= ymax)
    s.append(f'<polyline points="{ref}" class="line ref"/>')
    s.append(f'<text x="{X(3)+8:.1f}" y="{Y(min(4*_pend,ymax))-10:.1f}" class="dlabel mutc">sin recompra (hipotético)</text>')
    for i,r in enumerate(rep):
        s.append(f'<circle cx="{X(i):.1f}" cy="{Y(r["skus_acum_mediana"]):.1f}" r="4.5" class="dot s1" '
                 f'data-tip="Mes {r["mes_antiguedad"]}: {ES(r["skus_acum_mediana"])} SKUs acumulados (mediana)"/>')
        s.append(f'<text x="{X(i):.1f}" y="{h-mb+22}" class="xtick">m{r["mes_antiguedad"]}</text>')
    _fin = rep[-1]["skus_acum_mediana"]
    s.append(f'<text x="{X(n-1):.1f}" y="{Y(_fin)-14:.1f}" class="dlabel c1" text-anchor="end">{ES(_fin)} SKUs</text>')
    s.append(f'<text x="{ML+iw/2:.1f}" y="{h-6}" class="axlabel">meses de antigüedad · cohorte septiembre 2025</text>')
    return f'<svg viewBox="0 0 {W} {h}" class="chart" role="img" aria-label="SKUs acumulados por cliente según antigüedad">{"".join(s)}</svg>'

# ------------------------------------------------------------ 5. peso por clase
def chart_peso():
    h = 190
    pz = {r["clase"]: r for r in d["peso_clases"]}
    order = [("core","Núcleo (≥3 meses)","s1"),("dos_meses","2 meses","s3"),("one_off","Una sola vez","s2")]
    iw = W-ML-MR
    rows = [("% de pares cliente-SKU","pct_pares"),("% del importe","pct_importe")]
    s=[]
    for ri,(lbl,key) in enumerate(rows):
        y = 34 + ri*78
        s.append(f'<text x="{ML}" y="{y-10}" class="rowlabel">{lbl}</text>')
        x = ML
        for ck, cname, cls in order:
            wseg = pz[ck][key]/100*iw
            s.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{max(wseg-2,1):.1f}" height="40" rx="3" '
                     f'class="seg {cls}" data-tip="{cname} · {lbl}: {ES(pz[ck][key],1)} %"/>')
            if wseg > 70:
                s.append(f'<text x="{x+wseg/2-1:.1f}" y="{y+25:.1f}" class="seglabel">{ES(pz[ck][key],1)} %</text>')
            x += wseg
    lx = ML
    for ck, cname, cls in order:
        s.append(f'<rect x="{lx}" y="{h-22}" width="11" height="11" rx="2" class="seg {cls}"/>')
        s.append(f'<text x="{lx+17}" y="{h-12}" class="legend">{cname}</text>')
        lx += 26 + len(cname)*7.6
    return f'<svg viewBox="0 0 {W} {h}" class="chart" role="img" aria-label="Comparación de peso en pares y en importe por clase de par cliente-SKU">{"".join(s)}</svg>'

# ---------------------------------------------- 6. zona: ruta vs CEDIS vs global
def chart_zona():
    h, mb = 280, 52
    z = P["zona_vs_global"]
    iw, ih = W-ML-MR, h-MT-mb
    ymax = 80; ticks = [0,20,40,60,80]
    grupo = iw/len(z); bw = grupo/3.6
    s = [axes(h, mb, ticks, ymax, lambda v: f"{v:.0f}%")]
    series = [("recall_ruta","s1","Su ruta"),("recall_cedis","s3","Su CEDIS"),
              ("recall_global","s2o","Global")]
    for i, zz in enumerate(z):
        x0 = ML + i*grupo + grupo/2 - bw*1.5 - 4
        for k,(key,cls,lbl) in enumerate(series):
            v = zz[key]; bh = (v/ymax)*ih
            x = x0 + k*(bw+4); y = MT+ih-bh
            s.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{bw:.1f}" height="{bh:.1f}" rx="3" '
                     f'class="bar {cls}" data-tip="top-{zz["N"]} de {lbl}: {ES(v,1)} % de cobertura"/>')
            s.append(f'<text x="{x+bw/2:.1f}" y="{y-7:.1f}" class="blabel">{ES(v,1)}</text>')
        s.append(f'<text x="{ML+i*grupo+grupo/2:.1f}" y="{h-mb+22}" class="xtick str">top-{zz["N"]}</text>')
    lx = ML
    for key,cls,lbl in series:
        s.append(f'<rect x="{lx}" y="{h-20}" width="11" height="11" rx="2" class="bar {cls}"/>')
        s.append(f'<text x="{lx+17}" y="{h-10}" class="legend">{lbl}</text>')
        lx += 26 + len(lbl)*7.4
    s.append(f'<text x="{W-MR}" y="{h-10}" class="axlabel" text-anchor="end">'
             f'% del surtido histórico del cliente cubierto por la lista</text>')
    return f'<svg viewBox="0 0 {W} {h}" class="chart" role="img" aria-label="Cobertura del surtido por ruta, CEDIS y global">{"".join(s)}</svg>'

# ------------------------------------------------------ 7. concentración (Pareto)
def chart_pareto():
    h, mb = 250, 46
    pts = P["concentracion"]["pareto"]
    iw, ih = W-ML-MR, h-MT-mb
    xmax = 538; ymax = 100; ticks=[0,25,50,75,100]
    X = lambda n: ML + (n/xmax)*iw
    Y = lambda v: MT + ih - (v/ymax)*ih
    s = [axes(h, mb, ticks, ymax, lambda v: f"{v:.0f}%")]
    seq = [(0,0.0)] + [(p["n"], p["pct"]) for p in pts]
    s.append(f'<polyline points="{" ".join(f"{X(n):.1f},{Y(v):.1f}" for n,v in seq)}" class="line s1"/>')
    for n, v in seq[1:]:
        s.append(f'<circle cx="{X(n):.1f}" cy="{Y(v):.1f}" r="4" class="dot s1" '
                 f'data-tip="{ES(n)} productos = {ES(v,1)} % del importe"/>')
    for n, v, lbl in [(55,50.0,"55 productos"),(156,80.0,"156"),(283,95.0,"283")]:
        s.append(f'<line x1="{ML}" y1="{Y(v):.1f}" x2="{X(n):.1f}" y2="{Y(v):.1f}" class="grid" stroke-dasharray="3 3"/>')
        s.append(f'<text x="{X(n)+8:.1f}" y="{Y(v)+4:.1f}" class="dlabel c1">{lbl} = {ES(v,0)} %</text>')
    for n in (0,100,200,300,400,538):
        s.append(f'<text x="{X(n):.1f}" y="{h-mb+22}" class="xtick">{n}</text>')
    s.append(f'<text x="{ML+iw/2:.1f}" y="{h-8}" class="axlabel">productos ordenados por importe (de mayor a menor)</text>')
    return f'<svg viewBox="0 0 {W} {h}" class="chart" role="img" aria-label="Curva de concentración del importe por producto">{"".join(s)}</svg>'

# ------------------------------------ 8. adopción de productos nuevos por visita
def chart_adopcion():
    h, mb = 250, 50
    det = T["adopcion_por_visita"]["detalle"]
    iw, ih = W-ML-MR, h-MT-mb
    ymax = 32; ticks = [0,10,20,30]
    bw = iw/len(det)
    s = [axes(h, mb, ticks, ymax, lambda v: f"{v:.0f}%")]
    for i, r in enumerate(det):
        bh = (r["pct"]/ymax)*ih
        x = ML + i*bw + 14; y = MT+ih-bh
        s.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{bw-28:.1f}" height="{bh:.1f}" rx="3" '
                 f'class="bar {"mut" if i==0 else "acc"}" '
                 f'data-tip="Visita {r["visita"]}: {ES(r["nuevos"])} productos nuevos ({ES(r["pct"],1)} %)"/>')
        s.append(f'<text x="{x+(bw-28)/2:.1f}" y="{y-8:.1f}" class="blabel">{ES(r["pct"],1)} %</text>')
        s.append(f'<text x="{x+(bw-28)/2:.1f}" y="{h-mb+22}" class="xtick str">{r["visita"]}ª</text>')
    s.append(f'<text x="{ML+iw/2:.1f}" y="{h-8}" class="axlabel">visita del mes</text>')
    return f'<svg viewBox="0 0 {W} {h}" class="chart" role="img" aria-label="Adopción de productos nuevos según la visita del mes">{"".join(s)}</svg>'

# ------------------------------ 9. composición de la canasta: nunca/dormido/habitual
def chart_composicion():
    h = 176
    comp = T["composicion_canasta"]["por_ventana"]
    iw = W - ML - MR
    orden = [("nunca", "Nunca comprado", "s1"), ("dormido", "Dormido", "s3"),
             ("habitual", "Habitual", "s2")]
    s = []
    for ri, (v, d) in enumerate(comp.items()):
        y = 30 + ri * 44
        s.append(f'<text x="{ML-10}" y="{y+20:.0f}" class="ytick">{v} mes{"es" if v!="1" else ""}</text>')
        x = ML
        for k, nom, cls in orden:
            w = d[k] / 100 * iw
            s.append(f'<rect x="{x:.1f}" y="{y}" width="{max(w-2,1):.1f}" height="30" rx="3" '
                     f'class="seg {cls}" data-tip="{nom}, ventana {v} mes: {ES(d[k],1)} %"/>')
            if w > 60:
                s.append(f'<text x="{x+w/2-1:.1f}" y="{y+20:.0f}" class="seglabel">{ES(d[k],1)} %</text>')
            x += w
    lx = ML
    for k, nom, cls in orden:
        s.append(f'<rect x="{lx}" y="{h-20}" width="11" height="11" rx="2" class="seg {cls}"/>')
        s.append(f'<text x="{lx+17}" y="{h-10}" class="legend">{nom}</text>')
        lx += 26 + len(nom) * 7.4
    return f'<svg viewBox="0 0 {W} {h}" class="chart" role="img" aria-label="Composición de la canasta mensual por tipo de producto">{"".join(s)}</svg>'

CHARTS = dict(composicion=chart_composicion(), adopcion=chart_adopcion(), zona=chart_zona(), pareto=chart_pareto(), mensual=chart_mensual(), intervalo=chart_intervalo(), freq=chart_freq(),
              repertorio=chart_repertorio(), peso=chart_peso())
g,f,sp,iv,es = d["grano"],d["frecuencia_resumen"],d["sparsity"],d["intervalo"],d["estabilidad_repertorio"]
seg = {r["segmento"]: r for r in d["segmentos"]}
tpl = open(SRC / "plantilla_dashboard.html", encoding="utf-8").read()
for k,v in CHARTS.items(): tpl = tpl.replace(f"{{{{{k}}}}}", v)
# cifras derivadas para la lectura comercial
_sinventa = g["visitas"] - g["compras"]
_imp_tot = sum(r["importe"] for r in d["mensual"])
_ticket = _imp_tot / g["compras"]
_nocompra = g["skus"] - sp["skus_por_cliente_mediana"]

_af = P["afinidad"]["top_frecuencia"][:8]
repl_afinidad = "".join(
    f'<tr><td>{a["a"]}</td><td>{a["b"]}</td><td class="n">{ES(a["co"])}</td>'
    f'<td class="n">{ES(a["lift"],1)}</td><td class="n">{ES(a["conf"],1)} %</td></tr>'
    for a in _af)

S = lambda k: seg[k]
repl = {
 "{{visitas}}": ES(g["visitas"]), "{{compras}}": ES(g["compras"]),
 "{{conv}}": ES(g["tasa_conversion_visita"],1), "{{clientes}}": ES(g["clientes_que_compraron"]),
 "{{skus}}": ES(g["skus"]), "{{pctmulti}}": ES(f["pct_mas_de_una"],1),
 "{{media_compras}}": ES(f["media"],2), "{{visitas_mes}}": ES(f["visitas_media"],2),
 "{{conv_cm}}": ES(f["conversion_visita_compra"],1), "{{pct7}}": ES(iv["pct_7d"],1),
 "{{dens}}": ES(sp["densidad_pct"],3), "{{pares}}": ES(sp["pares_observados"]),
 "{{skucli}}": ES(sp["skus_por_cliente_mediana"]), "{{sku80}}": ES(sp["skus_80pct_importe"]),
 "{{recacum}}": ES(d["recompra_acumulada"][-1]["pct_ya_comprado"],1),
 "{{recady}}": ES(d["recompra"][-1]["pct_skus_repetidos"],1),
 "{{nuevos_sku}}": ES(d["recompra_acumulada"][-1]["skus_nunca_comprados"],2),
 "{{oneoff}}": ES(es["pct_one_off"],1), "{{core}}": ES(es["pct_core_3plus"],1),
 "{{n_alta}}": ES(S("Alta frecuencia (semanal)")["clientes"]), "{{p_alta}}": ES(S("Alta frecuencia (semanal)")["pct"],1),
 "{{n_media}}": ES(S("Media (quincenal)")["clientes"]), "{{p_media}}": ES(S("Media (quincenal)")["pct"],1),
 "{{n_baja}}": ES(S("Baja (mensual)")["clientes"]), "{{p_baja}}": ES(S("Baja (mensual)")["pct"],1),
 "{{n_esp}}": ES(S("Esporádico / abandonó")["clientes"]), "{{p_esp}}": ES(S("Esporádico / abandonó")["pct"],1),
 "{{n_cens}}": ES(S("Sin historia suficiente")["clientes"]), "{{p_cens}}": ES(S("Sin historia suficiente")["pct"],1),
}
_sr = d["segmentacion_regla"]
for _k, _v, _dc in [("cl_regla", _sr["clasificados"], 0), ("cens_regla", _sr["censurados"], 0),
                    ("fr_am", _sr["frontera_alta_media"], 1), ("fr_mb", _sr["frontera_media_baja"], 1),
                    ("p12m", _sr["pct_12_meses"], 1), ("alta12", _sr["alta_activos_12m"], 1)]:
    repl["{{"+_k+"}}"] = ES(_v, _dc)
_cd = P["calidad_dim"]; _cc = P["concentracion"]; _cv = P["ciclo_vida"]
repl["{{afinidad_tabla}}"] = repl_afinidad
for _k,_v,_dd in [("prod_total",_cd["skus_mercancia"],0),("prod_promo",_cd["skus_promocion"],0),
                  ("prod_recom",P["recomendables"],0),("prod_exhib",P["exhibidores"],0),
                  ("prod_activos",_cv["activos_ult2m"],0),("prod_muertos",_cv["descontinuados"],0),
                  ("pct_lineas_promo",_cd["pct_lineas_promocion"],1),
                  ("sku50",_cc["skus_50pct"],0),("sku80",_cc["skus_80pct"],0),
                  ("penetr",_cc["penetracion_mediana_pct"],2),
                  ("rec_mediana",P["recompra_sku"]["mediana_pct_core"],1),
                  ("jac_mismo",P["jaccard_rutas"]["mismo_cedis"],3),
                  ("jac_dist",P["jaccard_rutas"]["distinto_cedis"],3),
                  ("canastas_af",P["afinidad"]["canastas"],0),
                  ("mismamarca",P["afinidad"]["misma_marca_pct"],1)]:
    repl["{{"+_k+"}}"] = ES(_v,_dd)
for _i,_z in enumerate(P["zona_vs_global"]):
    repl["{{z%d_ruta}}"%_z["N"]] = ES(_z["recall_ruta"],1)
    repl["{{z%d_ced}}"%_z["N"]] = ES(_z["recall_cedis"],1)
    repl["{{z%d_glob}}"%_z["N"]] = ES(_z["recall_global"],1)
_av = T["adopcion_por_visita"]
_cc = T["composicion_canasta"]
repl["{{dormidos_cli}}"] = ES(_cc["dormidos_por_cliente"],1)
repl["{{tasa_react}}"] = ES(_cc["tasa_reactivacion_pct"],2)
repl["{{tasa_desc}}"] = ES(_cc["tasa_descubrimiento_pct"],2)
repl["{{veces}}"] = ES(_cc["veces_mas_probable"],1)
repl["{{pct_dormido2}}"] = ES(_cc["por_ventana"]["2"]["dormido"],1)
repl["{{pct_nunca}}"] = ES(_cc["por_ventana"]["2"]["nunca"],1)
repl["{{pct_habitual2}}"] = ES(_cc["por_ventana"]["2"]["habitual"],1)
repl["{{pct_tras_v1}}"] = ES(_av["pct_tras_primera_visita"],1)
repl["{{cli_2v}}"] = ES(_av["clientes_2plus_visitas"])
repl["{{pct_v1}}"] = ES(_av["detalle"][0]["pct"],1)
repl["{{sinventa}}"] = ES(_sinventa)
repl["{{ticket}}"] = ES(_ticket)
repl["{{nocompra}}"] = ES(_nocompra)
repl["{{pct_sinventa}}"] = ES(_sinventa / g["visitas"] * 100, 1)
for _k, _lbl in [("alta","Alta frecuencia (semanal)"),("media","Media (quincenal)"),
                 ("baja","Baja (mensual)"),("esp","Esporádico / abandonó"),
                 ("cens","Sin historia suficiente")]:
    repl["{{c_"+_k+"}}"] = ES(S(_lbl)["compras_mes"],2)
    repl["{{k_"+_k+"}}"] = ES(S(_lbl)["skus_mes"],1)
    repl["{{i_"+_k+"}}"] = ES(S(_lbl)["pct_imp"],1)
    repl["{{a_"+_k+"}}"] = ES(S(_lbl)["imp_cli"])
for k,v in repl.items(): tpl = tpl.replace(k,v)
open(INFORMES / "dashboard.html","w",encoding="utf-8").write(tpl)
left = [t for t in ["{{"] if t in tpl]
print("dashboard.html generado" + ("  OJO: quedan placeholders sin sustituir" if "{{" in tpl else ""))
