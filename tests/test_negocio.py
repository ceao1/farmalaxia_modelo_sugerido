import sys
from pathlib import Path
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from poc import negocio


def _ds():
    return pd.DataFrame({
        "cliente_id": ["A", "A", "B", "B"],
        "sku":        ["s1", "s2", "s1", "s2"],
        "y":          [1, 0, 1, 1],
        "score":      [9.0, 8.0, 9.0, 8.0],
        "origen":     ["dormido", "nunca", "dormido", "nunca"],
    })


def test_aciertos_por_cliente_promedia_bien():
    # A acierta 1, B acierta 2 -> 1,5
    assert negocio.aciertos_por_cliente(_ds(), "score", 2) == 1.5


def test_sku_extra_por_compra_divide_por_las_compras_del_mes():
    assert negocio.sku_extra_por_compra(_ds(), "score", 2, compras_mes=3.0) == 0.5


def test_importe_usa_el_precio_de_cada_sku():
    precio = pd.Series({"s1": 10.0, "s2": 20.0})
    # A acierta s1 (10). B acierta s1 y s2 (30). Media = 20.
    assert negocio.importe_de_aciertos(_ds(), "score", 2, precio) == 20.0


def test_importe_ignora_los_sku_sin_precio_conocido():
    precio = pd.Series({"s1": 10.0})          # s2 sin precio
    # A: 10 | B: 10 + 0 -> media 10
    assert negocio.importe_de_aciertos(_ds(), "score", 2, precio) == 10.0


def test_escenarios_escala_lineal_con_la_tasa():
    t = negocio.tabla_escenarios(importe_mes=100.0, n_clientes=10, tasas=(0.10, 0.20))
    assert len(t) == 2
    assert t.anual.iloc[1] == t.anual.iloc[0] * 2


def test_escenarios_anualiza_multiplicando_por_doce():
    t = negocio.tabla_escenarios(importe_mes=100.0, n_clientes=10, tasas=(1.0,))
    assert t.anual.iloc[0] == 100.0 * 10 * 12


def test_resumen_separa_reactivacion_de_descubrimiento():
    precio = pd.Series({"s1": 10.0, "s2": 20.0})
    r = negocio.resumen(_ds(), "score", n=2, precio=precio, compras_mes=3.0)
    assert r["aciertos_dormido"] == 2 and r["aciertos_nunca"] == 1
    assert r["pct_descubrimiento"] == round(1 / 3 * 100, 1)
