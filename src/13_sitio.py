"""Genera el sitio estático del informe final.

Salida: sitio/index.html — un solo archivo, sin dependencias salvo la hoja de
fuentes de Google. Se despliega copiándolo a un bucket de S3 o Cloud Storage.

Dos versiones en el mismo documento, conmutables: negocio y técnico.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from comun import RAIZ, RESULTADOS
from sitio import graficos as G
from sitio.graficos import ES

# Base para el enlace al análisis exploratorio.
#
# Servido desde storage.cloud.google.com, Google entrega el archivo desde otro
# host (*.googleusercontent.com) tras autenticar, así que un enlace RELATIVO se
# resuelve contra ese dominio y falla. Con --base se escribe absoluto.
#
#   ./.venv/bin/python src/13_sitio.py --base https://storage.cloud.google.com/mi-bucket
BASE = ""
if "--base" in sys.argv:
    BASE = sys.argv[sys.argv.index("--base") + 1].rstrip("/") + "/"

D = json.load(open(RESULTADOS / "eda_resultados.json"))
P = json.load(open(RESULTADOS / "eda_productos.json"))
T = json.load(open(RESULTADOS / "diag_techo.json"))
R = json.load(open(RESULTADOS / "poc.json"))
p4_path = RESULTADOS / "p4.json"
P4 = json.load(open(p4_path)) if p4_path.exists() else None

MOD = ["B0", "B1", "P1", "P2", "P3"]
NOM = {"B0": "B0 · popularidad global", "B1": "B1 · popularidad de ruta",
       "P1": "P1 · ruta + marca", "P2": "P2 · afinidad", "P3": "P3 · ranker",
       "P4": "P4 · por segmento"}
LIB = R["politicas"]["libre"]
MIX = R["politicas"]["mixta"]


def tabla(cabeceras, filas, clases=None):
    v = ""
    th = "".join(f"<th>{c}</th>" for c in cabeceras)
    tr = []
    for i, f in enumerate(filas):
        cl = f' class="{clases[i]}"' if clases and clases[i] else ""
        td = "".join(f'<td class="n">{c}</td>' if j else f"<td>{c}</td>"
                     for j, c in enumerate(f))
        tr.append(f"<tr{cl}>{td}</tr>")
    return (f'<div class="tw"{v}><table><thead><tr>{th}</tr></thead>'
            f'<tbody>{"".join(tr)}</tbody></table></div>')


def plain(titulo, cuerpo, warn=False):
    return (f'<div class="plain{" warn" if warn else ""}">'
            f'<div class="tag">{titulo}</div>{cuerpo}</div>')


# ══════════════════════════════════════════════════════ 1. DATOS
g = D["grano"]
cal = P["calidad_dim"]
s1 = f"""
<section id="contexto">
  <div class="snum">01 · Punto de partida</div>
  <h2>Qué hay en la base de datos</h2>
  <p class="lead">Un solo archivo de respaldo de SQL Server con <strong>una tabla</strong>,
  <strong>5.328.903 renglones de venta</strong> y doce meses exactos de preventa
  —del 1 de septiembre de 2025 al 27 de agosto de 2026— en dos centros de distribución.</p>

  <div class="stats">
    <div class="stat"><span class="v mono">{ES(g['visitas'])}</span><span class="k">visitas de preventista</span></div>
    <div class="stat"><span class="v mono">{ES(g['compras'])}</span><span class="k">terminaron en pedido</span></div>
    <div class="stat hi"><span class="v mono">{ES(g['tasa_conversion_visita'],1)} %</span><span class="k">de las visitas convierten</span></div>
    <div class="stat"><span class="v mono">{ES(g['clientes_que_compraron'])}</span><span class="k">clientes</span></div>
    <div class="stat"><span class="v mono">{ES(cal['skus_mercancia'])}</span><span class="k">productos reales</span></div>
  </div>

  {plain("Lo que hay que saber de entrada", f'''
    <p>El catálogo <strong>aparenta 883 productos, pero solo {ES(cal['skus_mercancia'])} son
    mercancía</strong>. Los otros {ES(cal['skus_promocion'])} son registros de mecánica
    promocional con importe cero: no mueven un peso, pero ocupan el
    {ES(cal['pct_lineas_promocion'],1)} % de los renglones.</p>
    <p>Descontando además exhibidores y productos sin venta reciente, quedan
    <strong>{ES(P['recomendables'])} productos que tiene sentido recomendar</strong>.
    Cualquier análisis que no haga esa limpieza cuenta mal.</p>''')}

  {plain("Advertencias sobre los datos", '''
    <ul>
      <li><b>El primer y el último mes están incompletos.</b> Septiembre de 2025 es donde
      arranca el archivo; agosto de 2026 corta un jueves y le faltan viernes y sábado.</li>
      <li><b>Noviembre de 2025 no registró las visitas sin pedido</b>, así que aparenta
      100 % de efectividad.</li>
      <li><b>Junio de 2026 no es temporada alta:</b> se abrieron 24 rutas de preventa.</li>
      <li><b>El código de promoción no discrimina:</b> viene lleno en casi todos los renglones.</li>
    </ul>''', warn=True)}
