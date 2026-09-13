import sys
from pathlib import Path
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from poc import features


def _hist():
    # en ruta 10: s1 lo compran A y B; s2 solo C (otra ruta)
    return pd.DataFrame({
        "cliente_id":    ["A", "B", "C"],
        "anio_mes":      ["2026-04", "2026-04", "2026-04"],
        "sku":           ["s1", "s1", "s2"],
        "ruta_preventa": ["10", "10", "20"],
    })


def test_popularidad_cuenta_clientes_distintos():
    ruta_cli = pd.Series({"A": "10", "B": "10", "C": "20"})
    pop = features.popularidad_ruta(_hist(), ruta_cli)
    assert pop[("10", "s1")] == 2
    assert pop[("20", "s2")] == 1


def test_popularidad_no_cuenta_dos_veces_al_mismo_cliente():
    h = pd.DataFrame({
        "cliente_id": ["A", "A"], "anio_mes": ["2026-03", "2026-04"],
        "sku": ["s1", "s1"], "ruta_preventa": ["10", "10"],
    })
    pop = features.popularidad_ruta(h, pd.Series({"A": "10"}))
    assert pop[("10", "s1")] == 1


def test_agregar_ruta_pone_cero_si_nadie_lo_compro_en_la_ruta():
    ds = pd.DataFrame({"cliente_id": ["A"], "anio_mes": ["2026-07"], "sku": ["s2"], "y": [0]})
    out = features.agregar_ruta(ds, _hist())
    assert out.pop_ruta.iloc[0] == 0          # s2 no se vende en la ruta 10
    assert out.pop_global.iloc[0] == 1        # pero sí existe globalmente


def test_rango_ruta_ordena_de_mas_a_menos_popular():
    h = pd.DataFrame({
        "cliente_id":    ["A", "B", "C", "A"],
        "anio_mes":      ["2026-04"] * 4,
        "sku":           ["s1", "s1", "s1", "s2"],
        "ruta_preventa": ["10"] * 4,
    })
    ds = pd.DataFrame({"cliente_id": ["Z", "Z"], "anio_mes": ["2026-07"] * 2,
                       "sku": ["s1", "s2"], "y": [0, 0]})
    # Z es de la ruta 10 pero no está en la historia: se le asigna por ruta_cli externa
    out = features.agregar_ruta(ds, h, ruta_forzada={"Z": "10"})
    r = dict(zip(out.sku, out.rango_ruta))
    assert r["s1"] < r["s2"]                  # rango 1 es el más popular


def _dim():
    return pd.DataFrame({"sku": ["s1", "s2", "s3"],
                         "marca": ["ACME", "ACME", "OTRA"]})


def test_marca_conocida_es_uno_si_el_cliente_ya_compro_esa_marca():
    hist = pd.DataFrame({"cliente_id": ["A"], "anio_mes": ["2026-04"],
                         "sku": ["s1"], "ruta_preventa": ["10"],
                         "importe_preventa": [100.0], "piezas_preventa": [5],
                         "fecha": pd.to_datetime(["2026-04-01"])})
    ds = pd.DataFrame({"cliente_id": ["A", "A"], "anio_mes": ["2026-07"] * 2,
                       "sku": ["s2", "s3"], "y": [0, 0]})
    out = features.agregar_marca(ds, hist, _dim())
    m = dict(zip(out.sku, out.marca_conocida))
    assert m["s2"] == 1   # misma marca que s1
    assert m["s3"] == 0


def test_afinidad_cuenta_co_ocurrencias_en_la_misma_canasta():
    hist = pd.DataFrame({
        "cliente_id": ["A"] * 2, "anio_mes": ["2026-04"] * 2,
        "sku": ["s1", "s2"], "ruta_preventa": ["10"] * 2,
        "fecha": pd.to_datetime(["2026-04-01"] * 2),
        "importe_preventa": [10.0, 10.0], "piezas_preventa": [1, 1],
    })
    afin = features.matriz_afinidad(hist, minimo=1)
    assert afin[("s1", "s2")] == 1


def test_afinidad_respeta_el_piso_de_soporte():
    hist = pd.DataFrame({
        "cliente_id": ["A"] * 2, "anio_mes": ["2026-04"] * 2,
        "sku": ["s1", "s2"], "ruta_preventa": ["10"] * 2,
        "fecha": pd.to_datetime(["2026-04-01"] * 2),
        "importe_preventa": [10.0, 10.0], "piezas_preventa": [1, 1],
    })
    assert len(features.matriz_afinidad(hist, minimo=5)) == 0


