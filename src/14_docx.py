"""Genera el informe final en Word a partir del sitio estático.

Salida: informes/farmalaxia-recomendador-informe-final.docx

La fuente es sitio/index.html — el mismo documento que se publica— así que el
Word nunca se desincroniza del sitio: se regenera después de 13_sitio.py.

Los dos gráficos del sitio son SVG con los estilos en la hoja del documento
(clases .g-*), así que no se pueden rasterizar tal cual: hay que extraerlos,
pegarles esas reglas con los colores ya resueltos y pasarlos por rsvg-convert.

    ./.venv/bin/python src/13_sitio.py --base https://…   # primero el sitio
    ./.venv/bin/python src/14_docx.py                     # después el Word
"""
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import lxml.html
from lxml import etree
from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Emu, Pt, RGBColor

sys.path.insert(0, str(Path(__file__).resolve().parent))
from comun import RAIZ

FUENTE = RAIZ / "sitio" / "index.html"
PLANTILLA = RAIZ / "src" / "sitio" / "plantilla.html"
SALIDA = RAIZ / "informes" / "farmalaxia-recomendador-informe-final.docx"

# Paleta clara del sitio, en el formato que quiere Word (sin almohadilla).
TINTA = "10161D"        # texto principal
TINTA_2 = "4A5765"      # texto secundario
TINTA_3 = "78848F"      # apoyo y notas
ACENTO = "2A78D6"       # azul de titulares y cifras
LINEA = "D9DFE6"
LINEA_SUAVE = "E7ECF1"
FONDO_SUAVE = "F0F7F4"  # recuadros .plain
FONDO_AVISO = "FDF4EF"  # recuadros .plain.warn
FONDO_CAB = "EEF1F5"    # cabeceras de tabla

TEXTO = "Calibri"       # las tipografías del sitio no están en el equipo del cliente
MONO = "Consolas"
ANCHO_IMG = Cm(16.4)


# ─────────────────────────────────────────────── utilidades de OOXML
def _el(tag, **attrs):
    e = OxmlElement(tag)
    for k, v in attrs.items():
        e.set(qn(f"w:{k}"), v)
    return e


def sombrear(celda, color):
    celda._tc.get_or_add_tcPr().append(_el("w:shd", val="clear", fill=color))


def bordes(tabla, **lados):
    """lados: top/left/bottom/right/insideH/insideV = (estilo, grosor, color)."""
    b = OxmlElement("w:tblBorders")
    for lado in ("top", "left", "bottom", "right", "insideH", "insideV"):
        estilo, sz, color = lados.get(lado, ("none", 0, "auto"))
        b.append(_el(f"w:{lado}", val=estilo, sz=str(sz), space="0", color=color))
    tabla._tbl.tblPr.append(b)


def margen_celdas(tabla, alto=70, ancho=100):
    m = OxmlElement("w:tblCellMar")
    for lado, v in (("top", alto), ("left", ancho), ("bottom", alto), ("right", ancho)):
        m.append(_el(f"w:{lado}", w=str(v), type="dxa"))
    tabla._tbl.tblPr.append(m)


def ancho_fijo(tabla, anchos):
    """Reparto de columnas explícito: sin esto cada visor calcula el suyo."""
    tabla.autofit = False
    tabla._tbl.tblPr.append(_el("w:tblLayout", type="fixed"))
    # Word mira la rejilla de la tabla, no solo el ancho de cada celda.
    for gc, ancho in zip(tabla._tbl.find(qn("w:tblGrid")), anchos):
        gc.set(qn("w:w"), str(Emu(int(ancho)).twips))
    for col, ancho in zip(tabla.columns, anchos):
        for celda in col.cells:
            celda.width = ancho


def ancho_completo(tabla):
    """La tabla ocupa el ancho de la caja de texto, en vez del que pida su contenido."""
    w = tabla._tbl.tblPr.find(qn("w:tblW"))
    if w is None:
        w = _el("w:tblW")
        tabla._tbl.tblPr.append(w)
    w.set(qn("w:w"), "5000")
    w.set(qn("w:type"), "pct")