</section>
"""

# ══════════════════════════════════════════════════════ 2. CLIENTES
f = D["frecuencia_resumen"]
iv = D["intervalo"]
av = T["adopcion_por_visita"]
hist_int = {x["dias"]: x["n"] for x in iv["hist"]}
g_int = G.barras([(str(d), hist_int.get(d, 0)) for d in range(1, 30)],
                 "Días entre una compra y la siguiente", ymax=440000,
                 fmt_y=lambda v: f"{v/1000:.0f}k", unidad="", h=250, mb=42,
                 destacar={"7", "14", "21", "28"},
                 etiqueta_x="días entre una compra y la siguiente")
# datos que usa el resumen (venían de la sección de productos, ahora fundida)
cc = T["composicion_canasta"]
conc = P["concentracion"]
af = P["afinidad"]
zz = {z["N"]: z for z in P["zona_vs_global"]}

s2 = f"""
<section id="datos">
  <div class="snum">02 · Lo que encontramos en los datos</div>
  <h2>Cinco cosas que cambian cómo hay que abordar el problema</h2>
  <p class="lead">El análisis exploratorio completo —comportamiento de clientes, estructura del
  catálogo, afinidades y calidad de los datos— está en un documento aparte. Aquí va solo lo que
  condiciona el modelo.</p>

  <div class="grid2">
    <div class="tk"><h3>El «cuándo» ya está resuelto</h3>
      <p>El {ES(iv['pct_7d'],1)} % de los intervalos entre compras son de exactamente siete días:
      el cliente compra el día que le toca visita. <b>No hay que predecir el momento, sino qué
      ofrecer cuando llegue.</b></p></div>

    <div class="tk"><h3>El catálogo real es la mitad</h3>
      <p>De los 883 códigos, <b>{ES(cal['skus_mercancia'])} son mercancía</b>; el resto son
      registros de promoción con importe cero. Descontando exhibidores y productos sin venta
      reciente quedan <b>{ES(P['recomendables'])} recomendables</b>.</p></div>

    <div class="tk"><h3>La zona sí importa, y es la ruta</h3>
      <p>El top-50 de la ruta cubre el {ES(zz[50]['recall_ruta'],1)} % de lo que compra un cliente,
      contra {ES(zz[50]['recall_global'],1)} % de la lista global. Y <b>no es surtido de almacén:
      el CEDIS no explica nada</b> ({ES(zz[50]['recall_cedis'],1)} %).</p></div>

    <div class="tk"><h3>La afinidad es de línea de sabor</h3>
      <p>Quien lleva un sabor se lleva los demás. Sobre {ES(af['canastas'])} canastas, los pares
      más frecuentes son variantes del mismo producto — una pista fácil de explotar y de explicar
      al preventista.</p></div>

    <div class="tk"><h3>La oportunidad más cercana ya está en casa</h3>
      <p>Un cliente ha comprado {ES(D['sparsity']['skus_por_cliente_mediana'],0)} productos
      distintos en el año pero pide unos {ES(D['canasta']['skus_por_cliente_mes_media'],1)} al mes.
      Son <b>{ES(cc['dormidos_por_cliente'],1)} productos que ya conoce y no está pidiendo</b>.</p></div>
  </div>

  <div class="callout">
    <div class="co-txt">
      <h3>Análisis exploratorio completo</h3>
      <p>Doce meses de preventa en detalle: ritmo de compra, segmentos de cliente, estructura del
      catálogo, concentración, afinidades, calidad de los datos y sus advertencias. Cada bloque
      cierra con una lectura en lenguaje llano.</p>
    </div>
    <a class="co-btn" href="{BASE}analisis-exploratorio.html">Abrir el análisis →</a>
  </div>

  {plain("Las advertencias que hay que tener presentes", '''
    <ul>
      <li><b>El primer y el último mes están incompletos</b> — septiembre de 2025 es donde arranca
      el archivo y agosto de 2026 corta un jueves.</li>
      <li><b>Junio de 2026 no es temporada alta:</b> se abrieron 24 rutas de preventa.</li>
      <li><b>El código de promoción no sirve como está:</b> viene lleno en casi todos los renglones.</li>
      <li><b>Un solo ciclo anual:</b> tendencia y estacionalidad no se pueden separar.</li>
    </ul>''', warn=True)}
