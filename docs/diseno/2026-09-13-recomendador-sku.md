# Diseño — POC de recomendador de SKUs (Farmalaxia)

Fecha: 2026-09-13 · Estado: propuesto
Antecedentes: [`informes/02-analisis-clientes.md`](../../informes/02-analisis-clientes.md) · [`informes/03-analisis-productos.md`](../../informes/03-analisis-productos.md)

---

## 1. Problema

La empresa ya opera un recomendador: sugiere a cada cliente **8 productos**, basados en lo
que compran clientes parecidos de su misma zona (`rutaPreventa`). El EDA confirmó que esa
premisa es correcta — la ruta aporta entre 15 y 20 puntos de cobertura sobre la lista global,
y el efecto **no** proviene del surtido de almacén (el CEDIS no explica nada más que el
catálogo entero).

El problema no es que el modelo actual esté mal. Es que **no tiene entrada a nivel de cliente**,
así que por diseño no puede distinguir entre dos tiendas de la misma ruta.

**Hipótesis del POC:** personalizar dentro de la ruta supera a la popularidad de ruta sola
(B1, el modelo actual).

### Por qué hay margen

Descomposición de lo que cada cliente compró en un mes de prueba:

| Fuente | Cobertura |
|---|---:|
| Su propia historia | 63,5 % |
| Top-50 de su ruta | 47,9 % |
| Unión de ambas | 74,9 % |
| **Ninguna de las dos** | **25,1 %** |

Sobre "volver a comprar", la lista de ruta aporta apenas **11,4 puntos**.

### No hay loop de retroalimentación

Se verificó la hipótesis de que el modelo actual empuje a todos los clientes hacia la misma
canasta. **No está ocurriendo:** la concentración en el top-50 pasó de 53,2 % a 52,0 %, los
productos distintos vendidos subieron de 364 a 418, y en las rutas estables el parecido entre
vecinos **bajó** de 0,073 a 0,057. El tope del modelo actual no es convergencia, es resolución.

---

## 2. Alcance

**Dentro:** POC reproducible en Python que cuantifica la mejora posible y entrega la
importancia de cada variable.

**Fuera:** recomendación a nivel de visita individual (evaluada y documentada en §7b como
siguiente iteración), predicción de quiebre de stock, optimización de promociones, integración
operativa, despliegue.

**No es un piloto.** Mide capacidad de predicción, no impacto causal. Ver §8.

---

## 3. La tarea

| | |
|---|---|
| **Unidad** | cliente-mes |
| **Candidatos** | SKU `recomendable` que el cliente **no está comprando ahora**: los que no pidió en los últimos **2 meses** (~403) |
| **Positivos** | los candidatos que sí compró en el mes *t* |
| **Salida** | los **8** productos mejor puntuados |

### Tres clases de producto, no dos

Una versión anterior de este diseño excluía todo lo que el cliente hubiera comprado alguna vez.
Era un error: mezclaba dos situaciones que no se parecen.

| Clase | Definición | ¿Candidato? |
|---|---|---|
| **Habitual** | lo pidió en los últimos 2 meses | **No.** Lo va a pedir por inercia; acertarle infla la métrica sin generar venta. |
| **Dormido** | lo compró alguna vez pero no en los últimos 2 meses | **Sí.** Recordárselo suma un SKU al mes. |
| **Nunca** | no lo ha comprado jamás | **Sí.** Descubrimiento puro. |

Composición real de la canasta de julio 2026: **39,2 % nunca comprado, 21,1 % dormido,
39,6 % habitual**. Excluir lo dormido descartaba un quinto de la oportunidad.

**Y el pozo dormido es el más productivo:** un cliente arrastra ~24 productos dormidos, y cada
uno tiene **8,6 veces más probabilidad** de comprarse que uno nunca comprado (9,67 % contra
1,12 % en un mes dado).

### Dos políticas de asignación de espacios

Las 8 sugerencias se reparten de dos maneras, y **cada modelo se evalúa bajo ambas**:

| Política | Regla |
|---|---|
| **Libre** | los 8 mejor puntuados, sin importar el origen |
| **Mixta 5+3** | los 5 mejores `dormido` y los 3 mejores `nunca`. Si a un cliente le faltan candidatos de una clase, los espacios sobrantes se llenan con la otra por puntuación. |