# Orden en que el esquema de OOXML exige los hijos de <w:tblPr>. Word abre el
# archivo igual si se desordenan, pero lo marca como contenido ilegible.
ORDEN_TBLPR = ["tblStyle", "tblpPr", "tblOverlap", "bidiVisual", "tblStyleRowBandSize",
               "tblStyleColBandSize", "tblW", "jc", "tblCellSpacing", "tblInd",
               "tblBorders", "shd", "tblLayout", "tblCellMar", "tblLook",
               "tblCaption", "tblDescription"]


def normalizar(doc):
    for tbl in doc.element.body.iter(qn("w:tbl")):
        pr = tbl.find(qn("w:tblPr"))
        if pr is None:
            continue
        for hijo in sorted(pr, key=lambda e: ORDEN_TBLPR.index(
                etree.QName(e).localname) if etree.QName(e).localname in ORDEN_TBLPR else 99):
            pr.append(hijo)


def sin_partir(tabla):
    """Evita que una fila se corte entre dos páginas."""
    for fila in tabla.rows:
        fila._tr.get_or_add_trPr().append(_el("w:cantSplit"))


# ─────────────────────────────────────────────── párrafos con formato
def _fmt(run, *, tam=10.5, color=TINTA_2, negrita=False, cursiva=False, mono=False):
    run.font.size = Pt(tam)
    run.font.color.rgb = RGBColor.from_string(color)
    run.font.name = MONO if mono else TEXTO
    run.bold = negrita
    run.italic = cursiva


def _añadir(par, txt, negrita, cursiva, est):
    txt = re.sub(r"\s+", " ", txt)
    if not txt.strip() and not par.runs:
        return
    if not par.runs:
        txt = txt.lstrip()
    if not txt:
        return
    r = par.add_run(txt)
    _fmt(r, negrita=negrita or est.get("negrita", False),
         cursiva=cursiva or est.get("cursiva", False),
         tam=est.get("tam", 10.5), color=est.get("color", TINTA_2),
         mono=est.get("mono", False))


def texto_rico(par, el, negrita=False, cursiva=False, **est):
    """Vuelca el contenido de un elemento HTML como runs, respetando b/strong/i."""
    if el.text:
        _añadir(par, el.text, negrita, cursiva, est)
    for hijo in el:
        if hijo.tag == "br":
            par.add_run().add_break()
        else:
            texto_rico(par, hijo,
                       negrita or hijo.tag in ("b", "strong"),
                       cursiva or hijo.tag in ("i", "em"), **est)
        if hijo.tail:
            _añadir(par, hijo.tail, negrita, cursiva, est)
    return par


def parrafo(doc, el=None, txt=None, *, antes=0, despues=8, sangria=0, **est):
    p = doc.add_paragraph()
    pf = p.paragraph_format
    pf.space_before, pf.space_after = Pt(antes), Pt(despues)
    pf.line_spacing = 1.22
    if sangria:
        pf.left_indent = Cm(sangria)
    if el is not None:
        texto_rico(p, el, **est)
    elif txt:
        _añadir(p, txt, False, False, est)
    return p


def titular(doc, texto, nivel):
    """h2/h3/h4 del sitio → Título 1/2/3 de Word, con la tipografía del informe."""
    cfg = {1: (17, TINTA, 20, 7), 2: (13, TINTA, 17, 5), 3: (11.5, ACENTO, 13, 4)}
    tam, color, antes, despues = cfg[nivel]
    p = doc.add_heading("", level=nivel)
    p.paragraph_format.space_before = Pt(antes)
    p.paragraph_format.space_after = Pt(despues)
    r = p.add_run(re.sub(r"\s+", " ", texto).strip())
    _fmt(r, tam=tam, color=color, negrita=True)
    return p