</section>
"""

# ══════════════════════════════════════════════════════ 4. METODOLOGÍA
imp = R["importancias"]
ETIQ_VAR = {"es_dormido": "ya lo compró", "peso_marca": "peso de marca",
            "afin_max": "afinidad máx.", "pop_global": "popularidad global",
            "pop_ruta": "popularidad ruta", "rango_ruta": "rango en ruta",
            "afin_suma": "afinidad suma", "pct_core": "retención del producto",
            "meses_disponible": "meses disponible", "n_skus_cliente": "surtido del cliente",
            "n_compras_cliente": "compras del cliente", "ticket_medio": "ticket medio",
            "marca_conocida": "marca conocida", "skus_de_la_marca": "SKU de la marca"}
g_imp = G.barras_h([(ETIQ_VAR.get(r["variable"], r["variable"]), r["pct"]) for r in imp],
                   "Cuánto aporta cada variable a las decisiones del modelo",
                   destacar={ETIQ_VAR.get(imp[0]["variable"]), ETIQ_VAR.get(imp[1]["variable"])},
                   nota_eje="% de la señal que usa el modelo")
s4 = f"""
<section id="metodo">
  <div class="snum">04 · Metodología</div>
  <h2>Cómo se comparó, para que la comparación signifique algo</h2>
  <p class="lead">Se reconstruyó la lógica del sistema actual como línea base y se midieron
  cuatro alternativas <strong>sobre el mismo conjunto de candidatos, el mismo mes y la misma
  población</strong>. Sin eso, cualquier diferencia sería del método y no del modelo.</p>

  <ol class="pasos">
    <li><b>Qué se recomienda.</b> Solo productos que el cliente <b>no pidió en los últimos dos
    meses</b>. Lo que ya viene comprando queda fuera: lo iba a pedir igual, y acertarle infla el
    número sin generar venta.</li>
    <li><b>Contra qué se compara.</b> B1 reproduce el sistema actual: ordenar por popularidad entre
    clientes de la misma ruta. <b>Es una reconstrucción</b>, porque la empresa no conserva las
    recomendaciones que su sistema generó.</li>
    <li><b>Cómo se evita hacer trampa.</b> Toda variable del mes se calcula solo con meses
    anteriores. Se entrena con febrero a abril, se valida con mayo y <b>se prueba con julio</b>,
    que el modelo nunca vio. Junio queda fuera: es el mes de la expansión de rutas.</li>
    <li><b>Cuándo se considera exitoso.</b> El umbral —superar a B1 por 5 puntos— se fijó
    <b>antes</b> de ver resultados, para no acomodarlo después.</li>
    <li><b>Cuántas sugerencias.</b> Ocho por cliente al mes, que es lo que hoy emite el
    sistema actual, ordenadas por la puntuación de cada modelo.</li>
  </ol>

  <div>
    <h3 style="margin-top:40px">Los cinco modelos</h3>
    {tabla(["Modelo", "Criterio de orden"], [
        ["B0 · popularidad global", "el producto más vendido en toda la operación"],
        ["B1 · popularidad de ruta", "el más vendido entre clientes de su ruta (sistema actual)"],
        ["P1 · ruta + marca", "B1 anteponiendo marcas que el cliente ya compra"],
        ["P2 · afinidad", "co-ocurrencia con lo que el cliente ya lleva"],
        ["P3 · ranker", "LightGBM LambdaRank sobre quince variables"],
    ])}
  </div>

  {plain("En una frase", '''
    <p>Se le tapó la respuesta al modelo: aprendió con datos hasta abril y se le pidió adivinar qué
    compraría cada cliente en julio, <strong>un mes que nunca vio</strong>. Luego se comparó contra
    lo que realmente compró.</p>''')}
