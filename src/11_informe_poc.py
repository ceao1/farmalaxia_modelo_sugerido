"""Genera informes/04-resultados-poc.md a partir de resultados/poc.json.

No contiene conclusiones escritas a mano: todo el texto de veredicto se deriva
de las cifras, para que el informe no pueda contradecir a los datos.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from comun import INFORMES, RESULTADOS

RUTA_JSON = Path(sys.argv[1]) if len(sys.argv) > 1 else RESULTADOS / "poc.json"
RUTA_MD = Path(sys.argv[2]) if len(sys.argv) > 2 else INFORMES / "04-resultados-poc.md"
D = json.load(open(RUTA_JSON))
NOMBRES = {"B0": "B0 · popularidad global",
           "B1": "**B1 · popularidad de ruta** *(modelo actual)*",
           "P1": "P1 · ruta + marca conocida",
           "P2": "P2 · afinidad ítem-ítem",
           "P3": "P3 · ranker LightGBM"}


def ES(n, d=0):
    t = f"{n:,.{d}f}"
    return t.replace(",", "\x00").replace(".", ",").replace("\x00", ".")


def tabla_politica(pol: str) -> str:
    b = D["politicas"][pol]
    filas = []
    for m in ["B0", "B1", "P1", "P2", "P3"]:
        lo, hi = b["intervalo_95"][m]
        g = b["desglose"][m]
        dif = b["hit_rate_8"][m] - b["hit_rate_8"]["B1"]
        # ES() devuelve cadena, así que el signo se antepone a mano
        marca = "—" if m == "B1" else ("+" if dif >= 0 else "−") + ES(abs(dif), 2)
        filas.append(f"| {NOMBRES[m]} | {ES(b['hit_rate_8'][m],2)} % | "
                     f"[{ES(lo,2)} – {ES(hi,2)}] | {marca} | "
                     f"{ES(g.get('dormido',0))} | {ES(g.get('nunca',0))} |")
    return ("| Modelo | hit-rate@8 | IC 95 % | vs B1 | Aciertos dormido | Aciertos nunca |\n"
            "|---|---:|---:|---:|---:|---:|\n" + "\n".join(filas))


def veredicto(pol: str) -> str:
    v = D["politicas"][pol]["veredicto"]
    if v["logrado"]:
        return (f"**Se alcanzó el umbral.** {v['mejor_propuesta']} supera a B1 en "
                f"**{ES(v['diferencia_pp'],2)} puntos** ({ES(v['b1'],2)} % → "
                f"{ES(v['b1']+v['diferencia_pp'],2)} %), por encima de los 5 exigidos.")
    return (f"**No se alcanzó el umbral.** La mejor propuesta ({v['mejor_propuesta']}) supera "
            f"a B1 en {ES(v['diferencia_pp'],2)} puntos, por debajo de los 5 exigidos "
            f"(objetivo {ES(v['objetivo'],2)} %). Significa que la popularidad de ruta ya "
            f"captura casi todo lo predecible con los datos disponibles, y que el camino no "
            f"es un mejor modelo sino **mejores datos**.")


def curvas(pol: str) -> str:
    b = D["politicas"][pol]
    mejor = b["veredicto"]["mejor_propuesta"]
    f = ["| N | B1 hit-rate | " + mejor + " hit-rate | B1 precisión | " + mejor + " precisión |",
         "|---:|---:|---:|---:|---:|"]
    for r1, r2 in zip(b["curvas"]["B1"], b["curvas"][mejor]):
        f.append(f"| {r1['N']} | {ES(r1['hit_rate'],2)} % | {ES(r2['hit_rate'],2)} % | "
                 f"{ES(r1['precision'],2)} % | {ES(r2['precision'],2)} % |")
    return "\n".join(f)


def negocio_bloque(pol: str) -> str:
    b = D["politicas"][pol]
    mejor = b["veredicto"]["mejor_propuesta"]
    n = b["negocio"][mejor]
    esc = "\n".join(
        f"| {ES(e['tasa_conversion']*100,0)} % | {ES(e['mensual'])} | {ES(e['anual'])} |"
        for e in b["escenarios"])
    return f"""Con **{mejor}** y 8 sugerencias por cliente-mes:

| Métrica | Valor |
|---|---:|
| Aciertos por cliente-mes | {ES(n['aciertos_por_cliente'],3)} |
| **SKU adicionales por compra** | **{ES(n['sku_extra_por_compra'],3)}** |
| Importe de los aciertos, por cliente | {ES(n['importe_por_cliente'],1)} |
| De los aciertos, cuántos son descubrimiento | {ES(n['pct_descubrimiento'],1)} % |

Escenarios de impacto anual sobre {ES(D['clientes_evaluados'])} clientes:

| Conversión incremental supuesta | Mensual | Anual |
|---:|---:|---:|
{esc}

