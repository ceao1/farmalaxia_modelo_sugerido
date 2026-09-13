# Exploración de `dbventas.bak`

## Cómo se levantó

El archivo es un **backup nativo de SQL Server (formato MTF)**, no un dump SQL:
no se puede leer con un editor ni importar a Postgres/MySQL directamente.
Requiere un motor SQL Server para restaurarlo.

Dato crítico: el backup fue generado por **SQL Server 2025** (`SoftwareVersionMajor=17`,
`CompatibilityLevel=170`). Un motor 2022 lo **rechaza** — los backups no son
compatibles hacia atrás. Hay que usar la imagen `2025-latest`.

```bash
docker run -d --name farmalaxia-sql --platform linux/amd64 \
  -e "ACCEPT_EULA=Y" -e "MSSQL_SA_PASSWORD=$MSSQL_SA_PASSWORD" -e "MSSQL_PID=Developer" \
  -p 11433:1433 --memory 6g \
  -v "$PWD":/backup:ro \
  mcr.microsoft.com/mssql/server:2025-latest

docker exec farmalaxia-sql /opt/mssql-tools18/bin/sqlcmd -S localhost -U sa -P "$MSSQL_SA_PASSWORD" -C -Q "
RESTORE DATABASE [dbventas] FROM DISK='/backup/dbventas.bak'
WITH MOVE 'dbventas'     TO '/var/opt/mssql/data/dbventas.mdf',
     MOVE 'dbventas_log' TO '/var/opt/mssql/data/dbventas_log.ldf',
     FILE=1, RECOVERY, STATS=25;"
```

En Apple Silicon corre bajo emulación Rosetta (amd64). Restauración: ~1 s, 141.409 páginas.
Puerto expuesto en el host: **11433**.

## Metadatos del backup

| Campo | Valor |
|---|---|
| Base de datos | `dbventas` |
| Tipo | Full Database Backup (1 solo backup set, `FILE=1`) |
| Servidor origen | `NS5028916` (Windows), usuario `admin` |
| Fecha del backup | 2026-09-03 14:02:37 |
| Tamaño | 1.106 MB |
| Recovery model | FULL |
| Collation | `Modern_Spanish_CI_AS` |
| Integridad | `IsDamaged = 0` |

## Estructura

La base contiene **una sola tabla**, sin vistas, procedimientos ni claves foráneas.

### `dbo.tblVentas` — 5.328.903 filas, 1.099 MB

Tabla **plana y denormalizada**: cada fila es un renglón de venta (cliente × SKU × día).
Único índice: PK clustered sobre `Id`. No hay índices sobre `fecha`, `ClienteCodigo`
ni `sku`, así que cualquier consulta analítica hace scan completo.

| # | Columna | Tipo | Notas |
|---|---|---|---|
| 1 | `Id` | bigint NOT NULL | PK clustered |
| 2 | `fecha` | date | sin nulos |
| 3 | `cedis` | varchar(100) | 2 valores |
| 4 | `rutaReparto` | int | 52 rutas |
| 5 | `rutaPreventa` | int | 102 rutas |
| 6 | `ClienteCodigo` | varchar(155) | 36.120 clientes |
| 7 | `cliente` | varchar(250) | nombre |
| 8 | `diaVisita` | varchar(250) | |
| 9 | `marca` | varchar(155) | 30 marcas |
| 10 | `sku` | varchar(50) | 883 SKUs |
| 11 | `descripcion` | varchar(250) | |
| 12 | `precio` | decimal(18,2) | |
| 13 | `PiezasPreventa` | int | |
| 14 | `importePreventa` | decimal(18,2) | |
| 15 | `PiezasRechazo` | int | |
| 16 | `importeRechazo` | decimal(18,2) | |
| 17 | `PiezasBackorder` | int | |
| 18 | `importeBackorder` | decimal(18,2) | |
| 19 | `ano` | int | redundante con `fecha` |
| 20 | `mes` | varchar(50) | nombre del mes en español |
| 21 | `PromocionCodigo` | varchar(50) | 363 promociones |
| 22 | `usuario` | varchar(155) | 210 usuarios |
| 23 | `idalmacen` | int | 8 almacenes |

## Contenido

- **Periodo:** 2025-09-01 → 2026-08-27 (12 meses exactos, sin huecos)
- **Importe preventa total:** 371.785.294
- **Importe rechazo:** 7.710.611 (2,1 % de la preventa)
- **Importe backorder:** 344.906 (0,09 %)

### Volumen mensual