</section>
"""

# ══════════════════════════════════════════════════════ 4b. LAS VARIABLES
FAMILIAS = [
    ("Lo que compra gente parecida", [
        ("pop_ruta", "popularidad en su ruta",
         "Cuántos clientes de la misma ruta de preventa han comprado ese producto. "
         "Es la única señal que usa el sistema actual."),
        ("rango_ruta", "posición en su ruta",
         "En qué lugar queda el producto dentro del ranking de su ruta: 1 es el más vendido. "
         "Dice lo mismo que la anterior pero en escala comparable entre rutas."),
        ("pop_global", "popularidad general",
         "Cuántos clientes en toda la operación lo compran, sin importar la zona."),
    ]),
    ("Con qué marcas trabaja el cliente", [
        ("peso_marca", "peso de la marca en su canasta",
         "Qué fracción de todo lo que compra el cliente es de esa marca. Un tendero que dedica "
         "el 30 % de su pedido a una marca es candidato natural para el resto de esa marca."),
        ("marca_conocida", "¿ya compra la marca?",
         "Sí o no. Del EDA salió que 4 de cada 5 productos nuevos que adopta un cliente son de "
         "una marca que ya le vende."),
        ("skus_de_la_marca", "cuántos productos de esa marca ya lleva",
         "Si ya tiene ocho productos de una marca, el noveno es una venta más fácil que el primero."),
    ]),
    ("Qué va junto con qué", [
        ("afin_max", "afinidad más alta",
         "De todo lo que el cliente ya compra, cuántas veces el producto candidato aparece en la "
         "misma canasta que el más afín. Captura el patrón de línea de sabor: quien lleva "
         "Whiskas atún lleva salmón."),
        ("afin_suma", "afinidad acumulada",
         "Lo mismo pero sumando sobre todos los productos que lleva, no solo el más afín. "
         "Distingue al que tiene una sola coincidencia fuerte del que tiene muchas medianas."),
    ]),
    ("Cómo es el producto", [
        ("precio", "precio unitario",
         "Importe dividido entre piezas. Un producto de 20 pesos y uno de 900 no se ofrecen igual."),
        ("pct_core", "retención del producto",
         "Qué fracción de quienes lo compran lo vuelven habitual (lo piden en tres meses o más). "
         "Separa los productos que enganchan de los que se prueban una vez."),
        ("meses_disponible", "antigüedad en catálogo",
         "En cuántos meses del periodo se ha vendido. Un lanzamiento reciente tiene menos "
         "historia y se comporta distinto."),
        ("es_dormido", "¿ya lo había comprado?",
         "Si el cliente compró ese producto antes, aunque haya dejado de pedirlo. "
         "Recordarle algo que ya conoce es más fácil que presentarle algo nuevo."),
    ]),
    ("Cómo es el cliente", [
        ("n_skus_cliente", "amplitud de su surtido",
         "Cuántos productos distintos ha comprado. Un cliente de surtido amplio acepta "
         "sugerencias que uno de surtido corto rechazaría."),
        ("n_compras_cliente", "frecuencia de compra",
         "Cuántas veces ha comprado en el periodo."),
        ("ticket_medio", "tamaño de su pedido",
         "Importe medio por compra. Acota qué rango de precio tiene sentido ofrecerle."),
    ]),
]
_pct = {r["variable"]: r["pct"] for r in imp}
_bloques = []
for fam, vs in FAMILIAS:
    _bloques.append(f'<div class="vfam">{fam}</div>')
    for var, nom, desc in vs:
        pc = _pct.get(var, 0)
        cl = "var" if pc >= 3 else "var baja"
        _bloques.append(f'<div class="{cl}"><div class="vn">{nom}</div>'
                        f'<div class="vd">{desc}</div>'
                        f'<div class="vp">{ES(pc,1)} %</div></div>')
_top2 = imp[0]["pct"] + imp[1]["pct"]
s4b = f"""
<section id="variables">
  <div class="snum">04 · Las variables</div>
  <h2>Qué mira el modelo para decidir</h2>
  <p class="lead">Quince señales, agrupadas en cinco familias. El porcentaje de la derecha es
  <strong>cuánto aporta cada una a las decisiones del modelo</strong>: los que superan el 3 %
  están en azul.</p>

  <div class="card">{g_imp}</div>

  <div class="vars">{"".join(_bloques)}</div>

  {plain("La conclusión que deja esta tabla", f'''
    <p><strong>El peso de la marca y la afinidad entre productos concentran el {ES(_top2,1)} %
    de lo que usa el modelo.</strong> Ninguna de las dos la mira el sistema actual.</p>
    <p>Y al revés: la popularidad en la ruta —la única señal del sistema de hoy— aporta
    <strong>{ES(_pct.get('pop_ruta',0),1)} %</strong>. No es que no sirva: es que ya está
    exprimida, y lo que queda por ganar está en otro lado.</p>''')}