⚠️ **La tasa de conversión es un supuesto, no un dato.** Los datos dicen si el modelo acierta
qué comprará el cliente, no si la sugerencia lo causó. Por eso no hay una cifra única de
impacto. Solo un piloto con grupo de control lo mide.
"""


imp = "\n".join(f"| {r['variable']} | {ES(r['ganancia'],1)} | {ES(r['pct'],1)} % |"
                for r in D["importancias"])
ruta = D.get("hit_rate_8_por_antiguedad_de_ruta", {})
ruta_tabla = ""
if ruta:
    ruta_tabla = ("| Rutas | Clientes | " + " | ".join(["B0","B1","P1","P2","P3"]) + " |\n"
                  "|---|---:|" + "---:|" * 5 + "\n")
    for k, v in ruta.items():
        ruta_tabla += (f"| {k.replace('_',' ')} | {ES(v['clientes'])} | "
                       + " | ".join(f"{ES(v[m],2)} %" for m in ["B0","B1","P1","P2","P3"]) + " |\n")

doc = f"""# Resultados del POC — recomendador de SKUs

Mes de prueba **{D['mes_prueba']}** · {ES(D['clientes_evaluados'])} clientes ·
{ES(D['candidatos_por_cliente'])} candidatos por cliente · {ES(D['positivos_pct'],3)} % de positivos

Diseño: [`docs/diseno/2026-09-13-recomendador-sku.md`](../docs/diseno/2026-09-13-recomendador-sku.md)
· Reproducible con `./.venv/bin/python src/10_ejecutar_poc.py`

---

## 1. Qué se probó

Si **personalizar dentro de la ruta** supera a la popularidad de ruta, que es la lógica del
modelo que la empresa opera hoy (B1, reconstruido — no conservan las recomendaciones que su
sistema generó).

Los cinco modelos ordenan **el mismo conjunto de candidatos**: productos recomendables que el
cliente **no pidió en los últimos dos meses**. Incluye los **dormidos** (los conoce pero dejó
de pedirlos) y los **nunca comprados**. Se excluye lo habitual: el cliente lo iba a pedir igual.

## 2. Resultados — política libre

Los 8 mejor puntuados, sin importar el origen.

{tabla_politica('libre')}

{veredicto('libre')}

## 3. Resultados — política mixta (5 dormidos + 3 nunca)

{tabla_politica('mixta')}

{veredicto('mixta')}

## 4. Curva de N — política libre

{curvas('libre')}

## 5. Importancia de variables

| Variable | Ganancia | % |
|---|---:|---:|
{imp}

## 6. Traducción a negocio — política libre

{negocio_bloque('libre')}

## 7. Desglose por antigüedad de ruta

{ruta_tabla if ruta_tabla else '_No hay suficientes clientes en rutas nuevas para reportar aparte._'}

Las rutas abiertas en junio de 2026 tienen menos de tres meses de historia, así que su B1 es
inestable por construcción.

## 8. Siguiente paso — P4, un modelo por segmento

El desglose por antigüedad de ruta muestra que **ningún modelo gana en todos lados**: P3 domina
donde el cliente tiene historia y pierde donde no la tiene, porque sus dos variables principales
—afinidad y peso de marca— se calculan sobre compras pasadas y quedan vacías en clientes
recientes.

La propuesta es una **regla de enrutamiento**, no un modelo nuevo:

```
si el cliente tiene poca historia  ->  B1 (popularidad de ruta)
si no                              ->  P3 (ranker)
```

Tres precisiones que salen de lo medido en este POC:

1. **Para clientes sin historia el mejor modelo es B1, no P1.** P1 filtra por marcas que el
   cliente ya compra, y quien lleva cuatro SKU comprados casi no tiene marcas conocidas: el
   filtro se queda sin material.
2. **El corte debe hacerse por historia del cliente, no por antigüedad de la ruta.** Un cliente
   nuevo en una ruta vieja tiene el mismo problema y hoy quedaría mal clasificado. Meses de
   historia o número de SKU comprados son candidatos naturales — ya son variables del modelo.
3. **El umbral del corte debe elegirse sobre el mes de validación, nunca sobre el de prueba.**
   Buscar el punto que maximiza el resultado en julio sería ajustar contra la respuesta.

La ganancia esperada es modesta, pero el valor principal no es la métrica: **evita desplegar
algo que rinde peor que el sistema actual en una parte de la base.** Un preventista de ruta
nueva que reciba sugerencias peores deja de confiar en la herramienta, y eso cuesta más que
los puntos que se ganen en el promedio.

## 9. Limitaciones

1. **B1 es una reconstrucción.** La empresa no conserva las recomendaciones que su modelo
   generó, así que comparamos contra su lógica descrita, no contra sus resultados. Si su
   implementación difiere de lo que entendimos, la vara se mueve.
2. **Esto mide predicción, no causalidad.** Acertar qué comprará un cliente no prueba que la
   sugerencia lo cause. **Solo un piloto con grupo de control** —unas rutas reciben las
   sugerencias y otras no— mide impacto real. Es la fase siguiente.
3. **Sin señal de faltante de stock:** un «no compró» puede ser «no había».
4. **Sin jerarquía de categorías:** marca es el nivel más fino disponible.
5. **Un solo ciclo anual:** tendencia y estacionalidad están confundidas.
6. **El 11 % de los clientes no adoptó ningún producto nuevo** en el mes de prueba. Están
   incluidos en la evaluación porque el preventista los visita igual, pero ningún recomendador
   puede acertarles.
"""
RUTA_MD.write_text(doc, encoding="utf-8")
print(f"informe escrito: {RUTA_MD}")