**Medido sobre B1 (julio 2026, muestra de 2.387 clientes):**

| Política | hit-rate@8 | Aciertos por cliente | % de aciertos que son descubrimiento |
|---|---:|---:|---:|
| Libre | 47,4 % | 0,95 | 46 % |
| **Mixta 5+3** | **53,0 %** | 1,00 | 39 % |

La cuota **no cuesta desempeño: lo mejora en 5,6 puntos.** B1 ordena por popularidad de ruta,
que no distingue origen; como el 94 % de los candidatos son «nunca comprados», la lista libre
se llena de ellos y entierra los dormidos, que son 8,6 veces más probables. Forzar cinco
espacios los rescata.

**La cuota es, por sí sola, una mejora barata sobre el modelo actual** — sin modelo de por
medio. Se reporta como tal.

El precio es de composición, no de volumen: el descubrimiento baja de 46 % a 39 % de los
aciertos (1.045 → 944 en la muestra). Si el objetivo es ampliar el surtido del cliente y no
solo subir SKU por visita, ese punto merece discusión con el negocio.

### Comparar siempre dentro de la misma política

Un modelo evaluado con cuota contra un B1 evaluado libre se llevaría el crédito de la cuota.
**Toda comparación es B1-libre contra P*-libre, y B1-mixta contra P*-mixta.**

### Consecuencia: el desglose es obligatorio

Con 24 dormidos por cliente y solo 8 espacios, **un modelo puede llenar la lista entera de
reactivaciones fáciles y no descubrir nada, luciendo excelente**. Toda métrica se reporta
además desglosada entre `origen = dormido` y `origen = nunca`. Sin ese corte, el número
principal es engañoso.

**Aclaración sobre el «8».** La empresa sugiere 8 productos; el POC evalúa **8 por
cliente-mes**, no 8 por visita. Si su sistema emite 8 en cada visita, el nuestro hace
~3,5 veces menos sugerencias al mes, así que la comparación **nos es desfavorable** —
preferible a inflar el resultado. La recomendación por visita queda fuera de alcance (§2)
y sería el paso natural después. **Conviene confirmar con la empresa si sus 8 son por
visita o por periodo**, porque cambia la lectura del resultado.

**Solo productos nuevos para el cliente.** Recomendar lo que ya compra siempre acierta y no
aporta: el cliente lo iba a pedir igual. El valor está en lo que aún no lleva.

**Sin restricción de candidatos.** Se midió el techo alcanzable por fuente: top-100 de ruta
alcanza 65,1 %, una mezcla de fuentes 83,4 %, y el catálogo completo **94,7 %**. Como el
catálogo recomendable es pequeño (428), abrirlo cuesta poco y evita descartar de antemano
productos que el modelo podría acertar.

---

## 4. Línea base y propuestas

Todo ordena **el mismo conjunto de candidatos**.

### La línea base es B1 — lo que la empresa tiene hoy

| | Criterio de orden |
|---|---|
| **B1** | popularidad en la ruta del cliente ← **la vara: el modelo actual** *(reconstruido)* |
| B0 | popularidad global — solo como referencia, para dimensionar cuánto aporta la ruta |

### Nuestras propuestas, de menor a mayor costo

| | Qué agrega sobre B1 |
|---|---|
| **P1** | filtra la lista de ruta a **marcas que el cliente ya compra**. Sale del EDA: 79,8 % de los productos nuevos que adopta un cliente son de una marca que ya le compra. Veinte líneas de código. |
| **P2** | ítem-ítem: co-ocurrencia con lo que el cliente ya lleva |
| **P3** | ranker LightGBM con todas las variables |

**P1, P2 y P3 son aportes nuestros**, no versiones del sistema de ellos. La empresa no aplica
el filtro por marca; es un hallazgo de este análisis.

### Dos comparaciones distintas, ambas necesarias

- **P* contra B1** → *¿cuánto mejora esto lo que hay hoy?* Es la cifra del foro comercial y la
  que define el éxito del POC (§10).