</section>
"""

# ══════════════════════════════════════════════════════ 5. RESULTADOS
def _leer(fuente, m):
    """POC y P4 guardan con estructuras distintas; aquí se unifican."""
    if "hit_rate_8" in fuente:                     # bloque del POC
        return (fuente["hit_rate_8"][m], fuente["desglose"][m],
                fuente["negocio"][m]["pct_descubrimiento"])
    b = fuente[m]                                  # bloque de P4
    return b["hit_rate"], b["desglose"], b["negocio"]["pct_descubrimiento"]


def fila_mod(fuente, m):
    hr, g, _ = _leer(fuente, m)
    base, gb, _ = _leer(fuente, "B1")
    acertados = sum(g.values())
    vs_base = acertados - sum(gb.values())
    dif = hr - base
    marca = "—" if m == "B1" else ("+" if dif >= 0 else "−") + ES(abs(dif), 2)
    extra = "—" if m == "B1" else ("+" if vs_base >= 0 else "−") + ES(abs(vs_base))
    return [NOM[m], ES(acertados), extra, f"{ES(hr,2)} %", marca]

P4L = P4["prueba"]["libre"] if P4 else None
CAB = ["Modelo", "SKU acertados", "vs actual", "Clientes con acierto", "vs actual"]
filas_l = [fila_mod(LIB, m) for m in MOD] + ([fila_mod(P4L, "P4")] if P4 else [])
cls_l = ["", "dest", "", "", "", ""][:len(filas_l)]
neg = LIB["negocio"]["P3"]
_acert = [(NOM[m].split(" · ")[1].capitalize(), sum(_leer(LIB, m)[1].values())) for m in MOD]
if P4:
    _acert.append(("Por segmento", sum(P4L["P4"]["desglose"].values())))
g_res = G.barras_h(_acert, "Productos acertados por cada modelo", unidad="",
                   destacar={"Ranker", "Por segmento"},
                   fmt=lambda v: f"{ES(v)} SKU",
                   nota_eje=f"sobre {ES(R['clientes_evaluados'])} clientes, 8 sugerencias a cada uno")
esc = LIB["escenarios"]
fil_esc = [[f"{ES(e['tasa_conversion']*100,0)} %", ES(e["mensual"]), ES(e["anual"])] for e in esc]

s5 = f"""
<section id="resultados">
  <div class="snum">05 · Resultados</div>
  <h2>El modelo supera al sistema actual en 10 puntos</h2>
  <p class="lead">De cada 100 clientes visitados, el sistema actual le atina a algo nuevo en
  <strong>{ES(LIB['hit_rate_8']['B1'],0)}</strong>. El modelo entrenado, en
  <strong>{ES(LIB['hit_rate_8']['P3'],0)}</strong>.</p>

  <div class="stats">
    <div class="stat"><span class="v mono">{ES(LIB['hit_rate_8']['B1'],1)} %</span><span class="k">sistema actual (B1)</span></div>
    <div class="stat hi"><span class="v mono">{ES(LIB['hit_rate_8']['P3'],1)} %</span><span class="k">modelo entrenado (P3)</span></div>
    <div class="stat"><span class="v mono">+{ES(LIB['hit_rate_8']['P3']-LIB['hit_rate_8']['B1'],2)}</span><span class="k">puntos de mejora</span></div>
    <div class="stat"><span class="v mono">{ES(neg['sku_extra_por_compra'],2)}</span><span class="k">SKU extra por compra</span></div>
  </div>

  <div class="card">{g_res}</div>

  <h3 style="margin-top:38px">Cuántos productos acertó cada modelo</h3>
  <p class="t">Sobre {ES(R['clientes_evaluados'])} clientes y 8 sugerencias a cada uno.
  <strong>«SKU acertados» es el total de productos sugeridos que el cliente efectivamente
  compró</strong> ese mes.</p>
  {tabla(CAB, filas_l, ["", "dest"] + [""] * (len(filas_l) - 2))}

  <p class="nota"><b>P4</b> es un refinamiento: usa el sistema actual para
  los clientes de los que casi no se sabe nada —menos de cinco productos comprados— y el modelo
  entrenado para el resto. Aporta poco al promedio, pero <b>garantiza que ningún cliente reciba
  algo peor de lo que ya recibe hoy</b>.</p>

  <div>
    <h3 style="margin-top:38px">P4 — un modelo por segmento</h3>
    <p class="t">El ranker necesita historia: sus dos variables principales se calculan sobre
    compras pasadas. Midiendo sobre mayo qué modelo gana en cada tramo, <strong>P3 solo pierde con
    menos de 5 productos comprados</strong> — el {ES(P4['por_tramo_validacion'][0]['clientes']/
    sum(t['clientes'] for t in P4['por_tramo_validacion'])*100,1) if P4 else '—'} % de la base.</p>
    {tabla(["Historia del cliente", "Clientes", "B1", "P1", "P2", "P3", "Mejor"],
           [[t["tramo"] + " SKU", ES(t["clientes"]), f"{ES(t['B1'],1)} %", f"{ES(t['P1'],1)} %",
             f"{ES(t['P2'],1)} %", f"{ES(t['P3'],1)} %", t["mejor"]]
            for t in P4["por_tramo_validacion"]]) if P4 else ""}
    <p class="nota">El umbral se eligió <b>sobre mayo</b> y se aplicó a ciegas sobre julio:
    buscarlo sobre el mes de prueba habría sido ajustar contra la respuesta.
    Resultado: <b>P4 alcanza {ES(P4L['P4']['hit_rate'],2) if P4 else '—'} %</b> contra
    {ES(P4L['P3']['hit_rate'],2) if P4 else '—'} % de P3 — apenas +{ES(P4L['P4']['hit_rate']-P4L['P3']['hit_rate'],2) if P4 else '—'} puntos,
    porque el tramo donde P3 falla es pequeño. <b>Su valor no es la métrica sino la garantía de que
    ningún cliente recibe algo peor que el sistema actual.</b></p>
  </div>

  <h3 style="margin-top:38px">Traducción a pesos</h3>
  <p class="t">Con 8 sugerencias por cliente al mes, el modelo acierta
  <strong>{ES(neg['aciertos_por_cliente'],2)} productos por cliente</strong>, equivalentes a
  <strong>{ES(neg['sku_extra_por_compra'],2)} SKU adicionales en cada visita</strong> y
  {ES(neg['importe_por_cliente'],0)} pesos por cliente al mes.</p>
  {tabla(["Si se convierte…", "Impacto mensual", "Impacto anual"], fil_esc)}

  {plain("Por qué no hay una cifra única de impacto", '''
    <p>Los datos dicen si el modelo <strong>acierta</strong> qué comprará el cliente, no si la
    sugerencia lo <strong>causó</strong>. Puede que lo hubiera comprado de todos modos.</p>
    <p>Por eso el impacto se presenta con la perilla a la vista: cada fila supone que una fracción
    distinta de los aciertos no habría ocurrido sin la sugerencia. <strong>Lo único que mide
    impacto real es un piloto con grupo de control</strong> — y eso es lo que viene.</p>''',
    warn=True)}
