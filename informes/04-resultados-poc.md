# Resultados del POC — recomendador de SKUs

Mes de prueba **2026-07** · 24.578 clientes ·
403 candidatos por cliente · 1,635 % de positivos

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

| Modelo | hit-rate@8 | IC 95 % | vs B1 | Aciertos dormido | Aciertos nunca |
|---|---:|---:|---:|---:|---:|
| B0 · popularidad global | 37,22 % | [36,64 – 37,95] | −11,45 | 8.656 | 5.101 |
| **B1 · popularidad de ruta** *(modelo actual)* | 48,67 % | [48,09 – 49,32] | — | 12.667 | 11.547 |
| P1 · ruta + marca conocida | 50,93 % | [50,34 – 51,61] | +2,26 | 13.913 | 10.945 |
| P2 · afinidad ítem-ítem | 52,00 % | [51,43 – 52,66] | +3,33 | 16.085 | 12.806 |
| P3 · ranker LightGBM | 58,79 % | [58,33 – 59,41] | +10,12 | 23.394 | 7.024 |

**Se alcanzó el umbral.** P3 supera a B1 en **10,12 puntos** (48,67 % → 58,79 %), por encima de los 5 exigidos.

## 3. Resultados — política mixta (5 dormidos + 3 nunca)

| Modelo | hit-rate@8 | IC 95 % | vs B1 | Aciertos dormido | Aciertos nunca |
|---|---:|---:|---:|---:|---:|
| B0 · popularidad global | 47,34 % | [46,74 – 47,98] | −6,50 | 15.676 | 3.469 |
| **B1 · popularidad de ruta** *(modelo actual)* | 53,84 % | [53,26 – 54,53] | — | 15.080 | 10.357 |
| P1 · ruta + marca conocida | 53,46 % | [52,97 – 54,13] | −0,38 | 15.080 | 10.221 |
| P2 · afinidad ítem-ítem | 52,75 % | [52,23 – 53,37] | −1,09 | 15.852 | 11.949 |
| P3 · ranker LightGBM | 57,60 % | [57,08 – 58,17] | +3,76 | 17.655 | 10.671 |

**No se alcanzó el umbral.** La mejor propuesta (P3) supera a B1 en 3,76 puntos, por debajo de los 5 exigidos (objetivo 58,84 %). Significa que la popularidad de ruta ya captura casi todo lo predecible con los datos disponibles, y que el camino no es un mejor modelo sino **mejores datos**.

## 4. Curva de N — política libre

| N | B1 hit-rate | P3 hit-rate | B1 precisión | P3 precisión |
|---:|---:|---:|---:|---:|
| 3 | 31,54 % | 40,68 % | 15,22 % | 19,77 % |
| 5 | 40,54 % | 50,25 % | 13,86 % | 17,67 % |
| 8 | 48,67 % | 58,79 % | 12,31 % | 15,47 % |
| 16 | 61,79 % | 71,49 % | 9,62 % | 12,28 % |
| 24 | 70,35 % | 77,88 % | 8,19 % | 10,42 % |
| 40 | 79,05 % | 84,44 % | 6,65 % | 8,15 % |

## 5. Importancia de variables

| Variable | Ganancia | % |
|---|---:|---:|
| peso_marca | 171.847,0 | 30,2 % |
| afin_max | 150.282,7 | 26,4 % |
| es_dormido | 49.691,7 | 8,7 % |
| pop_global | 42.701,5 | 7,5 % |
| precio | 39.867,8 | 7,0 % |
| rango_ruta | 28.910,0 | 5,1 % |
| meses_disponible | 22.448,3 | 3,9 % |
| pct_core | 21.596,7 | 3,8 % |
| afin_suma | 10.372,0 | 1,8 % |
| pop_ruta | 9.608,9 | 1,7 % |
| n_compras_cliente | 7.293,2 | 1,3 % |
| marca_conocida | 4.422,1 | 0,8 % |
| n_skus_cliente | 3.914,7 | 0,7 % |
| ticket_medio | 3.781,2 | 0,7 % |
| skus_de_la_marca | 2.573,2 | 0,5 % |

## 6. Traducción a negocio — política libre

Con **P3** y 8 sugerencias por cliente-mes:

| Métrica | Valor |
|---|---:|
| Aciertos por cliente-mes | 1,238 |
| **SKU adicionales por compra** | **0,357** |
| Importe de los aciertos, por cliente-mes | 57,2 |
| De los aciertos, cuántos son descubrimiento | 23,1 % |

### Qué significa «57,2 pesos por cliente», y qué no

Es la cifra más fácil de malinterpretar, así que conviene desarmarla. Son **tres
números distintos**, cada uno más pequeño que el anterior, y solo el tercero es venta nueva.