def test_producto_calcula_precio_unitario():
    hist = pd.DataFrame({
        "cliente_id": ["A"], "anio_mes": ["2026-04"], "sku": ["s1"],
        "ruta_preventa": ["10"], "fecha": pd.to_datetime(["2026-04-01"]),
        "importe_preventa": [100.0], "piezas_preventa": [5],
    })
    ds = pd.DataFrame({"cliente_id": ["B"], "anio_mes": ["2026-07"], "sku": ["s1"], "y": [0]})
    out = features.agregar_producto(ds, hist)
    assert out.precio.iloc[0] == 20.0        # 100 / 5


def test_producto_cuenta_meses_disponible():
    hist = pd.DataFrame({
        "cliente_id": ["A", "A"], "anio_mes": ["2026-03", "2026-04"], "sku": ["s1", "s1"],
        "ruta_preventa": ["10", "10"], "fecha": pd.to_datetime(["2026-03-01", "2026-04-01"]),
        "importe_preventa": [10.0, 10.0], "piezas_preventa": [1, 1],
    })
    ds = pd.DataFrame({"cliente_id": ["B"], "anio_mes": ["2026-07"], "sku": ["s1"], "y": [0]})
    assert features.agregar_producto(ds, hist).meses_disponible.iloc[0] == 2


def test_producto_pone_cero_si_el_sku_no_tiene_historia():
    hist = pd.DataFrame({
        "cliente_id": ["A"], "anio_mes": ["2026-04"], "sku": ["s1"],
        "ruta_preventa": ["10"], "fecha": pd.to_datetime(["2026-04-01"]),
        "importe_preventa": [10.0], "piezas_preventa": [1],
    })
    ds = pd.DataFrame({"cliente_id": ["B"], "anio_mes": ["2026-07"], "sku": ["sX"], "y": [0]})
    out = features.agregar_producto(ds, hist)
    assert out.precio.iloc[0] == 0.0 and out.meses_disponible.iloc[0] == 0


def test_cliente_cuenta_surtido_y_compras():
    hist = pd.DataFrame({
        "cliente_id": ["A", "A"], "anio_mes": ["2026-03", "2026-04"], "sku": ["s1", "s2"],
        "ruta_preventa": ["10", "10"],
        "fecha": pd.to_datetime(["2026-03-01", "2026-04-01"]),
        "importe_preventa": [100.0, 50.0], "piezas_preventa": [1, 1],
    })
    ds = pd.DataFrame({"cliente_id": ["A"], "anio_mes": ["2026-07"], "sku": ["s3"], "y": [0]})
    out = features.agregar_cliente(ds, hist)
    assert out.n_skus_cliente.iloc[0] == 2
    assert out.n_compras_cliente.iloc[0] == 2
    assert out.ticket_medio.iloc[0] == 75.0


def test_columnas_modelo_existen_tras_agregar_todo():
    assert isinstance(features.COLUMNAS_MODELO, list)
    for c in ("pop_ruta", "marca_conocida", "afin_max", "precio", "pct_core", "es_dormido"):
        assert c in features.COLUMNAS_MODELO


def test_afinidad_correcta_aunque_las_filas_esten_desordenadas():
    hist = pd.DataFrame({
        "cliente_id": ["A", "A", "B", "B"], "anio_mes": ["2026-04"] * 4,
        "sku": ["s1", "s2", "s1", "s3"], "ruta_preventa": ["10"] * 4,
        "fecha": pd.to_datetime(["2026-04-01"] * 4),
        "importe_preventa": [10.0] * 4, "piezas_preventa": [1] * 4,
    })
    afin = features.matriz_afinidad(hist, minimo=1)
    ds = pd.DataFrame({
        "cliente_id": ["A", "B", "A", "B"],          # filas de cada cliente NO contiguas
        "anio_mes": ["2026-07"] * 4,
        "sku": ["s3", "s2", "s4", "s4"], "y": [0] * 4,
    })
    out = features.agregar_afinidad(ds, hist, afin)
    v = {(c, s): a for c, s, a in zip(out.cliente_id, out.sku, out.afin_suma)}
    # A compró s1 y s2; s3 co-ocurre con s1 en la canasta de B -> A debe ver afinidad con s3
    assert v[("A", "s3")] > 0
    # B compró s1 y s3; s2 co-ocurre con s1 -> B debe ver afinidad con s2
    assert v[("B", "s2")] > 0
    # s4 no aparece en ninguna canasta
    assert v[("A", "s4")] == 0 and v[("B", "s4")] == 0