</section>
"""
# ══════════════════════════════════════════════════════ 6. HALLAZGOS
ruta = R.get("hit_rate_8_por_antiguedad_de_ruta", {})
s6 = f"""
<section id="hallazgos">
  <div class="snum">06 · Hallazgos</div>
  <h2>Cinco cosas que este análisis dejó claras</h2>

  <div class="grid2">
    <div class="tk"><h3>El «cuándo» ya está resuelto</h3>
      <p>El {ES(iv['pct_7d'],1)} % de los intervalos entre compras son de exactamente siete días.
      El calendario lo pone la ruta, no el cliente. No hay que predecir el momento — hay que
      decidir qué ofrecer cuando llegue.</p></div>

    <div class="tk"><h3>La premisa del sistema actual es correcta</h3>
      <p>La ruta aporta entre 15 y 20 puntos sobre la lista global, y no por surtido de almacén:
      el CEDIS no explica nada. <strong>No hay que tirar el modelo actual, hay que afinarlo.</strong></p></div>

    <div class="tk"><h3>Marca y afinidad son la señal desaprovechada</h3>
      <p>Concentran el {ES(imp[0]['pct']+imp[1]['pct'],1)} % de lo que usa el modelo. El sistema
      actual no mira ninguna de las dos. Ahí está el margen.</p></div>

    <div class="tk"><h3>La oportunidad más cercana ya está en casa</h3>
      <p>Cada cliente tiene unos {ES(cc['dormidos_por_cliente'],1)} productos que ya compró alguna
      vez y hoy no está pidiendo. No hay que convencerlo: ya los vendió.</p></div>

    <div class="tk"><h3>El modelo necesita historia</h3>
      <p>Rinde mejor cuanto más sabe del cliente: de +6 puntos sobre el sistema actual en quienes
      llevan pocos productos a <strong>+19 puntos</strong> en los de surtido amplio.</p></div>
  </div>

  <div>
    <h3 style="margin-top:40px">Dónde funciona y dónde no</h3>
    {tabla(["Segmento", "Clientes", "B1", "P3", "Diferencia"],
           [[k.replace("_", " "), ES(v["clientes"]), f"{ES(v['B1'],1)} %", f"{ES(v['P3'],1)} %",
             ("+" if v["P3"] >= v["B1"] else "−") + ES(abs(v["P3"] - v["B1"]), 1)]
            for k, v in ruta.items()]) if ruta else ""}
    <p class="nota">El modelo gana con holgura donde el cliente tiene historia y <b>pierde donde no
    la tiene</b>: sus variables principales se calculan sobre compras pasadas y quedan vacías. De
    ahí P4, que enruta por historia del cliente.</p>
  </div>

  {plain("Lo que conviene empezar a hacer ya", '''
    <p><strong>Registrar qué recomienda el sistema y qué se compra de eso.</strong> Hoy la base
    guarda compras, no ofertas: no hay forma de saber qué se sugirió y el cliente no tomó.</p>
    <p>Ese dato no se puede reconstruir hacia atrás y es lo único que permitiría aprender de los
    rechazos, medir el sistema que ya opera y evaluar sin depender de reconstrucciones.
    <strong>No cuesta nada empezar hoy.</strong></p>''')}
