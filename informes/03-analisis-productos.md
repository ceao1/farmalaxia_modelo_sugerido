# EDA — Lado de producto (`dbventas.tblVentas`)

Complemento de [`02-analisis-clientes.md`](02-analisis-clientes.md). Reproducible con
`./.venv/bin/python src/03_eda_productos.py` → `resultados/eda_productos.json` + `datos/derivado/dim_sku_flags.parquet`.

---

## 0. El catálogo no es lo que aparenta

`tblVentas` tiene 883 SKUs distintos. **Solo 538 son mercancía.**

Los 345 restantes llevan prefijo `PP*` y son **registros de mecánica
promocional**, no productos:

- Importe **exactamente 0,00** en las 905.802 líneas — ninguna excepción
- Precio 0 en el 100 % de los casos
- `PromocionCodigo` poblado en el 100 %
- Son el **19,8 % de las líneas de compra** y aparecen en el 63 %
  de las canastas, acompañando compra real (solo 16 canastas son exclusivamente packs)
- Sus descripciones son combinaciones: `1 SAL DE UVAS PICOT + 1 VANISH OXI ACTION`

**Esto contamina cualquier métrica de surtido.** Con ellos dentro, la afinidad entre productos
devuelve paquetes correlacionados consigo mismos (lifts de 7.000) y el conteo de productos por
cliente se infla un 40 %. Las cifras de [`02-analisis-clientes.md`](02-analisis-clientes.md) fueron corregidas.

### Lista de exclusión para el modelo → `datos/derivado/dim_sku_flags.parquet`

| Bandera | SKUs | Motivo |
|---|---:|---|
| `es_pack` | 345 | registro promocional, importe 0 |
| `es_exhibidor` | 17 | exhibidores, muebles y material de exhibición: no es mercancía |
| `activo_ult2m` = falso | 108 | sin una sola venta en los últimos 2 meses |
| **`recomendable`** | **428** | **lo que un recomendador puede proponer sin equivocarse** |

De 883 SKUs aparentes, **428 son recomendables**.

### Otro detalle de calidad

4 descripciones tienen los acentos corrompidos: `PIÑA` aparece como
`PINA`, y `NIÑO` como `NI209;O209;O` (entidad HTML mal decodificada). No afecta el análisis porque
se agrupa por `sku`, pero sí afectaría cualquier pantalla que muestre el nombre al preventista.

---

## 1. ¿La zona explica qué compra un cliente? — la pregunta del modelo actual

El modelo en producción recomienda *lo que compran clientes parecidos de la misma zona*, y «zona»
corresponde a `rutaPreventa`. Medimos cuánto del surtido histórico de cada cliente queda cubierto
por el top-N de su ruta, de su CEDIS y global.

Método: **leave-one-out** — al calcular el top de cada ruta se descuenta la contribución del propio
cliente, si no la prueba se cumpliría sola. Solo rutas con ≥30 clientes.

| Lista | top-20 | top-50 | top-100 |
|---|---:|---:|---:|
| **Su ruta** | 36,7 % | **58,0 %** | 75,8 % |
| Su CEDIS | 21,5 % | 39,7 % | 58,1 % |
| Global | 21,0 % | 37,8 % | 57,1 % |
| *Ganancia ruta sobre global* | *+15,6 pp* | *+20,2 pp* | *+18,7 pp* |

**La premisa del modelo actual se sostiene.** La ruta aporta entre 15 y 20 puntos sobre la lista
global — no es un efecto marginal.

**Y el efecto no es disponibilidad de almacén.** El CEDIS explica prácticamente lo mismo que el
catálogo entero (39,7 % contra 37,8 %). Si la
ruta funcionara solo porque cada bodega surte cosas distintas, el CEDIS mostraría una ganancia
parecida. No la muestra. **La ruta captura preferencia local real** — barrio, tipo de tienda,
clientela — no surtido.

El parecido entre rutas lo confirma: comparten **0,306** de su top-30 dentro del
mismo CEDIS y **0,148** entre CEDIS distintos. Las rutas son genuinamente
distintas entre sí.