| Mes | Filas | Importe preventa | Clientes |
|---|---:|---:|---:|
| 2025-09 | 431.596 | 29.540.038 | 27.102 |
| 2025-10 | 467.924 | 30.991.082 | 26.579 |
| 2025-11 | 387.027 | 29.085.020 | 23.897 |
| 2025-12 | 414.439 | 28.706.947 | 27.411 |
| 2026-01 | 451.633 | 31.360.549 | 26.844 |
| 2026-02 | 399.668 | 27.049.771 | 27.290 |
| 2026-03 | 434.831 | 29.431.399 | 26.980 |
| 2026-04 | 421.366 | 28.666.002 | 27.076 |
| 2026-05 | 437.632 | 30.242.007 | 26.815 |
| 2026-06 | 480.663 | 35.051.281 | 31.481 |
| 2026-07 | 546.504 | 39.318.447 | 28.513 |
| 2026-08 | 455.620 | 32.342.751 | 28.735 |

Serie muy estable (~30 M/mes) con pico en junio–julio 2026.

### CEDIS

| CEDIS | Filas | Importe preventa |
|---|---:|---:|
| ALMACEN ATIZAPAN | 2.806.218 | 191.775.964 |
| ALMACEN VALLEJO | 2.522.685 | 180.009.330 |

### Top marcas por importe

EFFEM (61,5 M, 52 SKUs) · CONAGRA (60,8 M, 58) · UNILEVER (56,5 M, 92) ·
COLGATE (40,0 M, 63) · QUALA (28,4 M, 34) · FERRERO (22,3 M, 37) ·
EMPACADORA SAN MARCOS (14,8 M, 11) · BEPENSA (12,2 M, 15) ·
CAMPARI (10,4 M, 10) · UPFIELD (8,9 M, 7)

Las marcas son de abarrotes y consumo masivo, no farmacéuticas — probablemente
`Farmalaxia` es el nombre del distribuidor, no la categoría de producto.

## Calidad de datos — leer antes de analizar

1. **744.851 filas (14 %) son visitas sin venta.** Tienen `sku`, `descripcion` y
   `precio` en NULL y las tres parejas de piezas/importe en cero. Afectan a 34.080
   clientes. **No son datos faltantes: son un hecho de negocio** (el vendedor visitó
   y no vendió). Cualquier promedio por fila debe excluirlas explícitamente, y el
   conteo de "visitas" debe incluirlas.

2. **Repeticiones de `fecha+ClienteCodigo+sku+rutaPreventa`** (excluyendo visitas sin
   venta): 355.329 grupos, **401.514 filas excedentes**. Desglose:

   - **339.967 grupos (374.656 filas excedentes) tienen importes distintos** entre sí →
     son pedidos legítimos repetidos el mismo día. **No deduplicar.**
   - **15.362 grupos (26.858 filas, 0,5 % del total) tienen importe idéntico** → posible
     duplicación de carga. En el spot-check, los `Id` son **consecutivos**
     (24203755 / 24203756: mismo cliente, SKU, pieza, importe y usuario), lo que apunta
     a doble inserción en el proceso de carga, no a dos pedidos reales.

   El impacto sobre los totales es menor al 0,5 %, pero conviene confirmar ese subconjunto
   con quien entregó el backup.

3. **`PromocionCodigo` es NULL en 748.673 filas** — casi exactamente las visitas sin
   venta, así que es consistente.

4. **Anomalías menores, despreciables:** 11 filas donde
   `importePreventa <> precio × PiezasPreventa`, y 2 filas con piezas negativas
   (probables devoluciones).

5. **`ano` y `mes` son redundantes** con `fecha`. Ambos verificados contra
   `YEAR(fecha)` y `MONTH(fecha)`: **0 discrepancias en las 5,3 M de filas**.
   `mes` usa los 12 nombres en español capitalizados. Se pueden ignorar sin riesgo.

## Consultar

### Desde la terminal

```bash
./sql.sh -Q "SELECT TOP 10 * FROM tblVentas"
./sql.sh -i mi_consulta.sql
```

### Desde DBeaver

Nueva conexión → **SQL Server** (driver `Microsoft Driver`, no jTDS):

| Campo | Valor |
|---|---|
| Host | `localhost` |
| Puerto | `11433` |
| Base de datos | `dbventas` |
| Autenticación | SQL Server Authentication |
| Usuario | `sa` |
| Contraseña | `$MSSQL_SA_PASSWORD` |

En la pestaña **Driver properties** hay que poner **`trustServerCertificate` = `true`**.
SQL Server 2025 exige conexión cifrada y el contenedor usa un certificado autofirmado;
sin esa propiedad DBeaver falla con un error de handshake SSL.

Si es la primera vez, DBeaver pedirá descargar el driver — aceptar.

> Nota: la contraseña `sa` está en texto plano en este documento y en `sql.sh`. Es un
> entorno local desechable; no reutilizar esa contraseña en ningún otro lado.

### Apagar y volver a levantar

```bash
docker stop farmalaxia-sql    # la base queda persistida en el contenedor
docker start farmalaxia-sql   # vuelve a estar disponible en el puerto 11433
```