</section>
"""

# ══════════════════════════════════════════════════════ 7. VALIDACIÓN
s7 = f"""
<section id="validar">
  <div class="snum">07 · Siguiente paso</div>
  <h2>Cómo comprobar que esto sirve de verdad</h2>
  <p class="lead">Todo lo anterior mide <strong>capacidad de predicción</strong>, no impacto.
  Que el modelo acierte qué comprará un cliente no prueba que la sugerencia lo haya causado:
  quizá lo iba a pedir de todos modos. <strong>Lo único que lo demuestra es un experimento con
  grupo de control</strong> — lo que se conoce como una prueba A/B.</p>

  <p class="t">La idea es simple: <strong>un grupo de rutas trabaja con el modelo nuevo y otro
  sigue con el sistema de siempre, durante el mismo periodo y en las mismas condiciones.</strong>
  Si al final el primero vende más SKU por visita, la diferencia solo puede venir del cambio —
  porque todo lo demás fue igual para ambos.</p>

  <p class="t">Sin ese segundo grupo no hay forma de saberlo. Comparar contra el mes anterior no
  sirve: entremedio cambian la temporada, los precios, las promociones y media docena de cosas
  más, y cualquiera de ellas puede explicar el resultado.</p>

  <ol class="pasos">
    <li><b>Partir las rutas en dos grupos comparables.</b> Asignar al azar, no por desempeño: si se
    eligen las mejores rutas para el grupo que recibe el modelo, el resultado está contaminado
    antes de empezar. Emparejar por CEDIS, tamaño y venta histórica.</li>
    <li><b>Dejar el grupo de control con el sistema actual.</b> Mismo número de sugerencias, misma
    operación. La única diferencia debe ser el algoritmo.</li>
    <li><b>Registrar qué se sugiere y qué se compra de eso.</b> Es el dato que hoy no existe y no
    se puede reconstruir hacia atrás. Sin él no hay experimento posible.</li>
    <li><b>Correrlo al menos ocho semanas.</b> El ciclo de compra es semanal y el de surtido
    mensual; menos tiempo no distingue el efecto del ruido.</li>
    <li><b>Comparar grupo contra grupo</b>, no contra el histórico. La pregunta es si las rutas
    con modelo vendieron más que las rutas sin modelo <b>en el mismo periodo</b>.</li>
  </ol>

  <h3 style="margin-top:34px">Qué mirar al final</h3>
  {tabla(["Indicador", "Qué responde"], [
      ["SKU distintos por visita", "la pregunta principal: ¿el cliente se lleva más productos?"],
      ["Importe por visita", "si esos productos de más son de valor o de relleno"],
      ["Visitas que terminan en pedido", "si la lista ayuda a cerrar o solo cambia qué se pide"],
      ["Uso por parte del preventista", "si la herramienta se está usando; sin esto lo demás no se interpreta"],
  ])}
  <p class="nota">El último importa más de lo que parece: si el preventista no abre la lista o no
  confía en ella, el experimento mide adopción y no calidad del modelo. <b>Conviene preguntarle
  también qué le pareció</b>, no solo contar pedidos.</p>

  {plain("Lo que se puede hacer hoy sin costo", '''
    <p><strong>Empezar a registrar qué recomienda el sistema actual y qué se compra de eso.</strong>
    Ese dato no existe hoy y no puede reconstruirse hacia atrás. Es lo único que permitiría después
    aprender de los rechazos, medir el impacto real del sistema que ya opera, y evaluar sin
    depender de reconstrucciones.</p>
    <p><strong>Cada mes que pasa sin registrarlo es un mes de aprendizaje perdido.</strong></p>''')}

  <div>
    <h3 style="margin-top:40px">Limitaciones de este análisis</h3>
    <ol class="pasos">
      <li><b>La línea base es una reconstrucción.</b> La empresa no conserva las recomendaciones
      que su sistema generó, así que se compara contra su lógica descrita, no contra sus
      resultados. Si la implementación difiere de lo que se entendió, la vara se mueve.</li>
      <li><b>No hay señal de faltante de stock.</b> Un «no compró» puede ser «no había».</li>
      <li><b>No hay jerarquía de categorías.</b> La marca es el nivel más fino disponible; con
      categorías se podría generalizar por familia de producto.</li>
      <li><b>Un solo ciclo anual.</b> Tendencia y estacionalidad están confundidas y no se pueden
      separar con doce meses.</li>
      <li><b>El 11 % de los clientes no adoptó ningún producto nuevo</b> en el mes de prueba.
      Están incluidos porque el preventista los visita igual, pero ningún recomendador puede
      acertarles.</li>
    </ol>
  </div>
