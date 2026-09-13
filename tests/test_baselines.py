import sys
from pathlib import Path
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from poc import baselines


def _ds():
    return pd.DataFrame({
        "cliente_id": ["A"] * 3,
        "sku": ["s1", "s2", "s3"],
        "pop_global": [10, 50, 30],
        "pop_ruta": [8, 1, 5],
        "marca_conocida": [1, 1, 0],
        "afin_suma": [0.0, 7.0, 2.0],
    })


def test_b1_ordena_por_popularidad_de_ruta():
    p = baselines.b1_ruta(_ds())
    assert p.idxmax() == 0          # s1 tiene pop_ruta 8, la mayor


def test_b0_ordena_por_popularidad_global():
    p = baselines.b0_global(_ds())
    assert p.idxmax() == 1          # s2 tiene pop_global 50


def test_p1_hunde_las_marcas_desconocidas_bajo_todas_las_conocidas():
    p = baselines.p1_ruta_marca(_ds())
    assert p.iloc[2] < p.iloc[0] and p.iloc[2] < p.iloc[1]


def test_p1_respeta_el_orden_de_ruta_entre_marcas_conocidas():
    p = baselines.p1_ruta_marca(_ds())
    assert p.iloc[0] > p.iloc[1]    # s1 (pop_ruta 8) sobre s2 (pop_ruta 1)


def test_p1_no_se_rompe_si_ninguna_marca_es_conocida():
    ds = _ds().assign(marca_conocida=0)
    p = baselines.p1_ruta_marca(ds)
    assert p.idxmax() == 0          # queda el orden de B1


def test_p2_ordena_por_afinidad():
    p = baselines.p2_itemitem(_ds())
    assert p.idxmax() == 1          # s2 tiene afin_suma 7


def test_todas_expone_las_cuatro():
    assert set(baselines.TODAS) == {"B0", "B1", "P1", "P2"}


def test_todas_devuelven_una_puntuacion_por_fila():
    ds = _ds()
    for nombre, fn in baselines.TODAS.items():
        assert len(fn(ds)) == len(ds), nombre
