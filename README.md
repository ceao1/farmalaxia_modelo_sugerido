# Proyecto Farmalaxia — análisis de datos y diseño del recomendador

Análisis exploratorio de doce meses de preventa (`dbventas`) y diseño de una prueba de
concepto para mejorar el recomendador de SKUs que la empresa opera hoy.

---

## Por dónde empezar

| Si usted es… | Lea |
|---|---|
| **Quiere el informe final completo** | [`sitio/index.html`](sitio/index.html) — sitio estático con vista de negocio y vista técnica ([cómo desplegarlo](sitio/DESPLIEGUE.md)) |
| **Del equipo comercial** | [`informes/dashboard.html`](informes/dashboard.html) — ábralo en el navegador. Cada bloque cierra con un recuadro «En palabras simples» sin tecnicismos. |
| **Analista o científico de datos** | [`informes/02-analisis-clientes.md`](informes/02-analisis-clientes.md) y [`informes/03-analisis-productos.md`](informes/03-analisis-productos.md) |
| **Quien va a implementar** | [`docs/diseno/2026-09-13-recomendador-sku.md`](docs/diseno/2026-09-13-recomendador-sku.md) |
| **Quien evalúa el resultado del POC** | [`informes/04-resultados-poc.md`](informes/04-resultados-poc.md) |
| **Quien necesita levantar la base** | [`informes/01-exploracion-base-de-datos.md`](informes/01-exploracion-base-de-datos.md) |

---

## Los hallazgos, en cinco líneas

1. **El ritmo de compra lo fija la ruta, no el cliente.** Mediana de 7 días entre compras;
   48,6 % de los intervalos son exactamente semanales. El *cuándo* ya está resuelto.
2. **345 de los 883 SKU no son mercancía**, son registros de promoción con importe 0.
   El catálogo real es de 538 productos, de los cuales 428 son recomendables.
3. **La premisa del modelo actual es correcta:** la ruta aporta entre 15 y 20 puntos sobre la
   lista global, y el efecto no es surtido de almacén — el CEDIS no explica nada.
4. **No hay loop de retroalimentación.** La concentración es plana y la variedad crece. El tope
   del modelo actual es de resolución, no de convergencia.
5. **79,8 % de los productos nuevos que adopta un cliente son de una marca que ya compra**, y
   el 73 % de esa adopción ocurre después de la primera visita del mes.

---

## Estructura

```
informes/     Los entregables. Empiece aquí.
docs/diseno/  Diseño del POC del recomendador.
src/          Código, numerado en orden de ejecución.
datos/        crudo/ (el .bak) y derivado/ (parquet). No versionados: pesan ~1,6 GB.
resultados/   Métricas en JSON. Cada cifra de los informes sale de aquí.
```

---

## Reproducir el análisis

### 1. Levantar la base

El archivo es un backup nativo de **SQL Server 2025** — no lo restaura un motor 2022.

```bash
docker run -d --name farmalaxia-sql --platform linux/amd64 \
  -e "ACCEPT_EULA=Y" -e "MSSQL_SA_PASSWORD=$MSSQL_SA_PASSWORD" -e "MSSQL_PID=Developer" \
  -p 11433:1433 --memory 6g -v "$PWD/datos/crudo":/backup:ro \
  mcr.microsoft.com/mssql/server:2025-latest

docker exec farmalaxia-sql /opt/mssql-tools18/bin/sqlcmd \
  -S localhost -U sa -P "$MSSQL_SA_PASSWORD" -C -Q "
RESTORE DATABASE [dbventas] FROM DISK='/backup/dbventas.bak'
WITH MOVE 'dbventas'     TO '/var/opt/mssql/data/dbventas.mdf',
     MOVE 'dbventas_log' TO '/var/opt/mssql/data/dbventas_log.ldf',
     FILE=1, RECOVERY, STATS=25;"
```

Detalles y conexión desde DBeaver: [`informes/01-exploracion-base-de-datos.md`](informes/01-exploracion-base-de-datos.md).

### 2. Preparar el entorno

```bash
python3 -m venv .venv
./.venv/bin/pip install pandas pyarrow matplotlib
```

### 3. Correr la tubería

```bash
./src/00_consultar_bd.sh -Q "SELECT COUNT(*) FROM tblVentas"   # verifica la conexión
./.venv/bin/python src/01_construir_parquet.py     # TSV exportado -> parquet
./.venv/bin/python src/02_eda_clientes.py          # comportamiento de clientes
./.venv/bin/python src/03_eda_productos.py         # catálogo, zona, afinidad
./.venv/bin/python src/04_diag_techo.py            # techo del modelo actual, loop, adopción
./.venv/bin/python src/05_diag_candidatos.py       # cobertura por fuente de candidatos
./.venv/bin/python src/06_diag_n_sugerencias.py    # desempeño de B1 según N
./.venv/bin/python src/07_gen_dashboard.py         # regenera informes/dashboard.html
./.venv/bin/python src/10_ejecutar_poc.py          # entrena y evalúa el POC (~8 min)
./.venv/bin/python src/11_informe_poc.py           # informes/04-resultados-poc.md
./.venv/bin/python src/12_p4_segmentado.py         # P4, enrutamiento por segmento
./.venv/bin/python src/13_sitio.py                 # sitio/index.html (informe final)
```

Los pasos 02 a 07 corren en minutos y no necesitan la base: leen de `datos/derivado/`.
El paso 01 requiere el export `ventas.tsv`, que se genera con `bcp` desde el contenedor
(ver `informes/01-exploracion-base-de-datos.md`).

---

## Advertencias sobre los datos

- **Septiembre 2025 y agosto 2026 están incompletos** (inicio del archivo y corte en jueves 27).
- **Noviembre 2025 no registró visitas sin venta**, así que aparenta 100 % de efectividad.
- **Junio 2026 no es temporada alta**: se abrieron 24 rutas de preventa.
- **`PromocionCodigo` no discrimina**: viene poblado en casi todas las líneas.
- Un solo ciclo anual: tendencia y estacionalidad están confundidas.

---

## Nota de seguridad

La contraseña del contenedor se pasa por la variable de entorno `MSSQL_SA_PASSWORD`
y no está en el repositorio. Es un entorno local desechable.