**1 · El valor de lo que el modelo acierta — 57,2 pesos.** Es la suma de los
productos que P3 sugirió y el cliente efectivamente compró ese mes. Ojo con la unidad:
son pesos **por cliente y por mes**, repartidos entre 3,47 visitas. Por visita son
16,5 pesos sobre un ticket medio de 439 — es decir, el
**3,8 %** de lo que ese cliente ya gasta al mes
(1.520 pesos). Compararla contra el ticket de **una** visita da
13 % y es la lectura equivocada: cruza un mes contra una visita.

**2 · La ganancia sobre el sistema actual — 16,0 pesos.** El modelo de hoy (B1) ya
acierta 41,2 pesos por cliente-mes por su cuenta. Lo que cambia por reemplazarlo
es la diferencia: 16,0 pesos al mes, 4,6 por visita, el
**1,1 %** del gasto mensual del cliente. Nadie va a facturar dos
veces lo que B1 ya acertaba.

| Concepto | Pesos/cliente-mes | Por visita | % del gasto mensual |
|---|---:|---:|---:|
| Acierta el sistema actual (B1) | 41,2 | 11,9 | 2,7 % |
| Acierta el modelo propuesto (P3) | 57,2 | 16,5 | 3,8 % |
| **Diferencia — lo que aporta el cambio** | 16,0 | 4,6 | 1,1 % |

**3 · Cuánto de eso lo causó la sugerencia — no se sabe, y por eso son escenarios.** Este es
el punto clave: **el POC mide aciertos, no ventas incrementales.** El mes evaluado ya ocurrió y ningún
vendedor vio estas recomendaciones; lo que se midió es que el modelo predijo bien qué iba a
comprar el cliente. Un acierto puede significar dos cosas muy distintas — que la sugerencia
provocó la compra, o que el cliente lo iba a pedir igual y el modelo simplemente lo adivinó.
**Los datos no distinguen una de la otra.**

Hay una razón concreta para no ser optimista: el 76,9 % de los
aciertos son productos **dormidos**, que el cliente ya compró antes y conoce de sobra. Son
precisamente los que tenía más probabilidad de volver a pedir sin ayuda de nadie.

Por eso la «tasa de conversión» de la tabla siguiente responde a una pregunta muy concreta:
**de cada 10 productos que el modelo acierta, ¿cuántos el cliente no habría pedido si el
vendedor no se los menciona?** Es un supuesto de negocio, no un resultado del análisis.

### Escenarios de impacto sobre 24.578 clientes

Sobre la ganancia del cambio (16,0 pesos por cliente-mes) — **esta es la tabla que
hay que mirar para decidir si vale la pena reemplazar el modelo actual**:

| Si se convierte… | Mensual | Anual |
|---:|---:|---:|
| 10 % | 39.325 | 471.898 |
| 20 % | 78.650 | 943.795 |
| 30 % | 117.974 | 1.415.693 |

La banda de trabajo razonable es **20–30 %**: entre 943.795 y
1.415.693 pesos al año. Un 10 % es el piso prudente; por encima del 30 % habría
que sostener que una de cada tres sugerencias acertadas cambia de verdad la decisión del
cliente, cosa que ningún dato de este análisis respalda.

Para referencia, la tabla equivalente sobre el importe **total** de los aciertos de P3
(57,2 pesos), que es la que sale directa del cálculo del POC:

| Si se convierte… | Mensual | Anual |
|---:|---:|---:|
| 10 % | 140.586 | 1.687.034 |
| 20 % | 281.172 | 3.374.068 |
| 30 % | 421.758 | 5.061.102 |

Esta segunda tabla **no mide la ganancia del cambio** — incluye lo que B1 ya acertaba hoy.
Sirve para dimensionar el canal completo de recomendación, no para justificar el proyecto.

### Dos precisiones de método

- **El importe cuenta una pieza por SKU acertado**, valorada al precio unitario medio de ese
  producto. Una línea de pedido real promedia más de una pieza, así que por este lado la cifra
  es conservadora.
- **El juego está acotado por diseño.** El modelo solo puede recomendar productos que el
  cliente **no pidió en los últimos dos meses**. Lo habitual, que es el grueso de la factura,
  queda fuera a propósito: el cliente lo iba a pedir de todos modos.

⚠️ **Nada de esto es un uplift medido.** Solo un piloto con grupo de control —mismas rutas,
unos vendedores con las sugerencias nuevas y otros con las de hoy— convierte estos escenarios
en una cifra. Ese es el siguiente paso, y hasta entonces la conversión es una perilla que el
negocio gira, no un dato del análisis.


## 7. Desglose por antigüedad de ruta

| Rutas | Clientes | B0 | B1 | P1 | P2 | P3 |
|---|---:|---:|---:|---:|---:|---:|
| estables | 22.176 | 41,23 % | 45,58 % | 48,58 % | 49,92 % | 57,33 % |
| nuevas jun2026 | 2.402 | 0,25 % | 77,23 % | 72,69 % | 71,15 % | 72,23 % |


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
