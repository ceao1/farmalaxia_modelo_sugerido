"""Gráficos SVG para el sitio estático.

Todo va embebido: el sitio debe funcionar servido desde S3 o Cloud Storage
sin ninguna dependencia externa salvo la hoja de fuentes de Google.
La geometría se calcula en Python; el SVG no lleva scripts.
"""
W, ML, MR, MT = 960, 62, 24, 20


def ES(n, d=0):
    """Formato español: miles con punto, decimales con coma."""
    t = f"{n:,.{d}f}"
    return t.replace(",", "\x00").replace(".", ",").replace("\x00", ".")


def _esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def _ejes(h, mb, ticks, ymax, fmt):
    out, iw, ih = [], W - ML - MR, h - MT - mb
    for t in ticks:
        y = MT + ih - (t / ymax) * ih
        out.append(f'<line x1="{ML}" y1="{y:.1f}" x2="{W-MR}" y2="{y:.1f}" class="g-grid"/>')
        out.append(f'<text x="{ML-10}" y="{y+4:.1f}" class="g-yt">{fmt(t)}</text>')
    return "".join(out)


def _svg(h, cuerpo, alt):
    return (f'<svg viewBox="0 0 {W} {h}" class="g-chart" role="img" '
            f'aria-label="{_esc(alt)}">{cuerpo}</svg>')


def barras(datos, alt, ymax=None, fmt_y=lambda v: f"{v:.0f}", unidad="%",
           h=280, mb=52, destacar=None, etiqueta_x=""):
    """Barras verticales. `datos` = [(etiqueta, valor), ...]."""
    ymax = ymax or max(v for _, v in datos) * 1.18
    iw, ih = W - ML - MR, h - MT - mb
    ticks = [ymax * k / 4 for k in range(5)]
    bw = iw / len(datos)
    s = [_ejes(h, mb, ticks, ymax, fmt_y)]
    for i, (lab, v) in enumerate(datos):
        bh = (v / ymax) * ih
        x = ML + i * bw + bw * 0.18
        y = MT + ih - bh
        cls = "g-bar acc" if (destacar and lab in destacar) else "g-bar"
        s.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{bw*0.64:.1f}" height="{max(bh,1):.1f}" '
                 f'rx="3" class="{cls}"><title>{_esc(lab)}: {ES(v,1)}{unidad}</title></rect>')
        s.append(f'<text x="{x+bw*0.32:.1f}" y="{y-8:.1f}" class="g-lab">{ES(v,1)}{unidad}</text>')
        s.append(f'<text x="{x+bw*0.32:.1f}" y="{h-mb+22}" class="g-xt">{_esc(lab)}</text>')
    if etiqueta_x:
        s.append(f'<text x="{ML+iw/2:.1f}" y="{h-8}" class="g-ax">{_esc(etiqueta_x)}</text>')
    return _svg(h, "".join(s), alt)


def barras_agrupadas(categorias, series, alt, ymax=None, h=300, mb=58, unidad="%"):
    """`series` = [(nombre, clase, [valores por categoría]), ...]."""
    ymax = ymax or max(max(v) for _, _, v in series) * 1.2
    iw, ih = W - ML - MR, h - MT - mb
    ticks = [ymax * k / 4 for k in range(5)]
    grupo = iw / len(categorias)
    bw = grupo / (len(series) + 1.4)
    s = [_ejes(h, mb, ticks, ymax, lambda v: f"{v:.0f}{unidad}")]
    for i, cat in enumerate(categorias):
        x0 = ML + i * grupo + (grupo - bw * len(series)) / 2
        for k, (nom, cls, vals) in enumerate(series):
            v = vals[i]
            bh = (v / ymax) * ih
            x = x0 + k * bw
            y = MT + ih - bh
            s.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{bw*0.88:.1f}" '
                     f'height="{max(bh,1):.1f}" rx="2.5" class="g-bar {cls}">'
                     f'<title>{_esc(nom)} · {_esc(cat)}: {ES(v,1)}{unidad}</title></rect>')
            s.append(f'<text x="{x+bw*0.44:.1f}" y="{y-6:.1f}" class="g-lab sm">{ES(v,1)}</text>')
        s.append(f'<text x="{ML+i*grupo+grupo/2:.1f}" y="{h-mb+22}" class="g-xt str">{_esc(cat)}</text>')
    lx = ML
    for nom, cls, _ in series:
        s.append(f'<rect x="{lx}" y="{h-20}" width="11" height="11" rx="2" class="g-bar {cls}"/>')
        s.append(f'<text x="{lx+17}" y="{h-10}" class="g-leg">{_esc(nom)}</text>')
        lx += 28 + len(nom) * 7.2
    return _svg(h, "".join(s), alt)