# ─────────────────────────────────────────────── bloques compuestos
def es_numero(s):
    return bool(re.fullmatch(r"[\d.,\s%+−\-—]+", s.strip()))


def tabla_datos(doc, el):
    """div.tw > table → tabla de Word con cabecera sombreada y filas .dest en negrita."""
    cab = [th.text_content().strip() for th in el.xpath(".//thead//th")]
    filas = el.xpath(".//tbody/tr")
    t = doc.add_table(rows=1, cols=len(cab))
    t.alignment = WD_TABLE_ALIGNMENT.LEFT
    bordes(t, top=("single", 6, TINTA), bottom=("single", 6, TINTA),
           insideH=("single", 4, LINEA_SUAVE))
    margen_celdas(t)
    for i, c in enumerate(cab):
        celda = t.rows[0].cells[i]
        p = celda.paragraphs[0]
        p.paragraph_format.space_after = Pt(2)
        _fmt(p.add_run(c), tam=9, color=TINTA, negrita=True)
        sombrear(celda, FONDO_CAB)
        if i:
            p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    for tr in filas:
        dest = "dest" in (tr.get("class") or "")
        celdas = t.add_row().cells
        for i, td in enumerate(tr.xpath("./td")):
            p = celdas[i].paragraphs[0]
            p.paragraph_format.space_after = Pt(2)
            crudo = td.text_content().strip()
            # la clase "n" marca la columna, no el contenido: solo se alinea a la
            # derecha lo que de verdad es una cifra.
            if i and es_numero(crudo):
                p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
            texto_rico(p, td, negrita=dest, tam=9.5,
                       color=TINTA if dest else TINTA_2,
                       mono=i > 0 and es_numero(crudo))
    ancho_completo(t)
    sin_partir(t)
    parrafo(doc, txt="", despues=4)
    return t