</section>
"""

# ══════════════════════════════════════════════════════ ENSAMBLADO
hero = f"""
<header class="hero">
  <div class="eyebrow">Informe final · Farmalaxia</div>
  <h1>Un recomendador que le gana<br>al que ya existe</h1>
  <p class="lede">Doce meses de preventa, {ES(g['clientes_que_compraron'])} clientes y
  {ES(P['recomendables'])} productos recomendables. El sistema actual acierta en
  {ES(LIB['hit_rate_8']['B1'],0)} de cada 100 clientes visitados; el modelo entrenado, en
  {ES(LIB['hit_rate_8']['P3'],0)}. Este informe explica cómo se midió, qué lo hace funcionar y
  qué falta para comprobarlo en la calle.</p>
  <div class="meta">
    <span>2025-09-01 → 2026-08-27</span><span>5.328.903 renglones</span>
    <span>Mes de prueba: julio 2026</span><span>{ES(R['clientes_evaluados'])} clientes evaluados</span>
  </div>
</header>
"""
cuerpo = hero + s1 + s2 + s4 + s4b + s5 + s6 + s7
html = (RAIZ / "src" / "sitio" / "plantilla.html").read_text(encoding="utf-8")
html = html.replace("{{CUERPO}}", cuerpo)
# El análisis exploratorio viaja junto al informe: ambos se despliegan al mismo bucket.
_eda_src = RAIZ / "informes" / "dashboard.html"
_eda_dst = RAIZ / "sitio" / "analisis-exploratorio.html"
_eda_dst.parent.mkdir(exist_ok=True)
if _eda_src.exists():
    _eda_dst.write_text(_eda_src.read_text(encoding="utf-8"), encoding="utf-8")
    print(f"análisis exploratorio copiado: {_eda_dst.name}")

salida = RAIZ / "sitio" / "index.html"
salida.parent.mkdir(exist_ok=True)
salida.write_text(html, encoding="utf-8")
kb = len(html.encode("utf-8")) / 1024
print(f"sitio generado: {salida}  ({kb:.0f} KB)")
print(f"  enlace al análisis: {'absoluto → ' + BASE if BASE else 'relativo (uso local)'}")
if "{{" in html:
    import re
    print("OJO, placeholders sin resolver:", set(re.findall(r"\{\{[a-zA-Z_]+\}\}", html)))