- **P3 contra P1** → *¿el modelo complejo se gana su lugar frente a un filtro de veinte líneas?*
  Es una decisión de ingeniería, no de negocio, pero hay que responderla honestamente: si P1
  captura casi todo el margen, lo correcto es recomendar P1 y no operar un modelo.

---

## 5. Modelos

### Modelo 1 — ítem-ítem (P2, primera entrega)

Puntúa cada candidato por co-ocurrencia con los productos que el cliente ya compra.
Explicable en una frase y no requiere entrenamiento. Aprovecha el hallazgo de afinidad de
línea de sabor del EDA.

### Modelo 2 — ranker LightGBM (LambdaRank)

- **Objetivo:** `lambdarank`, grupo = cliente-mes
- **Positivos:** SKU nuevos comprados en el mes; **negativos:** el resto de los candidatos
- **Submuestreo:** para controlar tamaño se entrena con una muestra aleatoria de ~8.000
  clientes por mes (≈3,2 M filas/mes). **La evaluación usa todos los clientes.**
- Semilla fija y registrada.

No se usa factorización matricial en el POC: es menos explicable y la importancia de
variables es parte del entregable.

---

## 6. Variables

| Familia | Variables |
|---|---|
| **Ruta** | popularidad LOO del SKU en la ruta, su rango dentro de la ruta |
| **Marca** | ¿el cliente compra esa marca?, peso de la marca en su canasta histórica, nº de SKU de la marca que ya lleva |
| **Afinidad** | co-ocurrencia máxima y media con los SKU que el cliente ya compra |
| **Producto** | popularidad global, precio, % de compradores que lo vuelven básico, meses disponible |
| **Cliente** | segmento de frecuencia, tamaño medio de canasta, antigüedad, ticket medio, nº de SKU distintos |

### Control de fuga de información — requisito, no recomendación

1. Toda variable del mes *t* se calcula **solo con meses < t**.
2. La popularidad de ruta **descuenta al propio cliente** (leave-one-out).
3. Los estadísticos de producto se calculan **solo sobre meses de entrenamiento**.
4. `datos/derivado/dim_sku_flags.parquet` → `activo_ult2m` está calculado sobre el periodo completo: **debe recalcularse
   por mes** o no usarse como filtro durante el entrenamiento.
5. Las 24 rutas abiertas en junio de 2026 tienen ≤3 meses de historia: **se reportan aparte**,
   su B1 es inestable.

---

## 7. Evaluación

**Partición temporal:** entrenar ≤ 2026-05 · validar 2026-06 · **probar 2026-07**.

Julio y no agosto: agosto termina en jueves 27 y le faltan viernes y sábado.

### Métricas

**Principal — `hit-rate@N`:** fracción de cliente-mes en que **al menos uno** de los N
sugeridos fue comprado.

**Población: todos los clientes con historia previa**, incluyendo el 11 % que en el mes de
prueba no adoptó ningún producto nuevo. Para esos ningún recomendador puede acertar, pero
son parte de la realidad operativa: el preventista los visita igual. La pregunta que responde
la métrica es *de cada 100 clientes visitados, en cuántos le atinamos a algo nuevo*.

Consecuencia: el `hit-rate@8` de B1 medido en el EDA (36,5 %) se calculó **solo sobre los
21.871 clientes que sí adoptaron algo**. Sobre los 24.578 con historia previa, el mismo B1
equivale a **~32,5 %**. Ambas cifras se reportan; la comparación entre modelos es válida en
cualquiera de las dos porque todos se miden sobre la misma población. **N = 8 es el titular**, pero se reporta la **curva completa para
N ∈ {3, 5, 8, 16, 24, 40}**.

Por qué la curva y no un solo número: la empresa dice emitir 8 recomendaciones, pero no está
confirmado si son 8 **por visita** o 8 **por periodo**. Con ~4,8 visitas al mes, la diferencia
es enorme — y ya está medida sobre B1 en julio de 2026:

