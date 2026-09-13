import sys
from pathlib import Path
import numpy as np
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from poc import ranker

COLS = ["f1", "f2"]


def _ds(n_cli=40, semilla=0):
    rng = np.random.default_rng(semilla)
    filas = []
    for c in range(n_cli):
        for s in range(6):
            f1 = rng.random()
            filas.append({"cliente_id": f"c{c}", "sku": f"s{s}",
                          "f1": f1, "f2": rng.random(),
                          "y": int(f1 > 0.8)})   # f1 alto => positivo
    return pd.DataFrame(filas)


def test_entrena_y_devuelve_un_booster():
    m = ranker.entrenar(_ds(), _ds(semilla=1), COLS)
    assert m.num_trees() > 0


def test_puntuar_devuelve_un_valor_por_fila():
    ds = _ds()
    m = ranker.entrenar(ds, _ds(semilla=1), COLS)
    assert len(ranker.puntuar(m, ds, COLS)) == len(ds)


def test_aprende_que_f1_es_la_variable_que_importa():
    m = ranker.entrenar(_ds(), _ds(semilla=1), COLS)
    imp = ranker.importancias(m, COLS).set_index("variable")
    assert imp.loc["f1", "ganancia"] > imp.loc["f2", "ganancia"]


def test_es_reproducible_con_la_misma_semilla():
    ds, val = _ds(), _ds(semilla=1)
    a = ranker.puntuar(ranker.entrenar(ds, val, COLS, semilla=7), ds, COLS)
    b = ranker.puntuar(ranker.entrenar(ds, val, COLS, semilla=7), ds, COLS)
    assert np.allclose(a, b)


def test_ordenar_agrupa_las_filas_de_cada_cliente():
    ds = _ds(n_cli=5).sample(frac=1, random_state=3)   # desordenado a propósito
    o = ranker.ordenar(ds)
    # tras ordenar, cada cliente ocupa un bloque contiguo
    cambios = (o.cliente_id != o.cliente_id.shift()).sum()
    assert cambios == o.cliente_id.nunique()


def test_importancias_suman_cien_por_ciento():
    m = ranker.entrenar(_ds(), _ds(semilla=1), COLS)
    assert abs(ranker.importancias(m, COLS).pct.sum() - 100.0) < 0.5
