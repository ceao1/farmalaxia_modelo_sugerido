import sys
from pathlib import Path
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from poc import datos


def _df():
    return pd.DataFrame({
        "cliente_id": ["A", "A", "B", "B"],
        "anio_mes": ["2026-04", "2026-07", "2026-05", "2026-06"],
        "sku": ["s1", "s2", "s1", "s3"],
        "ruta_preventa": ["10", "10", "20", "20"],
    })


def test_historia_hasta_excluye_el_mes_objetivo():
    h = datos.historia_hasta(_df(), "2026-06")
    assert set(h.anio_mes) == {"2026-04", "2026-05"}
    assert "2026-06" not in set(h.anio_mes)
    assert "2026-07" not in set(h.anio_mes)


def test_particion_no_se_solapa():
    assert datos.MES_TEST not in datos.MESES_TRAIN
    assert datos.MES_VAL not in datos.MESES_TRAIN
    assert datos.MES_VAL < datos.MES_TEST
    assert max(datos.MESES_TRAIN) < datos.MES_VAL


def test_no_se_usa_agosto():
    assert datos.MES_TEST == "2026-07"
    assert "2026-08" not in datos.MESES_TRAIN + [datos.MES_VAL, datos.MES_TEST]


def test_ruta_dominante_toma_la_mas_frecuente():
    df = pd.DataFrame({"cliente_id": ["A"] * 3, "ruta_preventa": ["10", "10", "20"]})
    assert datos.ruta_dominante(df)["A"] == "10"


def test_recomendables_al_mes_excluye_lo_que_dejo_de_venderse():
    df = pd.DataFrame({
        "cliente_id": ["A", "A", "A"],
        "anio_mes": ["2026-01", "2026-05", "2026-06"],
        "sku": ["viejo", "vigente", "vigente"],
    })
    # para julio, los meses previos son mayo y junio: "viejo" no aparece
    activos = datos.recomendables_al_mes(df, "2026-07", {"viejo", "vigente"})
    assert activos == {"vigente"}


def test_recomendables_al_mes_no_mira_el_futuro():
    df = pd.DataFrame({
        "cliente_id": ["A", "A"], "anio_mes": ["2026-03", "2026-07"],
        "sku": ["antiguo", "futuro"],
    })
    activos = datos.recomendables_al_mes(df, "2026-04", {"antiguo", "futuro"})
    assert "futuro" not in activos


def test_junio_2026_no_esta_en_entrenamiento_ni_validacion():
    """Junio es el mes de la expansión de rutas: clientes sin historia."""
    assert datos.MES_EXCLUIDO == "2026-06"
    assert datos.MES_EXCLUIDO not in datos.MESES_TRAIN
    assert datos.MES_EXCLUIDO != datos.MES_VAL


def test_validacion_es_posterior_al_entrenamiento():
    assert max(datos.MESES_TRAIN) < datos.MES_VAL < datos.MES_TEST