| Sugerencias | hit-rate | SKU extra por compra | Precisión |
|---:|---:|---:|---:|
| 3 | 22,3 % | 0,089 | 10,30 % |
| 5 | 29,0 % | 0,138 | 9,57 % |
| **8** | **36,5 %** | **0,201** | **8,70 %** |
| 16 | 49,8 % | 0,322 | 6,97 % |
| 24 | 59,1 % | 0,417 | 6,02 % |
| 40 | 70,8 % | 0,563 | 4,88 % |

Reportar un solo punto expone el informe: si se presenta «el modelo actual acierta 36,5 %» ante
alguien que sabe que su sistema rinde más porque dispara en cada visita, se pierde credibilidad
aunque el número sea correcto para 8 por periodo. **La curva se sostiene en cualquier punto de
operación.** También hace visible el intercambio: de 8 a 40 sugerencias el acierto casi se
duplica, pero la precisión cae de 8,70 % a 4,88 % — más renglones para el preventista y menos
confianza en cada uno.

Secundarias: `recall@N`, `precision@N`, `MAP@N` sobre la misma malla.

**La vara ya está medida: B1 alcanza `hit-rate@8` = 36,5 %.** El umbral de éxito (§10) son
41,5 %.

**Importancia de variables** (ganancia): cuánto aporta cada pista. Es parte del entregable
principal, no un apéndice — responde *dónde conviene invertir*.

### Traducción a negocio

Referencias medidas en el mes de prueba: un cliente incorpora productos nuevos por
**634 pesos/mes** en promedio (mediana 413), con **3,47 compras/mes**, o sea ~183 pesos por
compra.

```
SKUs adicionales por compra = aciertos por cliente-mes ÷ 3,47
Pesos por compra            = SKUs adicionales × precio medio de los aciertos
```

**Tabla de escenarios.** Como los datos no distinguen "lo compró porque se lo sugerimos" de
"lo iba a comprar igual", el impacto se presenta con la perilla visible: si el preventista
convierte 10 / 20 / 30 % de las sugerencias que el cliente no habría comprado por su cuenta,
el impacto anual es A / B / C. **No se reporta un número único de impacto.**

---

## 7b. Siguiente iteración — recomendar por visita, no por mes

**Fuera del alcance de este POC**, pero medido y documentado aquí porque condiciona qué datos
conviene empezar a guardar **hoy**.

La idea: en vez de calcular una lista al inicio del mes, recalcularla en **cada visita**,
usando lo que el cliente ya compró en las visitas anteriores de ese mismo mes.

### Sí hay margen — está medido

Sobre julio de 2026, con los 20.708 clientes que tuvieron dos o más visitas:

| Visita del mes | Productos nuevos adoptados | % del total |
|---:|---:|---:|
| 1ª | 27.134 | 27,0 % |
| 2ª | 26.129 | 26,0 % |
| 3ª | 18.684 | 18,6 % |
| 4ª | 12.613 | 12,6 % |
| 5ª y siguientes | 15.773 | 15,8 % |

**El 73 % de la adopción ocurre después de la primera visita**, a un ritmo parejo de ~1,2
productos nuevos por visita. Una lista calculada una sola vez al mes es ciega a casi tres
cuartas partes de las oportunidades.

Y la señal existe: **17,3 % de los productos nuevos adoptados tras una visita estaban entre los
20 «vecinos» por co-ocurrencia de lo comprado en la visita inmediatamente anterior**
(12.640 de 73.199). Veinte productos son el 5 % del catálogo recomendable y capturan el 17 % de
las adopciones — unas 3,5 veces mejor que al azar.

### Tres advertencias

1. **El objetivo es más escaso.** Una visita trae ~3,7 SKU contra ~9,6 del mes, así que las
   métricas absolutas se verán peores. Es otro denominador, no una regresión. Hay que decirlo
   antes de mostrar los números o se leerá como que el modelo empeoró.
2. **No se puede aprender de los rechazos, porque no existen en los datos.** `tblVentas`
   registra compras, no ofertas: no hay forma de saber qué se recomendó y el cliente no tomó.
   «No repetir lo que rechazó» solo puede ser una regla de negocio, no una variable aprendida.
3. **Sube el costo operativo:** la recomendación tiene que calcularse en campo o precalcularse
   por visita, no una vez al mes.

### Acción recomendada para hoy, sin costo