> **Implicación para el POC.** La línea base a vencer es *popularidad de la ruta*, y es fuerte:
> una lista de 50 productos ya cubre 58,0 % de lo que el cliente compra.
> Lo que el modelo actual **no** hace es distinguir entre vecinos de la misma ruta. Esa es la
> hipótesis a probar: personalización dentro de la zona, no mejor geografía.

⚠️ Esto mide **cobertura del surtido histórico**, no aciertos del modelo actual — no tenemos sus
predicciones. Es una cota de referencia, no su desempeño medido.

---

## 2. Concentración y cola larga

| Corte | Productos |
|---|---:|
| 50 % del importe | **55** |
| 80 % del importe | 156 |
| 95 % del importe | 283 |

Penetración mediana de un producto: **4,83 % de los clientes**.
Es una cola larga moderada: hay concentración, pero ningún producto domina y queda mucho espacio
de surtido sin explotar.

### Marcas (top 10 por importe)

| Marca | % importe | Penetración | Productos |
|---|---:|---:|---:|
| EFFEM | 16,5 % | 45,1 % | 52 |
| CONAGRA | 16,4 % | 37,8 % | 58 |
| UNILEVER | 15,2 % | 53,8 % | 92 |
| COLGATE | 10,7 % | 50,6 % | 63 |
| QUALA | 7,6 % | 41,0 % | 34 |
| FERRERO | 6,0 % | 41,0 % | 37 |
| EMPACADORA SAN MARCOS | 4,0 % | 38,2 % | 11 |
| BEPENSA | 3,3 % | 27,3 % | 15 |
| CAMPARI | 2,8 % | 18,8 % | 10 |
| UPFIELD | 2,4 % | 37,4 % | 7 |

---

## 3. Afinidad entre productos

Canasta = `(cliente, fecha)`. 890.455 canastas, 13.196 pares
con al menos 100 co-ocurrencias.

Ordenado por **frecuencia**, no por *lift*: ordenar por lift saca pares raros de soporte mínimo que
parecen señal y no lo son.

| Producto | Va junto con | Canastas | Lift | Confianza |
|---|---|---:|---:|---:|
| ACT II MANTEQUILLA | ACT II EXTRA MANTEQUILLA | 43.300 | 10,9 | 89,8 % |
| PEDIGREE PANC POUCH POLLO 100 GR | PEDIGREE PANC POUCH RES 100 GR | 34.844 | 13,1 | 80,1 % |
| WHISKAS POUCH ATUN 85 GR | WHISKAS POUCH SALMON 85 GR | 31.894 | 14,6 | 68,8 % |
| WHISKAS POUCH ATUN 85 GR | WHISKAS POUCH PARRILLADA MIXTA 85 GR | 31.722 | 15,0 | 68,4 % |
| WHISKAS POUCH ATUN 85 GR | WHISKAS POUCH POLLO 85 GR | 31.673 | 14,7 | 68,3 % |
| WHISKAS POUCH PARRILLADA MIXTA 85 GR | WHISKAS POUCH POLLO 85 GR | 30.543 | 16,2 | 75,4 % |
| WHISKAS POUCH PARRILLADA MIXTA 85 GR | WHISKAS POUCH SALMON 85 GR | 29.713 | 15,6 | 73,3 % |
| WHISKAS POUCH RES 85 GR | WHISKAS POUCH POLLO 85 GR | 29.517 | 16,6 | 77,2 % |
| WHISKAS POUCH SALMON 85 GR | WHISKAS POUCH POLLO 85 GR | 29.407 | 15,1 | 70,3 % |
| WHISKAS POUCH ATUN 85 GR | WHISKAS POUCH RES 85 GR | 28.836 | 14,5 | 62,2 % |

El **32,0 %** de los pares frecuentes son de la misma marca, pero los más
fuertes lo son casi todos. **El patrón dominante es la línea de sabor**: quien lleva Whiskas atún
lleva también salmón y pollo. No aparecen combinaciones sorprendentes entre categorías distintas.

> Pista barata para el modelo: si un cliente compra 3 de los 5 sabores de una línea, los 2 que le
> faltan son la sugerencia más obvia — y la más fácil de explicar al preventista.

---

