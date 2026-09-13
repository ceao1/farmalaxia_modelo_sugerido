import sys
from pathlib import Path
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from poc import metricas


def _ds():
    # A: 2 positivos (s1, s2). Con score, s1 queda 1ro y s2 3ro.
    # B: 1 positivo (t3), que queda 3ro.
    return pd.DataFrame({
        "cliente_id": ["A", "A", "A", "B", "B", "B"],
        "sku":        ["s1", "s3", "s2", "t1", "t2", "t3"],
        "y":          [1, 0, 1, 0, 0, 1],
        "score":      [9.0, 8.0, 7.0, 9.0, 8.0, 7.0],
        "origen":     ["nunca"] * 6,
    })


def test_hit_rate_en_1_solo_acierta_para_A():
    assert metricas.hit_rate_at_n(_ds(), "score", 1) == 50.0


def test_hit_rate_en_3_acierta_para_ambos():
    assert metricas.hit_rate_at_n(_ds(), "score", 3) == 100.0


def test_recall_en_3_es_total():
    assert metricas.recall_at_n(_ds(), "score", 3) == 100.0


def test_recall_en_1_es_la_mitad_para_A_y_cero_para_B():
    assert metricas.recall_at_n(_ds(), "score", 1) == 25.0


def test_precision_en_3_es_uno_de_tres_en_promedio():
    assert metricas.precision_at_n(_ds(), "score", 3) == 50.0


def test_curva_devuelve_una_fila_por_n():
    c = metricas.curva(_ds(), "score", ns=(1, 3))
    assert list(c.N) == [1, 3] and "hit_rate" in c.columns


def test_bootstrap_devuelve_intervalo_ordenado():
    lo, hi = metricas.bootstrap_ic(_ds(), "score", 3, reps=50)
    assert lo <= hi


# ---------- políticas de asignación ----------

def _ds_mixto():
    # A tiene 3 dormidos (d1..d3) con score alto y 3 nuncas (n1..n3) con score bajo.
    # El positivo está en n1, que la política libre nunca alcanzaría con n=2.
    return pd.DataFrame({
        "cliente_id": ["A"] * 6,
        "sku":    ["d1", "d2", "d3", "n1", "n2", "n3"],
        "origen": ["dormido"] * 3 + ["nunca"] * 3,
        "y":      [0, 0, 0, 1, 0, 0],
        "score":  [9.0, 8.0, 7.0, 6.0, 5.0, 4.0],
    })


def test_politica_libre_toma_los_mejores_sin_mirar_origen():
    sel = metricas.seleccionar(_ds_mixto(), "score", n=2, politica="libre")
    assert set(sel.sku) == {"d1", "d2"}


def test_politica_mixta_respeta_las_cuotas():
    sel = metricas.seleccionar(_ds_mixto(), "score", n=2, politica="mixta",
                               cuotas={"dormido": 1, "nunca": 1})
    assert set(sel.sku) == {"d1", "n1"}


def test_politica_mixta_encuentra_el_positivo_que_la_libre_pierde():
    libre = metricas.seleccionar(_ds_mixto(), "score", n=2, politica="libre")
    mixta = metricas.seleccionar(_ds_mixto(), "score", n=2, politica="mixta",
                                 cuotas={"dormido": 1, "nunca": 1})
    assert libre.y.sum() == 0 and mixta.y.sum() == 1


def test_politica_mixta_rellena_si_falta_una_clase():
    # cliente sin ningún dormido: los 2 espacios deben llenarse con nuncas
    ds = _ds_mixto()
    ds = ds[ds.origen == "nunca"]
    sel = metricas.seleccionar(ds, "score", n=2, politica="mixta",
                               cuotas={"dormido": 1, "nunca": 1})
    assert len(sel) == 2 and set(sel.sku) == {"n1", "n2"}


def test_politica_mixta_nunca_entrega_mas_de_n():
    sel = metricas.seleccionar(_ds_mixto(), "score", n=3, politica="mixta",
                               cuotas={"dormido": 2, "nunca": 1})
    assert len(sel) == 3


def test_desglose_por_origen_suma_los_aciertos():
    d = metricas.desglose_origen(_ds_mixto(), "score", n=6, politica="libre")
    assert d["nunca"] == 1 and d.get("dormido", 0) == 0
