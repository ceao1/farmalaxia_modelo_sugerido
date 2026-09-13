# EDA — Comportamiento de clientes (`dbventas.tblVentas`)

Periodo 2025-09-01 → 2026-08-27 · 5.328.903 líneas · 36.120 clientes · 538 productos

> Este documento es la versión técnica. Para presentar a un público comercial, use el
> [informe visual](https://claude.ai/code/artifact/72341c95-838b-4a10-bbee-84c0435cf408):
> tiene el mismo contenido y cada sección cierra con un recuadro «En palabras simples».
>
> **Corrección aplicada:** 345 SKUs con prefijo `PP*` resultaron ser registros de mecánica
> promocional (importe 0,00 en el 100 % de sus líneas), no mercancía. Se excluyen de toda
> métrica de surtido. Ver [`03-analisis-productos.md`](03-analisis-productos.md).
Reproducible con `./.venv/bin/python src/02_eda_clientes.py` → `resultados/eda_resultados.json`

---

## 0. Definición de grano

La tabla **no tiene ID de pedido**, así que el evento hay que reconstruirlo:

| Concepto | Definición | Volumen |
|---|---|---|
| **Visita** | `(fecha, ClienteCodigo)` distinto | 1.477.791 |
| **Compra** | visita con ≥1 línea con `PiezasPreventa > 0` | 890.471 |
| **Conversión** | compras / visitas | **60,3 %** |

Dos decisiones deliberadas:

- **Se colapsan las rutas.** 167.817 eventos (11 %) tienen el mismo cliente y fecha en
  más de una `rutaPreventa`. Para el cliente es un solo día de compra; al recomendador
  no le importa qué ruta lo surtió.
- **El filtro es `piezas > 0`, no `sku IS NOT NULL`.** Hay 56 líneas con SKU pero cero
  piezas que no son compras.

Se usa **preventa** como señal de demanda. El rechazo (2,1 % del importe) es un problema
de surtido posterior, no de intención de compra.

---

## 1. Clientes activos por mes

| Mes | Visitados | Compradores | Conv. | Compras | Compras/cliente | Ticket |
|---|---:|---:|---:|---:|---:|---:|
| 2025-09 | 27.102 | 23.827 | 87,9 % | 71.452 | 3,00 | 413 |
| 2025-10 | 26.579 | 23.662 | 89,0 % | 76.614 | 3,24 | 405 |
| 2025-11 | — | 23.897 | — | 73.994 | 3,10 | 393 |
| 2025-12 | 27.411 | 24.392 | 89,0 % | 68.176 | 2,80 | 421 |
| 2026-01 | 26.844 | 23.886 | 89,0 % | 72.559 | 3,04 | 432 |
| 2026-02 | 27.290 | 23.269 | 85,3 % | 66.326 | 2,85 | 408 |
| 2026-03 | 26.980 | 23.291 | 86,3 % | 72.932 | 3,13 | 404 |
| 2026-04 | 27.076 | 23.130 | 85,4 % | 68.220 | 2,95 | 420 |
| 2026-05 | 26.815 | 23.437 | 87,4 % | 72.971 | 3,11 | 414 |
| 2026-06 | 31.481 | 26.032 | 82,7 % | 79.982 | 3,07 | 438 |
| 2026-07 | 28.513 | 25.859 | 90,7 % | 89.664 | 3,47 | 439 |
| 2026-08 | 28.735 | 25.675 | 89,4 % | 77.581 | 3,02 | 417 |

**La base de clientes es notablemente estable**: ~23.500 compradores mensuales durante
nueve meses, con retención mes a mes del **90–95 %**. El ticket promedio apenas se mueve
(393–439). Esto no es un negocio con problema de churn.

### El salto de junio–julio no es estacional, es expansión

Las rutas de preventa pasaron de **71 a 95 en junio de 2026** y se mantienen en 95–96.
De los 3.312 clientes nuevos de ese mes, **2.997 están en ALMACÉN ATIZAPÁN**. Es una
apertura comercial, no un pico de demanda. No modelar como estacionalidad.

### Ciclo de vida

| Mes | Nuevos | Recurrentes | Reactivados | Perdidos | Retención |
|---|---:|---:|---:|---:|---:|
| 2025-10 | 1.378 | 22.284 | 0 | 1.543 | 93,5 % |
| 2025-12 | 1.068 | 22.501 | 823 | 1.396 | 94,2 % |
| 2026-03 | 388 | 21.567 | 1.336 | 1.702 | 92,7 % |
| 2026-06 | 3.312 | 21.420 | 1.300 | 2.017 | 91,4 % |
| 2026-08 | 535 | 24.114 | 1.026 | 1.745 | 93,3 % |

Hay un flujo constante de ~1.000–1.300 **reactivados** por mes: clientes que faltaron un
mes y vuelven. No son bajas reales; el churn verdadero es bajo.

---

## 2. Frecuencia intramensual — la pregunta central

**Sí, la mayoría compra más de una vez al mes: el 80,3 %.**
Sobre 290.357 pares cliente-mes: media 3,07 compras, mediana 3, p90 5.

| Compras/mes | % de pares cliente-mes |
|---|---:|
| 1 | 19,7 % |
| 2 | 22,6 % |
| 3 | 22,4 % |
| 4 | 19,7 % |
| 5–6 | 10,4 % |
| 7–9 | 4,9 % |
| 10+ | 0,3 % |

### Pero la frecuencia la fija la ruta, no el cliente

Este es el hallazgo que más condiciona el modelado:

- Intervalo entre compras: **mediana 7 días**, p25 = 7, p75 = 14
- **48,6 % de los intervalos son exactamente 7 días**
- Visitas por cliente-mes: media 4,83 (excluye 2025-11)
- Conversión visita→compra: **64,6 %** (media por cliente-mes; 60,3 % global)

`diaVisita` asigna a cada cliente un día fijo de la semana. El cliente no "decide"
comprar tres veces al mes: **es visitado semanalmente y convierte cerca de 2 de cada 3 visitas.**
La distribución de arriba es, en el fondo, la distribución de cuántas visitas convirtió.

**Implicación para el recomendador:** el *cuándo* ya se conoce (próxima visita
programada). El problema no es predecir timing — es **qué poner en la canasta** y,
secundariamente, **si la visita va a convertir**.

### El descubrimiento no se concentra al inicio del mes

Repartiendo por visita los productos que un cliente compra por primera vez (julio 2026,
20.708 clientes con dos o más visitas):

| Visita del mes | Productos nuevos | % del total | Por visita |
|---:|---:|---:|---:|
| 1ª | 27.134 | 27,0 % | 1,31 |
| 2ª | 26.129 | 26,0 % | 1,26 |
| 3ª | 18.684 | 18,6 % | 1,17 |
| 4ª | 12.613 | 12,6 % | 1,15 |
| 5ª | 6.790 | 6,8 % | 1,08 |

**El 73 % de la adopción ocurre después de la primera visita del mes**, y a un ritmo
notablemente parejo — entre 1,0 y 1,3 productos nuevos por visita, sin agotarse. El cliente no
carga su surtido al principio del mes y luego repite: va incorporando durante todo el ciclo.

Es un dato con consecuencia directa: cualquier lista de sugerencias calculada **una sola vez al
mes es ciega a casi tres cuartas partes de las oportunidades**. Ver
[`docs/diseno/2026-09-13-recomendador-sku.md`](../docs/diseno/2026-09-13-recomendador-sku.md) §7b.

### De qué está hecha la canasta de un mes

Un producto que el cliente compró hace meses y dejó de pedir **no es lo mismo** que uno que
pide cada semana. Separando la canasta de julio 2026 en tres:

| Ventana de «habitual» | Nunca comprado | **Dormido** | Habitual |
|---|---:|---:|---:|
| 1 mes | 39,2 % | **31,7 %** | 29,1 % |
| **2 meses** | 39,2 % | **21,1 %** | 39,6 % |
| 3 meses | 39,2 % | 15,2 % | 45,6 % |

- **Habitual**: lo pidió hace poco. Va a volver a pedirlo por inercia.
- **Dormido**: lo conoce, lo compró alguna vez, y dejó de pedirlo. Un cliente típico tiene
  **24 productos dormidos**.
- **Nunca comprado**: descubrimiento puro.

**Un producto dormido tiene 8,6 veces más probabilidad de comprarse que uno nunca comprado**
(9,67 % contra 1,12 % en un mes dado). Es el pozo más rentable del negocio y el más fácil de
convertir: el cliente ya conoce el producto, ya lo vendió una vez, no hay que convencerlo.

Esto tiene consecuencia directa sobre qué debe sugerir un recomendador. Recomendar lo
**habitual** no aporta —el cliente lo iba a pedir igual—, pero recomendar lo **dormido** sí
suma un SKU al mes. Ver el spec §3.

---

## 3. Canasta

| Métrica | Valor |
|---|---:|
| SKUs distintos por compra (media / mediana / p90) | 3,7 / 3 / 8 |
| Importe mediano por compra | 280 |
| SKUs distintos por cliente-mes (media) | 9,6 |
| SKUs distintos por cliente, toda la historia (mediana) | 31 |

---

## 4. Recompra y repertorio — lo que decide el tipo de modelo

Medir "recompra contra el mes anterior" da **25 %**, que parecería indicar poca lealtad
de canasta. **Es engañoso.** Contra *toda* la historia previa del cliente, el número real
es **56,8 %**, y solo **3,59 SKUs por cliente-mes son realmente nuevos**.

El cliente rota dentro de un repertorio propio; no compra lo mismo cada mes, pero
tampoco descubre constantemente.

### El repertorio no se estabiliza

SKUs acumulados (mediana) de la cohorte de septiembre 2025, por mes de antigüedad:

```
m1: 7   m2:13   m3:17   m4:21   m5:24   m6:26
m7:29   m8:32   m9:35  m10:38  m11:41  m12:44
```

Crece de forma casi lineal, **sin meseta a 12 meses**. Y no es porque entren SKUs nuevos
al catálogo: 364 productos aparecen en el primer mes y después solo debutan 4–34 por mes.
**Es exploración genuina del cliente.**

### Pero el dinero está en el núcleo estable

Clasificando cada par cliente-SKU por en cuántos meses distintos se compró:

| Clase | % de pares | % del importe | Importe medio por par |
|---|---:|---:|---:|
| **Core** (≥3 meses) | 22,0 % | **56,6 %** | 688 |
| 2 meses | 18,7 % | 17,0 % | 244 |
| **One-off** (1 mes) | 59,4 % | 26,4 % | 119 |

Esta es la tensión central del negocio: **el 59,4 % de las combinaciones cliente-SKU
ocurren una sola vez, pero valen apenas un cuarto del importe.** El 22,0 % que es núcleo
estable genera más de la mitad. En mediana, el 34 % del importe de un cliente está en sus
SKUs core.

---

## 5. Viabilidad del recomendador

| Métrica | Valor | Lectura |
|---|---:|---|
| Matriz cliente × producto | 34.485 × 538 | pequeña y manejable |
| Pares observados | 1.391.890 | |
| **Densidad** | **7,50 %** | **muy alta** para filtrado colaborativo |
| SKUs por cliente (mediana / media / p90) | 31 / 40,4 / 88 | |
| SKUs que concentran 80 % del importe | 156 de 538 | cola larga moderada |
| Top-10 SKUs | 17,5 % del importe | sin dominancia extrema |

Un catálogo de retail típico tiene densidad de 0,1 %. **Aquí es 7,50 %** — setenta y cinco
veces más denso. El problema de sparsity que suele hundir al filtrado colaborativo
prácticamente no existe en este dataset.

### Segmentos

**No es clustering.** Es una regla explícita de tres cortes sobre `compras_mes`, definida en
`src/02_eda_clientes.py` (función `seg`). Se evalúa en orden y el primer caso que se cumple manda:

```python
if meses_activo <= 2:   "Esporádico / abandonó"      # se evalúa primero: gana sobre frecuencia
elif compras_mes >= 4:  "Alta frecuencia (semanal)"
elif compras_mes >= 2:  "Media (quincenal)"
else:                   "Baja (mensual)"
# después, sobrescribiendo lo anterior:
if primera_compra >= "2026-07":  "Sin historia suficiente"
```

Donde, por cliente y sobre la tabla `cliente_mes`:

- `meses_activo` = número de meses distintos con al menos una compra
- `compras_mes` = **media de compras por mes activo** (no sobre los 12 meses del periodo)

**Por qué esos umbrales.** No salen de un criterio estadístico sino de la cadencia de ruta,
que es lo que gobierna la frecuencia (§2): un mes tiene ~4,3 semanas, así que ≥4 compras
mensuales equivale a comprar en cada visita; 2–4 es una de cada dos; <2 es mensual o menos.
Se eligió así para que cada segmento sea accionable en términos de ruta.

**El sesgo que no resultó serlo.** Promediar solo sobre meses activos podría inflar a alguien
que estuvo activo pocos meses pero compró mucho en ellos. No ocurre: **el 96,8 % de los de
alta frecuencia estuvieron activos los 12 meses** (mediana 12). El 47,9 % de toda la base
clasificada también.

**Fragilidad de los cortes.** El 7,2 % de los clientes cae a ±0,25 compras/mes de la frontera
alta/media, y el **14,8 % de la frontera media/baja**. Ese segundo corte es blando: mover a un
cliente de «baja» a «media» equivale a una visita más al mes que termine en pedido.

La regla clasifica 32.669 clientes y aparta 1.816 por censura.

| Segmento | Clientes | % clientes | % importe | Compras/mes | SKUs/mes | Importe/año |
|---|---:|---:|---:|---:|---:|---:|
| Media (quincenal) | 16.921 | 49,1 % | **51,9 %** | 2,84 | 10,6 | 11.398 |
| Alta frecuencia (semanal) | 4.800 | 13,9 % | **39,6 %** | 5,33 | 24,6 | 30.673 |
| Baja (mensual) | 7.610 | 22,1 % | 7,3 % | 1,49 | 5,2 | 3.583 |
| Esporádico / abandonó | 3.338 | 9,7 % | 0,7 % | 1,23 | 5,1 | 745 |
| Sin historia suficiente | 1.816 | 5,3 % | 0,5 % | 1,50 | 5,5 | 1.064 |

La concentración es fuerte: **13,9 % de los clientes aporta 39,6 % del importe**, y un cliente
de alta frecuencia vale 8,6 veces más al año que uno de baja. Los dos segmentos inferiores
(31,8 % de la base) suman 8 % del importe.

Los "sin historia suficiente" llegaron en julio/agosto 2026 y **no pueden** tener más de
dos meses: es censura, no abandono. Separarlos evita sobreestimar el churn.

**Limitación.** Al ser una regla fija, no captura interacciones (un cliente de baja frecuencia
pero ticket alto se ve igual que uno de ticket bajo). Si más adelante hace falta segmentar para
el modelo, conviene un RFM o k-means sobre frecuencia, importe y amplitud de surtido — pero para
leer el negocio, una regla explicable gana a un cluster que hay que interpretar.

---

## 6. Salvedades — leer antes de modelar

1. **Censura izquierda.** Los datos empiezan el 2025-09-01: los 23.827 clientes de ese mes
   aparecen como "nuevos" pero son una cohorte mixta de antigüedad desconocida. Las tasas
   de alta solo son interpretables desde 2025-10.

2. **Censura derecha.** El último día es jueves 2026-08-27; a agosto le faltan viernes y
   sábado. Sus totales quedan bajos por construcción — no es una caída.

3. **Noviembre 2025 no tiene registro de visitas sin venta** (0 filas, contra ~15 % en
   todos los demás meses). No es 100 % de conversión: es un hueco de captura. **Excluido
   de toda métrica basada en visitas**; las métricas basadas en compras no se afectan.

4. **Un solo ciclo anual.** Con 12 meses exactos, tendencia y estacionalidad están
   confundidas. No se puede separar una de otra con estos datos.

5. **`PromocionCodigo` no discrimina.** Está poblado en ~100 % de las líneas de compra de
   las tres clases. No es una marca de "hubo promoción"; funciona más como clave de lista
   de precios. Hay 363 valores distintos — habría que entender su semántica antes de
   usarlo como feature.

6. **Duplicados.** 15.362 grupos `fecha+cliente+sku+ruta` con importe idéntico e `Id`
   consecutivos (26.858 filas, 0,5 %) parecen doble inserción de carga. Impacto marginal,
   pero conviene confirmarlo.

---

## 7. Hacia el modelo — qué sugieren estos datos

**El timing está resuelto, la composición no.** El cliente es visitado en un día fijo y
convierte ~65 % de las veces. La pregunta útil es *qué recomendar en la próxima visita*,
no *cuándo*.

Tres implicaciones concretas:

- **Hay dos líneas base y ambas son fuertes.** «Volver a comprar lo de siempre» cubre 56,8 %
  de la canasta. Y el **top-50 de la propia ruta cubre 58,0 %** del surtido histórico del
  cliente, contra 37,8 % del top-50 global (ver `03-analisis-productos.md` §1). El modelo actual de la
  empresa —recomendar lo que compran clientes parecidos de la misma zona— descansa sobre esta
  segunda, y **no es fácil de vencer**. Cualquier propuesta debe compararse contra las dos.

- **El espacio de mejora está dentro de la ruta, no entre rutas.** Agrupar por CEDIS no explica
  nada (39,7 % contra 37,8 % global): el efecto de zona es real y vive a nivel de ruta. Lo que el
  modelo actual no hace es **distinguir entre vecinos de la misma ruta**. Ahí está la hipótesis
  del POC.

- **Hay espacio real para descubrimiento.** Los ~4,9 SKUs genuinamente nuevos por
  cliente-mes y el repertorio que sigue creciendo a 12 meses dicen que el cliente sí
  incorpora productos. Ahí es donde un modelo colaborativo aporta sobre el baseline.

- **La densidad de 7,50 % es una ventaja poco común.** Con 34.485 × 538 y casi 1,4 M de
  pares observados, tanto factorización matricial como item-item collaborative filtering
  son viables sin trucos de cold-start para el grueso de la base.

Dos cosas que faltan y convendría conseguir: **si hubo quiebre de stock** (sin eso, un
"no compró" se confunde con "no había") y **la jerarquía de categorías de producto**
(`marca` y `sku` sueltos no dan estructura para generalizar).

### Artefactos generados

| Ruta | Contenido |
|---|---|
| `datos/derivado/ventas.parquet` | 5,3 M líneas limpias, con banderas `es_compra` / `visita_sin_venta` / `es_pack` |
| `datos/derivado/cliente_mes.parquet` | 290.357 pares cliente-mes: compras, visitas, SKUs, importe |
| `datos/derivado/perfil_clientes.parquet` | 34.485 clientes con segmento y censura |
| `datos/derivado/dim_sku_flags.parquet` | catálogo con banderas `es_pack` / `es_exhibidor` / `activo_ult2m` / `recomendable` |
| `resultados/*.json` | todas las métricas de estos informes |
| `informes/dashboard.html` | informe visual con lectura en lenguaje llano |

Ver el [`README.md`](../README.md) para la tubería completa y cómo reproducirla.
