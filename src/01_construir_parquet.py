"""Convierte el export TSV de tblVentas a parquet, listo para el EDA y el modelado."""
import pandas as pd
from comun import DERIVADO

COLS = ["fecha","cliente_id","cedis","ruta_preventa","dia_visita","marca","sku",
        "precio","piezas_preventa","importe_preventa","piezas_rechazo",
        "promocion","id_almacen"]

df = pd.read_csv(
    DERIVADO / "ventas.tsv", sep="\t", names=COLS, header=None,
    dtype={"cliente_id": "str", "sku": "str", "marca": "str", "cedis": "str",
           "dia_visita": "str", "promocion": "str", "ruta_preventa": "str"},
    parse_dates=["fecha"], na_values=[""], keep_default_na=False,
)

# sku vacío = visita sin venta (no es dato faltante, es un hecho de negocio)
df["sku"] = df["sku"].replace("", pd.NA)
df["visita_sin_venta"] = df["sku"].isna()
# Los SKU con prefijo PP* son registros de mecánica promocional, no mercancía:
# importe 0.00 en el 100% de sus lineas. Se marcan para poder excluirlos del
# análisis de producto sin perder el rastro de la promoción.
df["es_pack"] = df["sku"].fillna("").str.upper().str.startswith("PP")
# Compra efectiva: la línea movió piezas de preventa
df["es_compra"] = df["piezas_preventa"] > 0

for c in ["cedis", "marca", "dia_visita", "ruta_preventa", "promocion"]:
    df[c] = df[c].astype("category")

df["anio_mes"] = df["fecha"].dt.to_period("M").astype(str)

df.to_parquet(DERIVADO / "ventas.parquet", index=False, compression="zstd")
print(f"ventas.parquet: {len(df):,} filas x {len(df.columns)} columnas")
print(f"  rango: {df.fecha.min().date()} -> {df.fecha.max().date()}")
print(f"  visitas sin venta: {df.visita_sin_venta.sum():,}")
print(f"  lineas de compra (piezas>0): {df.es_compra.sum():,}")
print(f"  lineas con sku pero 0 piezas: {(~df.visita_sin_venta & ~df.es_compra).sum():,}")
print(f"  lineas de promocion (PP*, importe 0): {df.es_pack.sum():,}")

dim = pd.read_csv(DERIVADO / "dim_sku.tsv", sep="\t", names=["sku","marca","descripcion"],
                  header=None, dtype=str, na_values=[""], keep_default_na=False)
print(f"\ndim_sku: {len(dim):,} filas / {dim.sku.nunique():,} SKUs distintos")
dupes = dim.sku.duplicated().sum()
if dupes:
    print(f"  OJO: {dupes:,} filas con sku repetido -> sku no mapea 1:1 a marca/descripcion")
dim.to_parquet(DERIVADO / "dim_sku.parquet", index=False)