**Empezar a registrar qué se recomienda y qué se compra de eso.** Ese dato no existe, no se
puede reconstruir hacia atrás, y es lo único que permitiría más adelante (a) aprender de los
rechazos, (b) medir el impacto real del recomendador actual, y (c) evaluar sin depender de
reconstrucciones como B1. Cada mes que pasa sin registrarlo es un mes de aprendizaje perdido.

---

## 8. Limitaciones — van en el informe final

1. **B1 es una reconstrucción.** La empresa confirmó que no conserva las recomendaciones que
   su modelo generó, así que comparamos contra su lógica descrita —popularidad entre clientes
   parecidos de la misma ruta— y no contra sus resultados reales. Es la limitación más
   importante del POC: si su implementación difiere de lo que entendimos, la vara se mueve.
2. **La evaluación es predictiva, no causal.** Acertar qué comprará un cliente no prueba que
   la sugerencia lo cause. **Solo un piloto con grupo de control** —unas rutas reciben las
   sugerencias y otras no— mide impacto real. Es la fase siguiente.
3. **Sin señal de faltante de stock:** un "no compró" puede ser "no había".
4. **Sin jerarquía de categorías:** marca es el nivel más fino disponible.
5. **Un solo ciclo anual:** tendencia y estacionalidad están confundidas.
6. **5,3 % del importe** proviene de SKU de paquete promocional excluidos del análisis.

---

## 9. Estructura

```
features.py          construye la matriz cliente-mes × candidato, sin fuga
baselines.py         B1 (modelo actual) y B0; propuestas P1 y P2
modelo_ranker.py     entrenamiento LightGBM + importancia de variables
evaluar.py           métricas, traducción a negocio, escenarios
RESULTADOS.md        informe final
```

El directorio no es repositorio git: inicializarlo es el primer paso del plan, con
`.gitignore` para `*.bak`, `*.tsv`, `*.parquet` y `.venv/`.

Dependencia nueva: `lightgbm`.

---

## 10. Criterio de éxito

El umbral se fija **antes** de ver los resultados, para no acomodarlo después:

> El POC es exitoso si **la mejor de nuestras propuestas supera el `hit-rate@8` de B1 —el
> modelo actual— en al menos 5 puntos porcentuales absolutos** en el mes de prueba, y la
> importancia de variables identifica qué señales producen esa diferencia.
>
> **B1 libre: ~47 %. B1 mixta 5+3: ~53 %.** El umbral de éxito es **superar a B1 en 5 puntos
> dentro de la misma política**: ~52 % en libre, ~58 % en mixta.
>
> La vara se movió tres veces conforme se corrigieron el alcance y la definición de candidato
> (36,5 % → 32,5 % → ~47 %). **Queda fija aquí.** El orquestador la mide exactamente sobre el
> conjunto de prueba completo y ese valor es el de referencia; si difiere de ~47 % por más de
> 3 puntos, hay una discrepancia que revisar antes de interpretar nada.
>
> Además: **el 54 % de los aciertos de B1 son reactivación.** Una propuesta que suba el número
> total pero baje el descubrimiento no es mejor, es distinta — y hay que decirlo.
>
> La mejora debe sostenerse a lo largo de la curva de N, no solo en N = 8.

Cinco puntos porque por debajo de eso la diferencia no sobrevive al ruido de un solo mes de
prueba ni justifica el costo de cambiar algo que ya opera.

Se reportará además el intervalo de confianza por *bootstrap* sobre clientes, para distinguir
una mejora real de una casualidad del mes elegido.

**Recomendación de ingeniería, aparte del criterio de éxito.** Si P3 no supera a P1 por margen
propio, el informe recomendará **P1** — el filtro por marca— aunque el POC sea exitoso frente
a B1. Vale más entregar veinte líneas que funcionan que un modelo que no se gana su
mantenimiento.

Si ninguna propuesta supera a B1 por 5 puntos, el resultado también es útil: significa que la
popularidad de ruta ya captura casi todo lo predecible con los datos disponibles, y que el
camino no es un mejor modelo sino **mejores datos** — quiebre de stock y jerarquía de
categorías (§8). Es un desenlace válido y se reporta como tal.