def apiladas(filas, segmentos, alt, h=None):
    """Barras 100 % apiladas. `filas` = [(etiqueta, {clave: pct}), ...]."""
    h = h or 46 + len(filas) * 46
    iw = W - ML - MR
    s = []
    for ri, (lab, vals) in enumerate(filas):
        y = 20 + ri * 46
        s.append(f'<text x="{ML-10}" y="{y+21:.0f}" class="g-yt">{_esc(lab)}</text>')
        x = ML
        for clave, nom, cls in segmentos:
            v = vals.get(clave, 0)
            w = v / 100 * iw
            s.append(f'<rect x="{x:.1f}" y="{y}" width="{max(w-2,1):.1f}" height="32" rx="3" '
                     f'class="g-seg {cls}"><title>{_esc(nom)}: {ES(v,1)} %</title></rect>')
            if w > 66:
                s.append(f'<text x="{x+w/2-1:.1f}" y="{y+21:.0f}" class="g-segl">{ES(v,1)} %</text>')
            x += w
    lx = ML
    for _, nom, cls in segmentos:
        s.append(f'<rect x="{lx}" y="{h-18}" width="11" height="11" rx="2" class="g-seg {cls}"/>')
        s.append(f'<text x="{lx+17}" y="{h-8}" class="g-leg">{_esc(nom)}</text>')
        lx += 28 + len(nom) * 7.2
    return _svg(h, "".join(s), alt)


def lineas(x_labels, series, alt, ymax=None, h=290, mb=48, unidad=""):
    """`series` = [(nombre, clase, [valores]), ...]. Valores None cortan la línea."""
    vals = [v for _, _, vv in series for v in vv if v is not None]
    ymax = ymax or max(vals) * 1.15
    iw, ih = W - ML - MR, h - MT - mb
    ticks = [ymax * k / 4 for k in range(5)]
    n = len(x_labels)
    X = lambda i: ML + (i * iw / (n - 1) if n > 1 else iw / 2)
    Y = lambda v: MT + ih - (v / ymax) * ih
    s = [_ejes(h, mb, ticks, ymax, lambda v: f"{v:,.0f}{unidad}".replace(",", "."))]
    for nom, cls, vv in series:
        seg = []
        for i, v in enumerate(vv):
            if v is None:
                if len(seg) > 1:
                    s.append(f'<polyline points="{" ".join(seg)}" class="g-line {cls}"/>')
                seg = []
                continue
            seg.append(f"{X(i):.1f},{Y(v):.1f}")
        if len(seg) > 1:
            s.append(f'<polyline points="{" ".join(seg)}" class="g-line {cls}"/>')
        for i, v in enumerate(vv):
            if v is None:
                continue
            s.append(f'<circle cx="{X(i):.1f}" cy="{Y(v):.1f}" r="4" class="g-dot {cls}">'
                     f'<title>{_esc(nom)} · {_esc(x_labels[i])}: {ES(v,1)}{unidad}</title></circle>')
    for i, lab in enumerate(x_labels):
        s.append(f'<text x="{X(i):.1f}" y="{h-mb+22}" class="g-xt">{_esc(lab)}</text>')
    lx = ML
    for nom, cls, _ in series:
        s.append(f'<rect x="{lx}" y="{h-16}" width="11" height="3" rx="1.5" class="g-seg {cls}"/>')
        s.append(f'<text x="{lx+17}" y="{h-9}" class="g-leg">{_esc(nom)}</text>')
        lx += 28 + len(nom) * 7.2
    return _svg(h, "".join(s), alt)