def tira_cifras(doc, el):
    """div.stats → una fila de cifras grandes con su etiqueta debajo, sin bordes."""
    stats = el.xpath("./div")
    t = doc.add_table(rows=2, cols=len(stats))
    bordes(t)
    margen_celdas(t, alto=40, ancho=40)
    ancho_fijo(t, [ANCHO_IMG // len(stats)] * len(stats))
    for i, s in enumerate(stats):
        hi = "hi" in (s.get("class") or "")
        v = s.xpath('./span[contains(@class,"v")]')[0].text_content().strip()
        k = s.xpath('./span[@class="k"]')[0].text_content().strip()
        pv = t.rows[0].cells[i].paragraphs[0]
        pv.paragraph_format.space_after = Pt(0)
        _fmt(pv.add_run(v), tam=15, color=ACENTO if hi else TINTA, negrita=True, mono=True)
        pk = t.rows[1].cells[i].paragraphs[0]
        pk.paragraph_format.space_after = Pt(0)
        _fmt(pk.add_run(k), tam=8, color=TINTA_3)
    ancho_completo(t)
    sin_partir(t)
    parrafo(doc, txt="", despues=6)


def recuadro(doc, el, fondo, borde):
    """div.plain / .plain.warn / .callout → celda única sombreada."""
    t = doc.add_table(rows=1, cols=1)
    bordes(t, top=("single", 4, borde), left=("single", 18, ACENTO),
           bottom=("single", 4, borde), right=("single", 4, borde))
    margen_celdas(t, alto=140, ancho=180)
    celda = t.rows[0].cells[0]
    sombrear(celda, fondo)
    celda._element.remove(celda.paragraphs[0]._p)
    for hijo in el:
        cls = hijo.get("class") or ""
        if cls == "tag":
            p = celda.add_paragraph()
            p.paragraph_format.space_after = Pt(5)
            _fmt(p.add_run(hijo.text_content().strip().upper()),
                 tam=8.5, color=TINTA, negrita=True)
        elif hijo.tag == "ul":
            for li in hijo.xpath("./li"):
                p = celda.add_paragraph(style="List Bullet")
                p.paragraph_format.space_after = Pt(4)
                p.paragraph_format.line_spacing = 1.18
                texto_rico(p, li, tam=10)
        else:
            p = celda.add_paragraph()
            p.paragraph_format.space_after = Pt(5)
            p.paragraph_format.line_spacing = 1.2
            texto_rico(p, hijo, tam=10)
    celda.paragraphs[-1].paragraph_format.space_after = Pt(0)
    ancho_completo(t)
    sin_partir(t)
    parrafo(doc, txt="", despues=6)


def fichas_variables(doc, el):
    """div.vars → tabla de tres columnas con las familias como fila de cabecera."""
    t = doc.add_table(rows=0, cols=3)
    bordes(t, top=("single", 6, TINTA), bottom=("single", 6, TINTA),
           insideH=("single", 4, LINEA_SUAVE))
    margen_celdas(t)
    for hijo in el:
        cls = hijo.get("class") or ""
        celdas = t.add_row().cells
        if cls == "vfam":
            celdas[0].merge(celdas[2])
            p = celdas[0].paragraphs[0]
            p.paragraph_format.space_after = Pt(2)
            _fmt(p.add_run(hijo.text_content().strip().upper()),
                 tam=8.5, color=TINTA_3, negrita=True)
            sombrear(celdas[0], FONDO_CAB)
            continue
        baja = "baja" in cls
        for i, sel in enumerate(("vn", "vd", "vp")):
            n = hijo.xpath(f'./div[@class="{sel}"]')[0]
            p = celdas[i].paragraphs[0]
            p.paragraph_format.space_after = Pt(2)
            p.paragraph_format.line_spacing = 1.15
            if sel == "vn":
                _fmt(p.add_run(n.text_content().strip()), tam=9.5, color=TINTA,
                     negrita=True, mono=True)
            elif sel == "vd":
                texto_rico(p, n, tam=9.5)
            else:
                p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
                _fmt(p.add_run(n.text_content().strip()), tam=9.5,
                     color=TINTA_3 if baja else ACENTO, negrita=True, mono=True)
    ancho_fijo(t, (Cm(4.2), Cm(10.2), Cm(2.0)))
    ancho_completo(t)
    sin_partir(t)
    parrafo(doc, txt="", despues=6)


def lista_pasos(doc, el):
    for i, li in enumerate(el.xpath("./li"), 1):
        p = doc.add_paragraph()
        p.paragraph_format.space_after = Pt(7)
        p.paragraph_format.left_indent = Cm(0.9)
        p.paragraph_format.first_line_indent = Cm(-0.9)
        p.paragraph_format.line_spacing = 1.2
        _fmt(p.add_run(f"{i}.  "), tam=10.5, color=ACENTO, negrita=True)
        texto_rico(p, li)


def callout(doc, el):
    t = doc.add_table(rows=1, cols=1)
    bordes(t, top=("single", 4, LINEA), left=("single", 18, ACENTO),
           bottom=("single", 4, LINEA), right=("single", 4, LINEA))
    margen_celdas(t, alto=140, ancho=180)
    celda = t.rows[0].cells[0]
    sombrear(celda, FONDO_CAB)
    celda._element.remove(celda.paragraphs[0]._p)
    txt = el.xpath('.//div[@class="co-txt"]')[0]
    p = celda.add_paragraph()
    p.paragraph_format.space_after = Pt(4)
    _fmt(p.add_run(txt.xpath("./h3")[0].text_content().strip()),
         tam=11, color=TINTA, negrita=True)
    for pe in txt.xpath("./p"):
        q = celda.add_paragraph()
        q.paragraph_format.space_after = Pt(5)
        texto_rico(q, pe, tam=10)
    enlace = el.xpath(".//a")[0]
    q = celda.add_paragraph()
    q.paragraph_format.space_after = Pt(0)
    _fmt(q.add_run(enlace.get("href")), tam=9, color=ACENTO, mono=True)
    ancho_completo(t)
    sin_partir(t)
    parrafo(doc, txt="", despues=6)


# ─────────────────────────────────────────────── gráficos
def css_graficos():
    """Las reglas .g-* de la plantilla, con los var(--x) resueltos a la paleta clara.

    Las tipografías del sitio no están instaladas: se sustituyen por equivalentes
    del sistema, porque si no librsvg cae en una serif que no es la del informe.
    """
    hoja = PLANTILLA.read_text(encoding="utf-8")
    raiz = re.search(r":root\{(.*?)\}", hoja, re.S).group(1)
    var = dict(re.findall(r"(--[\w-]+)\s*:\s*([^;]+);", raiz))
    reglas = re.findall(r"\.g-[^{}]*\{[^}]*\}", hoja, re.S)
    css = "\n".join(reglas)
    css = re.sub(r"var\((--[\w-]+)\)", lambda m: var.get(m.group(1), "#000").strip(), css)
    css = css.replace('"IBM Plex Mono",monospace', "Menlo,Consolas,monospace")
    return "svg{font-family:Helvetica,Arial,sans-serif}\n" + css


def rasterizar(svg, destino, css):
    """SVG suelto + hoja de estilos → PNG.

    El SVG viaja como texto crudo del HTML, no como elemento parseado: el parser
    de HTML pasa los atributos a minúsculas y `viewBox` es sensible a mayúsculas
    —convertido en `viewbox`, librsvg lo ignora y el gráfico sale deformado.
    """
    svg = svg.replace("<svg ", '<svg xmlns="http://www.w3.org/2000/svg" ', 1)
    svg = svg.replace(">", f"><style>{css}</style>", 1)
    tmp = destino.with_suffix(".svg")
    tmp.write_text(svg, encoding="utf-8")
    subprocess.run(["rsvg-convert", "-w", "1920", "--background-color=white",
                    "-o", str(destino), str(tmp)], check=True)
    return destino


def grafico(doc, el, ctx):
    n = ctx["n"]()
    svg = el.xpath("./svg")[0]
    if not shutil.which("rsvg-convert"):
        print("  ⚠ falta rsvg-convert: el gráfico se omite")
        return
    png = rasterizar(ctx["svgs"][n - 1], Path(ctx["tmp"]) / f"g{n}.png", ctx["css"])
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before = Pt(6)
    p.paragraph_format.space_after = Pt(4)
    p.paragraph_format.keep_with_next = True
    p.add_run().add_picture(str(png), width=ANCHO_IMG)
    pie = doc.add_paragraph()
    pie.alignment = WD_ALIGN_PARAGRAPH.CENTER
    pie.paragraph_format.space_after = Pt(12)
    _fmt(pie.add_run(svg.get("aria-label", "")), tam=8.5, color=TINTA_3, cursiva=True)


# ─────────────────────────────────────────────── documento
def preparar(doc):
    s = doc.sections[0]
    s.left_margin = s.right_margin = Cm(2.4)
    s.top_margin = Cm(2.2)
    s.bottom_margin = Cm(2.0)
    normal = doc.styles["Normal"]
    normal.font.name = TEXTO
    normal.font.size = Pt(10.5)
    normal.element.rPr.rFonts.set(qn("w:eastAsia"), TEXTO)
    # Pie con el número de página.
    pie = s.footer.paragraphs[0]
    pie.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _fmt(pie.add_run("Farmalaxia · recomendador de SKUs · "), tam=8, color=TINTA_3)
    # El número va dentro del campo y con su propio formato: si no, sale en el
    # cuerpo de texto normal y desentona en todas las páginas.
    campo = _el("w:fldSimple", instr=" PAGE ")
    r = pie.add_run("1")
    _fmt(r, tam=8, color=TINTA_3)
    campo.append(r._r)
    pie._p.append(campo)
    return doc


def portada(doc, hero):
    parrafo(doc, txt=hero.xpath('./div[@class="eyebrow"]')[0].text_content().strip().upper(),
            antes=40, despues=10, tam=9.5, color=ACENTO, negrita=True)
    p = doc.add_paragraph()
    p.paragraph_format.space_after = Pt(18)
    p.paragraph_format.line_spacing = 1.05
    for i, linea in enumerate(hero.xpath("./h1")[0].itertext()):
        if i:
            p.add_run().add_break()
        _fmt(p.add_run(linea.strip()), tam=30, color=TINTA, negrita=True)
    parrafo(doc, hero.xpath('./p[@class="lede"]')[0], despues=22, tam=12.5, color=TINTA_2)
    meta = " · ".join(s.text_content().strip()
                      for s in hero.xpath('./div[@class="meta"]/span'))
    parrafo(doc, txt=meta, despues=0, tam=9, color=TINTA_3, mono=True)
    doc.paragraphs[-1].add_run().add_break(WD_BREAK.PAGE)


def bloque(doc, el, ctx):
    cls = el.get("class") or ""
    tag = el.tag
    if tag == "h2":
        titular(doc, el.text_content(), 1)
    elif tag == "h3":
        titular(doc, el.text_content(), 2)
    elif tag == "h4":
        titular(doc, el.text_content(), 3)
    elif cls == "snum":
        p = parrafo(doc, txt=el.text_content().strip().upper(), antes=22, despues=2,
                    tam=9, color=ACENTO, negrita=True, mono=True)
        p.paragraph_format.keep_with_next = True
    elif tag == "p" and cls == "lead":
        parrafo(doc, el, despues=12, tam=11.5, color=TINTA)
    elif tag == "p" and cls == "nota":
        parrafo(doc, el, despues=10, tam=9.5, color=TINTA_3, cursiva=True)
    elif tag == "p":
        parrafo(doc, el, despues=10)
    elif cls == "stats":
        tira_cifras(doc, el)
    elif cls == "card":
        grafico(doc, el, ctx)
    elif cls.startswith("plain"):
        aviso = "warn" in cls
        recuadro(doc, el, FONDO_AVISO if aviso else FONDO_SUAVE,
                 "F2D3BF" if aviso else "C5E3D7")
    elif cls == "callout":
        callout(doc, el)
    elif cls == "tw":
        tabla_datos(doc, el.xpath("./table")[0])
    elif cls == "vars":
        fichas_variables(doc, el)
    elif cls == "grid2":
        for tk in el.xpath('./div[@class="tk"]'):
            titular(doc, tk.xpath("./h3")[0].text_content(), 3)
            for pe in tk.xpath("./p"):
                parrafo(doc, pe, despues=8, tam=10)
    elif cls == "pasos":
        lista_pasos(doc, el)
    elif tag in ("div", "section"):   # envoltorios sin estilo propio
        for hijo in el:
            bloque(doc, hijo, ctx)


def main():
    if not FUENTE.exists():
        sys.exit("falta sitio/index.html — ejecuta antes src/13_sitio.py")
    crudo = FUENTE.read_text(encoding="utf-8")
    svgs = re.findall(r"<svg\b.*?</svg>", crudo, re.S)
    arbol = lxml.html.fromstring(crudo)
    wrap = arbol.xpath('//div[@class="wrap"]')[0]
    doc = preparar(Document())
    portada(doc, wrap.xpath("./header")[0])
    contador = iter(range(1, 99))
    with tempfile.TemporaryDirectory() as tmp:
        ctx = {"tmp": tmp, "css": css_graficos(), "svgs": svgs,
               "n": lambda: next(contador)}
        for sec in wrap.xpath("./section"):
            for hijo in sec:
                bloque(doc, hijo, ctx)
        SALIDA.parent.mkdir(exist_ok=True)
        normalizar(doc)
        doc.save(SALIDA)
    kb = SALIDA.stat().st_size / 1024
    print(f"documento generado: {SALIDA}  ({kb:.0f} KB)")


if __name__ == "__main__":
    main()