## 4. Recompra por producto

Qué productos se vuelven básicos y cuáles se prueban una vez.

**Control importante:** un producto que solo existió 2 meses **no puede** tener compradores de ≥3
meses. Sin controlar disponibilidad, la mediana daba 6,8 % y la lista de «menos recomprados» era
en realidad una lista de productos recién lanzados. Restringido a los
276 productos con ≥200 compradores **y disponibles los 12 meses**, la mediana real es
**16,6 %**.

### Básicos — alta recompra

| Producto | Marca | Compradores | % que lo vuelve básico |
|---|---|---:|---:|
| ACT II EXTRA MANTEQUILLA | CONAGRA | 11.133 | 67,7 % |
| ACT II MANTEQUILLA | CONAGRA | 9.633 | 58,1 % |
| IBERIA MARGARINA S/SAL C/4/90 GR | UPFIELD | 11.283 | 51,0 % |
| FABULOSO LAVANDA 1 LT | COLGATE | 7.419 | 49,7 % |
| CHIPOTLE SM 100 GR | EMPACADORA SAN MARCOS | 11.307 | 48,8 % |
| FABULOSO MAR FRESCO 1 LT | COLGATE | 6.735 | 45,6 % |

### De prueba — baja recompra

| Producto | Marca | Compradores | % que lo vuelve básico |
|---|---|---:|---:|
| MEJORALITO C/30 TABLETAS - 80 MG | HALEON | 848 | 0,9 % |
| RAIDOLITOS LAVANDA / ORIGINAL C/50/12 GR | SC JOHNSON | 1.178 | 1,7 % |
| MEJORAL C/12 TABLETAS - 500 MG | HALEON | 371 | 2,7 % |
| CHAMP ADULTO SECO 500 GR | EFFEM | 425 | 2,8 % |
| TESALON C/10 CAPSULAS - 100 MG | HALEON | 295 | 3,1 % |
| KINDER SORPRESA JOYAS T12 | FERRERO | 390 | 3,3 % |

Un recomendador debería tratarlos distinto: a los básicos **se les recuerda**, a los de prueba
**se les introduce**.

---

## 5. Ciclo de vida del catálogo

- 538 productos vendidos en el periodo
- **430 activos** (con venta en los últimos 2 meses)
- **108 sin una sola venta** en los últimos 2 meses → no recomendar
- 277 se vendieron los 12 meses

---

## 6. Rechazo por producto

309.216 piezas rechazadas, 14.445 clientes afectados,
815 productos. **El top-10 concentra el 30,3 %**
de las piezas rechazadas.

| Producto | Marca | Piezas rechazadas | % de lo pedido |
|---|---|---:|---:|
| ACT II EXTRA MANTEQUILLA | CONAGRA | 20.073 | 3,1 % |
| ACT II MANTEQUILLA | CONAGRA | 12.308 | 2,9 % |
| PEDIGREE PANC POUCH RES 100 GR | EFFEM | 12.109 | 2,8 % |
| PEDIGREE PANC POUCH POLLO 100 GR | EFFEM | 8.271 | 2,9 % |
| WHISKAS POUCH ATUN 85 GR | EFFEM | 7.511 | 2,9 % |
| ACT II NATURAL | CONAGRA | 7.104 | 2,9 % |

Es la única señal de surtido que tienen los datos. No sustituye el quiebre de stock —un producto
que nunca se pidió porque el preventista sabía que no había no deja rastro aquí— pero acota el
problema.

---

## 7. Qué se lleva el modelado

1. **Usar `datos/derivado/dim_sku_flags.parquet`** y recomendar solo sobre los 428 productos
   marcados `recomendable`.
2. **La línea base es popularidad de ruta**, no popularidad global ni «lo que ya compró».
   Cubre 58,0 % con 50 productos.
3. **El margen está dentro de la ruta.** El CEDIS no aporta; la geografía fina sí. La pregunta es
   si se puede distinguir entre vecinos.
4. **La afinidad de línea de sabor es una señal fuerte y explicable**, y probablemente la victoria
   más rápida.
5. **Separar «recordar» de «introducir»**: los básicos y los de prueba se comportan distinto.
