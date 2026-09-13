import sys
from pathlib import Path
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from poc import candidatos

RECOM = {"s1", "s2", "s3", "s4"}


def _df():
    # A: s1 habitual (junio, mes anterior) | s2 dormido (enero) | compra s2 y s3 en julio
    return pd.DataFrame({
        "cliente_id": ["A", "A", "A", "A"],
        "anio_mes":   ["2026-01", "2026-06", "2026-07", "2026-07"],
        "sku":        ["s2", "s1", "s2", "s3"],
    })


def test_excluye_lo_habitual_pero_no_lo_dormido():
    c = candidatos.construir(_df(), "2026-07", RECOM, ventana=2)
    assert "s1" not in set(c.sku)          # comprado en junio: habitual
    assert "s2" in set(c.sku)              # comprado en enero: dormido, sí es candidato


def test_marca_el_origen_correctamente():
    c = candidatos.construir(_df(), "2026-07", RECOM, ventana=2)
    o = dict(zip(c.sku, c.origen))
    assert o["s2"] == "dormido"            # lo compró alguna vez
    assert o["s3"] == "nunca"
    assert o["s4"] == "nunca"


def test_reactivacion_cuenta_como_acierto():
    c = candidatos.construir(_df(), "2026-07", RECOM, ventana=2)
    fila = c[c.sku == "s2"]
    assert fila.y.iloc[0] == 1             # lo volvió a comprar en julio


def test_descubrimiento_cuenta_como_acierto():
    c = candidatos.construir(_df(), "2026-07", RECOM, ventana=2)
    assert c[c.sku == "s3"].y.iloc[0] == 1


def test_la_ventana_cambia_que_es_habitual():
    # con ventana de 12 meses, s2 (enero) también cuenta como habitual y se excluye
    c = candidatos.construir(_df(), "2026-07", RECOM, ventana=12)
    assert "s2" not in set(c.sku)


def test_solo_propone_recomendables():
    cands = candidatos.candidatos_cliente({"fuera_de_catalogo"}, RECOM)
    assert set(cands) <= RECOM


def test_es_determinista():
    assert candidatos.candidatos_cliente({"s1"}, RECOM) == candidatos.candidatos_cliente({"s1"}, RECOM)


def test_ignora_clientes_sin_historia():
    df = pd.DataFrame({"cliente_id": ["C"], "anio_mes": ["2026-07"], "sku": ["s1"]})
    assert candidatos.construir(df, "2026-07", RECOM).empty
