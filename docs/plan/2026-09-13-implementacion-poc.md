# Plan de implementación — POC del recomendador de SKUs

> **Para quien ejecute con agentes:** SUB-SKILL REQUERIDA: usar
> `superpowers:subagent-driven-development` (recomendado) o `superpowers:executing-plans`
> para implementar tarea por tarea. Los pasos usan casillas (`- [ ]`) para seguimiento.

**Objetivo:** medir si personalizar dentro de la ruta supera a la popularidad de ruta
(el modelo que la empresa opera hoy) al sugerir productos que el cliente nunca ha comprado.

**Arquitectura:** una tubería de cinco etapas —candidatos, variables, líneas base, ranker,
evaluación— sobre un dataset con grano *cliente-mes × candidato*. Cada etapa es un módulo
importable en `src/poc/` con pruebas propias; un único script orquestador los encadena y
escribe el informe. Todas las variables del mes *t* se calculan solo con meses anteriores.

**Tecnologías:** Python 3.14, pandas 3.0, LightGBM 4.7 (LambdaRank), pytest 9.1.

**Spec:** [`docs/diseno/2026-09-13-recomendador-sku.md`](../diseno/2026-09-13-recomendador-sku.md)

## Restricciones globales

Aplican a **todas** las tareas:

- **Candidatos = SKU `recomendable` que el cliente no pidió en los últimos 2 meses.** Incluye
  los **dormidos** (los conoce pero dejó de pedirlos) y los **nunca comprados**. Excluye solo
  lo habitual, que el cliente iba a pedir igual. Sin restricción por ruta.
- **Columna `origen` obligatoria** (`dormido` / `nunca`) y desglose de toda métrica por ella:
  un dormido tiene 8,6 veces más probabilidad de comprarse, así que un modelo puede lucir bien
  reactivando y sin descubrir nada.
- **Partición temporal fija:** entrenamiento ≤ `2026-05`, validación `2026-06`,
  prueba `2026-07`. Nunca agosto: está censurado a la derecha.
- **Sin fuga:** toda variable del mes *t* se calcula exclusivamente con meses `< t`.
- **N titular = 8**; se reporta la curva `N ∈ {3, 5, 8, 16, 24, 40}`.
- **Dos políticas de asignación**, cada modelo evaluado bajo ambas: `libre` (los 8 mejores) y
  `mixta` (5 `dormido` + 3 `nunca`, rellenando con la otra clase si falta alguna).
  **Comparar siempre dentro de la misma política.**
- **Vara a vencer:** B1 alcanza `hit-rate@8 ≈ 47 %` en política libre y **≈ 53 %** en mixta.
  El umbral es superar a B1 **en 5 puntos dentro de la misma política**.
- **Semilla = 7** en todo muestreo y entrenamiento, declarada en el código.
- **Submuestreo solo en entrenamiento:** ~8.000 clientes por mes. La evaluación usa todos.
- Los paquetes promocionales (`es_pack`) ya están excluidos de `ventas.parquet` vía la bandera;
  todo filtro parte de `es_compra & ~es_pack`.

## Estructura de archivos

| Archivo | Responsabilidad |
|---|---|
| `src/poc/datos.py` | cargar compras, definir la partición temporal, recortar historia |
| `src/poc/candidatos.py` | construir el conjunto cliente-mes × candidato con su etiqueta |
| `src/poc/features.py` | variables de ruta, marca, afinidad, producto y cliente |
| `src/poc/baselines.py` | B0, B1, P1, P2 |
| `src/poc/metricas.py` | hit-rate@N, recall, precisión, MAP, curva, bootstrap |
| `src/poc/negocio.py` | SKU extra por compra, pesos, tabla de escenarios |
| `src/poc/ranker.py` | entrenamiento LightGBM e importancia de variables |
| `src/10_ejecutar_poc.py` | orquestador → `informes/04-resultados-poc.md` |
| `tests/test_*.py` | una prueba por módulo, con datos sintéticos |

Las pruebas **no leen los parquet reales**: usan tablas pequeñas construidas a mano, para que
corran en segundos y fallen por la razón correcta.

---

### Tarea 1: Andamiaje y partición temporal

**Archivos:**
- Crear: `src/poc/__init__.py`, `src/poc/datos.py`
- Crear: `tests/test_datos.py`, `pytest.ini`
- Modificar: `requirements.txt` (crear si no existe)

**Interfaces:**
- Consume: `src/comun.py` (`DERIVADO`)
- Produce:
  - `MESES_TRAIN: list[str]`, `MES_VAL: str`, `MES_TEST: str`, `SEMILLA: int`
  - `cargar_compras() -> pd.DataFrame` — solo `es_compra & ~es_pack`, columna `anio_mes` como `str`
  - `recomendables_base() -> set[str]` — ni promoción ni exhibidor. **Sin** filtro de actividad.
  - `recomendables_al_mes(df: pd.DataFrame, mes: str, base: set[str]) -> set[str]` — los de
    `base` con venta en los dos meses anteriores a `mes`
  - `historia_hasta(df: pd.DataFrame, mes: str) -> pd.DataFrame` — filas con `anio_mes < mes`
  - `ruta_dominante(hist: pd.DataFrame) -> pd.Series` — índice `cliente_id`, valor ruta más frecuente

- [ ] **Paso 1: instalar dependencias y declararlas**

```bash
brew install libomp                       # LightGBM lo necesita en macOS
./.venv/bin/pip install lightgbm pytest
cat > requirements.txt <<'EOF'
pandas>=3.0
pyarrow>=25.0
matplotlib>=3.11
lightgbm>=4.7
pytest>=9.1
EOF
printf '[pytest]\ntestpaths = tests\n' > pytest.ini
```

- [ ] **Paso 2: escribir la prueba que falla**

Crear `tests/test_datos.py`:

```python
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
```

- [ ] **Paso 3: correr la prueba y ver que falla**

Ejecutar: `./.venv/bin/python -m pytest tests/test_datos.py -v`
Esperado: FALLA con `ModuleNotFoundError: No module named 'poc'`

- [ ] **Paso 4: implementar lo mínimo**

Crear `src/poc/__init__.py` vacío y `src/poc/datos.py`:

```python
"""Carga de datos y partición temporal del POC.

La partición es fija y está declarada aquí, no como parámetro: cambiarla a
mitad del experimento invalidaría la comparación contra la vara del spec.
"""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from comun import DERIVADO

SEMILLA = 7
MESES_TRAIN = ["2025-09", "2025-10", "2025-11", "2025-12",
               "2026-01", "2026-02", "2026-03", "2026-04", "2026-05"]
MES_VAL = "2026-06"
MES_TEST = "2026-07"   # agosto no: termina en jueves 27, está censurado


def cargar_compras() -> pd.DataFrame:
    """Líneas de compra reales: piezas > 0 y sin paquetes promocionales."""
    df = pd.read_parquet(DERIVADO / "ventas.parquet")
    df["anio_mes"] = df["anio_mes"].astype(str)
    if "es_pack" not in df.columns:
        df["es_pack"] = df["sku"].fillna("").str.upper().str.startswith("PP")
    return df[df.es_compra & ~df.es_pack].copy()


def recomendables_base() -> set[str]:
    """SKU que son mercancía real: ni promoción, ni exhibidor.

    NO aplica el filtro de actividad: la bandera `activo_ult2m` del parquet está
    calculada sobre el periodo COMPLETO, así que usarla para un mes de
    entrenamiento metería información del futuro. La actividad se resuelve por
    mes en `recomendables_al_mes`.
    """
    f = pd.read_parquet(DERIVADO / "dim_sku_flags.parquet")
    return set(f.loc[~f.es_pack & ~f.es_exhibidor, "sku"])


def recomendables_al_mes(df: pd.DataFrame, mes: str, base: set[str]) -> set[str]:
    """De `base`, los que tuvieron venta en los dos meses anteriores a `mes`.

    Recomendar un producto que dejó de venderse es un error operativo, pero
    «dejó de venderse» solo puede juzgarse con el pasado de cada mes.
    """
    previos = sorted(m for m in df.anio_mes.unique() if m < mes)[-2:]
    activos = set(df.loc[df.anio_mes.isin(previos), "sku"])
    return base & activos


def historia_hasta(df: pd.DataFrame, mes: str) -> pd.DataFrame:
    """Filas estrictamente anteriores a `mes`. Es la única puerta a datos pasados."""
    return df[df.anio_mes < mes]


def ruta_dominante(hist: pd.DataFrame) -> pd.Series:
    """Ruta de preventa más frecuente por cliente. Un cliente puede cambiar de ruta."""
    return (hist.groupby("cliente_id", observed=True).ruta_preventa
                .agg(lambda s: s.value_counts().index[0]))
```

- [ ] **Paso 5: correr la prueba y ver que pasa**

Ejecutar: `./.venv/bin/python -m pytest tests/test_datos.py -v`
Esperado: 6 passed

- [ ] **Paso 6: comprobar contra los datos reales**

Ejecutar:
```bash
./.venv/bin/python -c "
import sys; sys.path.insert(0,'src')
from poc import datos
d = datos.cargar_compras(); base = datos.recomendables_base()
jul = datos.recomendables_al_mes(d, datos.MES_TEST, base)
print('compras:', f'{len(d):,}', '| base:', len(base), '| activos en julio:', len(jul))
assert len(d) == 3_678_221 and len(base) == 534, 'los datos no son los esperados'
print('OK')"
```
Esperado: `compras: 3,678,221 | base: 534 | activos en julio: 419` y `OK`

Las 3,68 M salen de 4,58 M líneas de compra menos las 906 K de paquetes promocionales.
Los 419 activos son menos que los 428 de `dim_sku_flags.recomendable` justamente porque
el filtro por mes es más estricto y no mira el futuro.

- [ ] **Paso 7: confirmar**

```bash
git add src/poc/ tests/test_datos.py pytest.ini requirements.txt
git commit -m "poc: carga de datos y partición temporal con pruebas"
```

---

### Tarea 2: Conjunto de candidatos

**Archivos:**
- Crear: `src/poc/candidatos.py`, `tests/test_candidatos.py`

**Interfaces:**
- Consume: `datos.historia_hasta`, `datos.recomendables`
- Produce:
  - `candidatos_cliente(comprados: set[str], recom: set[str]) -> list[str]` — ordenado, determinista
  - `construir(df: pd.DataFrame, mes: str, recom: set[str], clientes: set[str] | None = None) -> pd.DataFrame`
    con columnas `cliente_id, anio_mes, sku, y` donde `y ∈ {0,1}`

- [ ] **Paso 1: escribir la prueba que falla**

Crear `tests/test_candidatos.py`:

```python
import sys
from pathlib import Path
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from poc import candidatos

RECOM = {"s1", "s2", "s3", "s4"}


def _df():
    # A compró s1 en abril y s2 en julio (s2 es nuevo para A en julio)
    # B compró s3 en abril y nada nuevo en julio
    return pd.DataFrame({
        "cliente_id": ["A", "A", "B", "B"],
        "anio_mes":   ["2026-04", "2026-07", "2026-04", "2026-07"],
        "sku":        ["s1", "s2", "s3", "s3"],
    })


def test_excluye_lo_ya_comprado():
    assert candidatos.candidatos_cliente({"s1"}, RECOM) == ["s2", "s3", "s4"]


def test_solo_propone_recomendables():
    assert "s9" not in candidatos.candidatos_cliente(set(), RECOM | {"s9"} - {"s9"})


def test_es_determinista():
    a = candidatos.candidatos_cliente({"s1"}, RECOM)
    b = candidatos.candidatos_cliente({"s1"}, RECOM)
    assert a == b


def test_etiqueta_marca_lo_comprado_nuevo():
    ds = candidatos.construir(_df(), "2026-07", RECOM)
    fila_a_s2 = ds[(ds.cliente_id == "A") & (ds.sku == "s2")]
    assert len(fila_a_s2) == 1 and fila_a_s2.y.iloc[0] == 1


def test_no_aparece_lo_que_el_cliente_ya_tenia():
    ds = candidatos.construir(_df(), "2026-07", RECOM)
    assert len(ds[(ds.cliente_id == "A") & (ds.sku == "s1")]) == 0
    assert len(ds[(ds.cliente_id == "B") & (ds.sku == "s3")]) == 0


def test_todo_lo_no_comprado_queda_en_cero():
    ds = candidatos.construir(_df(), "2026-07", RECOM)
    b = ds[ds.cliente_id == "B"]
    assert set(b.sku) == {"s1", "s2", "s4"} and b.y.sum() == 0
```

- [ ] **Paso 2: correr y ver que falla**

Ejecutar: `./.venv/bin/python -m pytest tests/test_candidatos.py -v`
Esperado: FALLA con `ModuleNotFoundError: No module named 'poc.candidatos'`

- [ ] **Paso 3: implementar**

Crear `src/poc/candidatos.py`:

```python
"""Conjunto candidato por cliente-mes.

Un candidato es un producto recomendable que el cliente NO ha comprado nunca
hasta el mes objetivo. Recomendar lo que ya compra siempre acierta y no aporta:
el cliente lo iba a pedir igual.
"""
import pandas as pd

from . import datos


def candidatos_cliente(comprados: set[str], recom: set[str]) -> list[str]:
    """Recomendables que este cliente nunca ha comprado, en orden estable."""
    return sorted(recom - comprados)


def construir(df: pd.DataFrame, mes: str, recom: set[str],
              clientes: set[str] | None = None) -> pd.DataFrame:
    """Filas cliente-mes × candidato con la etiqueta `y`.

    `y = 1` si el cliente compró ese SKU en `mes` siendo nuevo para él.
    `clientes` permite submuestrear; si es None se usan todos los del mes.
    """
    hist = datos.historia_hasta(df, mes)
    objetivo = df[df.anio_mes == mes]
    if clientes is not None:
        hist = hist[hist.cliente_id.isin(clientes)]
        objetivo = objetivo[objetivo.cliente_id.isin(clientes)]

    comprados = hist.groupby("cliente_id", observed=True).sku.apply(set)
    compras_mes = objetivo.groupby("cliente_id", observed=True).sku.apply(set)

    filas = []
    for cli in compras_mes.index:
        if cli not in comprados.index:
            continue                      # sin historia: no hay con qué personalizar
        cands = candidatos_cliente(comprados[cli], recom)
        nuevos = compras_mes[cli] & set(cands)
        for s in cands:
            filas.append((cli, mes, s, 1 if s in nuevos else 0))
    return pd.DataFrame(filas, columns=["cliente_id", "anio_mes", "sku", "y"])
```

- [ ] **Paso 4: correr y ver que pasa**

Ejecutar: `./.venv/bin/python -m pytest tests/test_candidatos.py -v`
Esperado: 6 passed

- [ ] **Paso 5: confirmar**

```bash
git add src/poc/candidatos.py tests/test_candidatos.py
git commit -m "poc: conjunto de candidatos con etiqueta de compra nueva"
```

---

### Tarea 3: Variables de ruta

**Archivos:**
- Crear: `src/poc/features.py`, `tests/test_features.py`

**Interfaces:**
- Consume: `datos.historia_hasta`, `datos.ruta_dominante`
- Produce:
  - `popularidad_ruta(hist: pd.DataFrame, ruta_cli: pd.Series) -> pd.Series` — índice `(ruta, sku)`, valor nº de clientes distintos
  - `popularidad_global(hist: pd.DataFrame) -> pd.Series` — índice `sku`
  - `agregar_ruta(ds: pd.DataFrame, hist: pd.DataFrame) -> pd.DataFrame` — añade `pop_ruta`, `rango_ruta`, `pop_global`

**Nota sobre leave-one-out.** En los diagnósticos del EDA había que descontar al propio cliente
de la popularidad de su ruta. **Aquí no hace falta:** los candidatos son SKU que el cliente
nunca compró, así que nunca contribuyó a esa cuenta. Lo que sí hay que garantizar —y lo prueba
el test— es que la popularidad se calcule **solo con meses anteriores** al objetivo.

- [ ] **Paso 1: escribir la prueba que falla**

Crear `tests/test_features.py`:

```python
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
```

- [ ] **Paso 2: correr y ver que falla**

Ejecutar: `./.venv/bin/python -m pytest tests/test_features.py -v`
Esperado: FALLA con `ModuleNotFoundError: No module named 'poc.features'`

- [ ] **Paso 3: implementar**

Crear `src/poc/features.py`:

```python
"""Variables del modelo. Todas se calculan con historia anterior al mes objetivo.

Quien modifique este módulo debe preservar esa regla: es la diferencia entre un
resultado creíble y uno que solo funciona en el papel.
"""
import numpy as np
import pandas as pd

from . import datos


def popularidad_ruta(hist: pd.DataFrame, ruta_cli: pd.Series) -> pd.Series:
    """Clientes distintos que compraron cada SKU en cada ruta."""
    pares = hist[["cliente_id", "sku"]].drop_duplicates().copy()
    pares["ruta"] = pares.cliente_id.map(ruta_cli)
    pares = pares.dropna(subset=["ruta"])
    return pares.groupby(["ruta", "sku"], observed=True).cliente_id.nunique()


def popularidad_global(hist: pd.DataFrame) -> pd.Series:
    """Clientes distintos que compraron cada SKU, sin distinguir ruta."""
    return hist.groupby("sku", observed=True).cliente_id.nunique()


def agregar_ruta(ds: pd.DataFrame, hist: pd.DataFrame,
                 ruta_forzada: dict[str, str] | None = None) -> pd.DataFrame:
    """Añade `pop_ruta`, `rango_ruta` y `pop_global` al conjunto de candidatos."""
    ruta_cli = datos.ruta_dominante(hist)
    if ruta_forzada:
        ruta_cli = pd.concat([ruta_cli, pd.Series(ruta_forzada)])
        ruta_cli = ruta_cli[~ruta_cli.index.duplicated(keep="last")]

    pop_r = popularidad_ruta(hist, ruta_cli)
    pop_g = popularidad_global(hist)

    # rango dentro de cada ruta: 1 = el más popular
    rango = (pop_r.groupby(level=0).rank(ascending=False, method="min")
                  .rename("rango_ruta"))

    out = ds.copy()
    out["ruta"] = out.cliente_id.map(ruta_cli)
    idx = pd.MultiIndex.from_arrays([out.ruta, out.sku])
    out["pop_ruta"] = pop_r.reindex(idx).to_numpy()
    out["rango_ruta"] = rango.reindex(idx).to_numpy()
    out["pop_global"] = out.sku.map(pop_g)

    out["pop_ruta"] = out.pop_ruta.fillna(0)
    out["pop_global"] = out.pop_global.fillna(0)
    # sin rango = nadie lo compró en la ruta: se le da el peor rango posible
    out["rango_ruta"] = out.rango_ruta.fillna(9999)
    return out.drop(columns="ruta")
```

- [ ] **Paso 4: correr y ver que pasa**

Ejecutar: `./.venv/bin/python -m pytest tests/test_features.py -v`
Esperado: 4 passed

- [ ] **Paso 5: confirmar**

```bash
git add src/poc/features.py tests/test_features.py
git commit -m "poc: variables de popularidad por ruta y global"
```

---

### Tarea 4: Variables de marca, afinidad, producto y cliente

**Archivos:**
- Modificar: `src/poc/features.py` (añadir al final)
- Modificar: `tests/test_features.py` (añadir al final)

**Interfaces:**
- Produce:
  - `agregar_marca(ds, hist, dim: pd.DataFrame) -> pd.DataFrame` — añade `marca_conocida`, `peso_marca`, `skus_de_la_marca`
  - `matriz_afinidad(hist: pd.DataFrame, minimo: int = 50) -> pd.Series` — índice `(sku_x, sku_y)`, valor co-ocurrencias
  - `agregar_afinidad(ds, hist, afin: pd.Series) -> pd.DataFrame` — añade `afin_max`, `afin_suma`
  - `agregar_cliente(ds, hist) -> pd.DataFrame` — añade `n_skus_cliente`, `n_compras_cliente`, `ticket_medio`
  - `agregar_producto(ds, hist) -> pd.DataFrame` — añade `precio`, `pct_core`, `meses_disponible`
  - `COLUMNAS_MODELO: list[str]` — el orden exacto de variables que consume el ranker

- [ ] **Paso 1: escribir la prueba que falla**

Añadir al final de `tests/test_features.py`:

```python
def _dim():
    return pd.DataFrame({"sku": ["s1", "s2", "s3"],
                         "marca": ["ACME", "ACME", "OTRA"]})


def test_marca_conocida_es_uno_si_el_cliente_ya_compro_esa_marca():
    hist = pd.DataFrame({"cliente_id": ["A"], "anio_mes": ["2026-04"],
                         "sku": ["s1"], "ruta_preventa": ["10"],
                         "importe_preventa": [100.0], "fecha": pd.to_datetime(["2026-04-01"])})
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
        "importe_preventa": [10.0, 10.0],
    })
    afin = features.matriz_afinidad(hist, minimo=1)
    assert afin[("s1", "s2")] == 1


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


def test_columnas_modelo_existen_tras_agregar_todo():
    assert isinstance(features.COLUMNAS_MODELO, list)
    for c in ("pop_ruta", "marca_conocida", "afin_max", "precio", "pct_core"):
        assert c in features.COLUMNAS_MODELO
```

- [ ] **Paso 2: correr y ver que falla**

Ejecutar: `./.venv/bin/python -m pytest tests/test_features.py -v`
Esperado: FALLA con `AttributeError: module 'poc.features' has no attribute 'agregar_marca'`

- [ ] **Paso 3: implementar**

Añadir al final de `src/poc/features.py`:

```python
def agregar_marca(ds: pd.DataFrame, hist: pd.DataFrame, dim: pd.DataFrame) -> pd.DataFrame:
    """Variables de marca. El EDA mostró que 79,8 % de lo nuevo es de marca conocida."""
    mrc = dict(zip(dim.sku, dim.marca))
    h = hist.copy()
    h["marca"] = h.sku.map(mrc)
    h = h.dropna(subset=["marca"])

    marcas_cli = h.groupby("cliente_id", observed=True).marca.apply(set)
    peso = (h.groupby(["cliente_id", "marca"], observed=True).size()
              / h.groupby("cliente_id", observed=True).size())
    skus_marca = h.groupby(["cliente_id", "marca"], observed=True).sku.nunique()

    out = ds.copy()
    out["marca"] = out.sku.map(mrc)
    out["marca_conocida"] = [
        1 if (c in marcas_cli.index and m in marcas_cli[c]) else 0
        for c, m in zip(out.cliente_id, out.marca)]
    idx = pd.MultiIndex.from_arrays([out.cliente_id, out.marca])
    out["peso_marca"] = peso.reindex(idx).to_numpy()
    out["skus_de_la_marca"] = skus_marca.reindex(idx).to_numpy()
    out["peso_marca"] = out.peso_marca.fillna(0.0)
    out["skus_de_la_marca"] = out.skus_de_la_marca.fillna(0)
    return out.drop(columns="marca")


def matriz_afinidad(hist: pd.DataFrame, minimo: int = 50) -> pd.Series:
    """Co-ocurrencias entre SKU dentro de una misma canasta (cliente + fecha).

    Se exige un piso de `minimo` canastas: sin él, los pares raros dominan y
    parecen señal cuando son ruido.
    """
    h = hist.copy()
    h["canasta"] = h.cliente_id.astype(str) + "|" + h.fecha.dt.strftime("%Y%m%d")
    b = h[["canasta", "sku"]].drop_duplicates()
    par = b.merge(b, on="canasta")
    par = par[par.sku_x != par.sku_y]
    co = par.groupby(["sku_x", "sku_y"], observed=True).canasta.nunique()
    return co[co >= minimo]


def agregar_afinidad(ds: pd.DataFrame, hist: pd.DataFrame, afin: pd.Series) -> pd.DataFrame:
    """Afinidad del candidato con lo que el cliente ya lleva: máximo y suma."""
    comprados = hist.groupby("cliente_id", observed=True).sku.apply(set)
    # afin indexada por (sku_ya_comprado, sku_candidato)
    por_x = {x: g.droplevel(0) for x, g in afin.groupby(level=0)}

    mx, sm = [], []
    for cli, cand in zip(ds.cliente_id, ds.sku):
        vals = []
        for s0 in comprados.get(cli, ()):
            serie = por_x.get(s0)
            if serie is not None and cand in serie.index:
                vals.append(float(serie[cand]))
        mx.append(max(vals) if vals else 0.0)
        sm.append(float(sum(vals)))
    out = ds.copy()
    out["afin_max"] = mx
    out["afin_suma"] = sm
    return out


def agregar_cliente(ds: pd.DataFrame, hist: pd.DataFrame) -> pd.DataFrame:
    """Variables del cliente: amplitud de surtido, frecuencia y ticket."""
    g = hist.groupby("cliente_id", observed=True)
    n_skus = g.sku.nunique()
    n_compras = g.fecha.nunique()
    ticket = g.importe_preventa.sum() / n_compras.replace(0, 1)

    out = ds.copy()
    out["n_skus_cliente"] = out.cliente_id.map(n_skus).fillna(0)
    out["n_compras_cliente"] = out.cliente_id.map(n_compras).fillna(0)
    out["ticket_medio"] = out.cliente_id.map(ticket).fillna(0.0)
    return out


def agregar_producto(ds: pd.DataFrame, hist: pd.DataFrame) -> pd.DataFrame:
    """Variables del producto: precio unitario, cuánto retiene y hace cuánto existe.

    `pct_core` = fracción de sus compradores que lo pidieron en 3 meses o más.
    Separa los básicos (se recuerdan) de los de prueba (se introducen).
    """
    g = hist.groupby("sku", observed=True)
    precio = g.importe_preventa.sum() / g.piezas_preventa.sum().replace(0, 1)
    meses = g.anio_mes.nunique()
    por_par = hist.groupby(["sku", "cliente_id"], observed=True).anio_mes.nunique()
    pct_core = por_par.groupby(level=0).apply(lambda x: (x >= 3).mean() * 100)

    out = ds.copy()
    out["precio"] = out.sku.map(precio).fillna(0.0)
    out["meses_disponible"] = out.sku.map(meses).fillna(0)
    out["pct_core"] = out.sku.map(pct_core).fillna(0.0)
    return out


COLUMNAS_MODELO = [
    "pop_ruta", "rango_ruta", "pop_global",
    "marca_conocida", "peso_marca", "skus_de_la_marca",
    "afin_max", "afin_suma",
    "n_skus_cliente", "n_compras_cliente", "ticket_medio",
    "precio", "pct_core", "meses_disponible",
]
```

- [ ] **Paso 4: correr y ver que pasa**

Ejecutar: `./.venv/bin/python -m pytest tests/test_features.py -v`
Esperado: 10 passed

- [ ] **Paso 5: confirmar**

```bash
git add src/poc/features.py tests/test_features.py
git commit -m "poc: variables de marca, afinidad y cliente"
```

---

### Tarea 5: Líneas base

**Archivos:**
- Crear: `src/poc/baselines.py`, `tests/test_baselines.py`

**Interfaces:**
- Consume: columnas `pop_global`, `pop_ruta`, `marca_conocida`, `afin_suma` del conjunto
- Produce: cada función recibe el `ds` con variables y devuelve `pd.Series` de puntuación
  - `b0_global(ds) -> pd.Series`
  - `b1_ruta(ds) -> pd.Series`
  - `p1_ruta_marca(ds) -> pd.Series`
  - `p2_itemitem(ds) -> pd.Series`
  - `TODAS: dict[str, callable]` — nombre → función

- [ ] **Paso 1: escribir la prueba que falla**

Crear `tests/test_baselines.py`:

```python
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
    # s3 es de marca desconocida: debe quedar por debajo de s1 y s2
    assert p.iloc[2] < p.iloc[0] and p.iloc[2] < p.iloc[1]


def test_p1_respeta_el_orden_de_ruta_entre_marcas_conocidas():
    p = baselines.p1_ruta_marca(_ds())
    assert p.iloc[0] > p.iloc[1]    # s1 (pop_ruta 8) sobre s2 (pop_ruta 1)


def test_p2_ordena_por_afinidad():
    p = baselines.p2_itemitem(_ds())
    assert p.idxmax() == 1          # s2 tiene afin_suma 7


def test_todas_expone_las_cuatro():
    assert set(baselines.TODAS) == {"B0", "B1", "P1", "P2"}
```

- [ ] **Paso 2: correr y ver que falla**

Ejecutar: `./.venv/bin/python -m pytest tests/test_baselines.py -v`
Esperado: FALLA con `ModuleNotFoundError: No module named 'poc.baselines'`

- [ ] **Paso 3: implementar**

Crear `src/poc/baselines.py`:

```python
"""Línea base y propuestas simples.

B1 es la vara: reproduce la lógica del modelo que la empresa opera hoy
—popularidad entre clientes de la misma ruta—. P1 y P2 son aportes nuestros.
"""
import pandas as pd


def b0_global(ds: pd.DataFrame) -> pd.Series:
    """Popularidad global. Solo sirve para dimensionar cuánto aporta la ruta."""
    return ds.pop_global.astype(float)


def b1_ruta(ds: pd.DataFrame) -> pd.Series:
    """Popularidad en la ruta del cliente: el modelo actual, reconstruido."""
    return ds.pop_ruta.astype(float)


def p1_ruta_marca(ds: pd.DataFrame) -> pd.Series:
    """B1 pero anteponiendo las marcas que el cliente ya compra.

    El desplazamiento garantiza que cualquier candidato de marca conocida quede
    sobre cualquiera de marca desconocida, conservando el orden de ruta dentro
    de cada grupo.
    """
    desplazamiento = float(ds.pop_ruta.max()) + 1.0
    return ds.pop_ruta.astype(float) + ds.marca_conocida.astype(float) * desplazamiento


def p2_itemitem(ds: pd.DataFrame) -> pd.Series:
    """Afinidad acumulada con lo que el cliente ya lleva."""
    return ds.afin_suma.astype(float)


TODAS = {"B0": b0_global, "B1": b1_ruta, "P1": p1_ruta_marca, "P2": p2_itemitem}
```

- [ ] **Paso 4: correr y ver que pasa**

Ejecutar: `./.venv/bin/python -m pytest tests/test_baselines.py -v`
Esperado: 6 passed

- [ ] **Paso 5: confirmar**

```bash
git add src/poc/baselines.py tests/test_baselines.py
git commit -m "poc: lineas base B0, B1 y propuestas P1, P2"
```

---

### Tarea 6: Métricas

**Archivos:**
- Crear: `src/poc/metricas.py`, `tests/test_metricas.py`

**Interfaces:**
- Produce:
  - `top_n(ds: pd.DataFrame, col: str, n: int) -> pd.DataFrame` — las n mejores por cliente
  - `seleccionar(ds, col, n=8, politica="libre", cuotas=None) -> pd.DataFrame` — aplica la
    política de asignación; `cuotas={"dormido":5,"nunca":3}` para la mixta
  - `hit_rate_at_n(ds, col, n) -> float` — % de clientes con ≥1 acierto
  - `recall_at_n(ds, col, n) -> float`
  - `precision_at_n(ds, col, n) -> float`
  - `map_at_n(ds, col, n) -> float`
  - `curva(ds, col, ns=(3,5,8,16,24,40)) -> pd.DataFrame` — columnas `N, hit_rate, recall, precision, map`
  - `bootstrap_ic(ds, col, n, reps=200, semilla=7) -> tuple[float, float]`

- [ ] **Paso 1: escribir la prueba que falla**

Crear `tests/test_metricas.py`:

```python
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
    })


def test_hit_rate_en_1_solo_acierta_para_A():
    assert metricas.hit_rate_at_n(_ds(), "score", 1) == 50.0


def test_hit_rate_en_3_acierta_para_ambos():
    assert metricas.hit_rate_at_n(_ds(), "score", 3) == 100.0


def test_recall_en_3_es_total():
    assert metricas.recall_at_n(_ds(), "score", 3) == 100.0


def test_recall_en_1_es_la_mitad_para_A_y_cero_para_B():
    # A recupera 1 de 2 -> 0,5 ; B recupera 0 de 1 -> 0,0 ; media 0,25
    assert metricas.recall_at_n(_ds(), "score", 1) == 25.0


def test_precision_en_3_es_uno_de_tres_en_promedio():
    # A: 2 de 3 ; B: 1 de 3 -> media 0,5
    assert metricas.precision_at_n(_ds(), "score", 3) == 50.0


def test_curva_devuelve_una_fila_por_n():
    c = metricas.curva(_ds(), "score", ns=(1, 3))
    assert list(c.N) == [1, 3] and "hit_rate" in c.columns


def test_bootstrap_devuelve_intervalo_ordenado():
    lo, hi = metricas.bootstrap_ic(_ds(), "score", 3, reps=50)
    assert lo <= hi
```

- [ ] **Paso 2: correr y ver que falla**

Ejecutar: `./.venv/bin/python -m pytest tests/test_metricas.py -v`
Esperado: FALLA con `ModuleNotFoundError: No module named 'poc.metricas'`

- [ ] **Paso 3: implementar**

Crear `src/poc/metricas.py`:

```python
"""Métricas de recomendación, medidas por cliente y promediadas.

`hit_rate_at_n` es la principal: fracción de clientes en que al menos una de las
N sugerencias se compró. Es la que entiende el equipo comercial.
"""
import numpy as np
import pandas as pd

NS_POR_DEFECTO = (3, 5, 8, 16, 24, 40)


def top_n(ds: pd.DataFrame, col: str, n: int) -> pd.DataFrame:
    """Las n filas de mayor puntuación por cliente. Desempate estable por `sku`."""
    return (ds.sort_values([col, "sku"], ascending=[False, True])
              .groupby("cliente_id", observed=True).head(n))


def hit_rate_at_n(ds: pd.DataFrame, col: str, n: int) -> float:
    t = top_n(ds, col, n)
    acierta = t.groupby("cliente_id", observed=True).y.max()
    return float(acierta.mean() * 100)


def recall_at_n(ds: pd.DataFrame, col: str, n: int) -> float:
    t = top_n(ds, col, n)
    encontrados = t.groupby("cliente_id", observed=True).y.sum()
    totales = ds.groupby("cliente_id", observed=True).y.sum()
    r = (encontrados / totales.replace(0, np.nan)).dropna()
    return float(r.mean() * 100)


def precision_at_n(ds: pd.DataFrame, col: str, n: int) -> float:
    t = top_n(ds, col, n)
    p = t.groupby("cliente_id", observed=True).y.sum() / n
    return float(p.mean() * 100)


def map_at_n(ds: pd.DataFrame, col: str, n: int) -> float:
    """Precisión media en cada posición acertada, promediada por cliente."""
    t = top_n(ds, col, n).copy()
    t["pos"] = t.groupby("cliente_id", observed=True).cumcount() + 1
    t["acum"] = t.groupby("cliente_id", observed=True).y.cumsum()
    t["prec_en_pos"] = t.acum / t.pos
    aportes = t[t.y == 1].groupby("cliente_id", observed=True).prec_en_pos.sum()
    totales = ds.groupby("cliente_id", observed=True).y.sum().clip(upper=n)
    ap = (aportes.reindex(totales.index).fillna(0) / totales.replace(0, np.nan)).dropna()
    return float(ap.mean() * 100)


def curva(ds: pd.DataFrame, col: str, ns=NS_POR_DEFECTO) -> pd.DataFrame:
    return pd.DataFrame([{
        "N": n,
        "hit_rate": round(hit_rate_at_n(ds, col, n), 2),
        "recall": round(recall_at_n(ds, col, n), 2),
        "precision": round(precision_at_n(ds, col, n), 2),
        "map": round(map_at_n(ds, col, n), 2),
    } for n in ns])


def bootstrap_ic(ds: pd.DataFrame, col: str, n: int,
                 reps: int = 200, semilla: int = 7) -> tuple[float, float]:
    """Intervalo del 95 % remuestreando CLIENTES, no filas.

    Remuestrear filas rompería los grupos y daría un intervalo falsamente estrecho.
    """
    rng = np.random.default_rng(semilla)
    t = top_n(ds, col, n)
    acierta = t.groupby("cliente_id", observed=True).y.max().to_numpy()
    vals = [acierta[rng.integers(0, len(acierta), len(acierta))].mean() * 100
            for _ in range(reps)]
    return float(np.percentile(vals, 2.5)), float(np.percentile(vals, 97.5))
```

- [ ] **Paso 4: correr y ver que pasa**

Ejecutar: `./.venv/bin/python -m pytest tests/test_metricas.py -v`
Esperado: 7 passed

- [ ] **Paso 5: confirmar**

```bash
git add src/poc/metricas.py tests/test_metricas.py
git commit -m "poc: metricas hit-rate, recall, precision, MAP y bootstrap"
```

---

### Tarea 7: Traducción a negocio

**Archivos:**
- Crear: `src/poc/negocio.py`, `tests/test_negocio.py`

**Interfaces:**
- Consume: `metricas.top_n`
- Produce:
  - `aciertos_por_cliente(ds, col, n) -> float`
  - `sku_extra_por_compra(ds, col, n, compras_mes: float) -> float`
  - `importe_de_aciertos(ds, col, n, precio: pd.Series) -> float` — importe medio por cliente
  - `tabla_escenarios(importe_mes: float, n_clientes: int, tasas=(0.10,0.20,0.30)) -> pd.DataFrame`

- [ ] **Paso 1: escribir la prueba que falla**

Crear `tests/test_negocio.py`:

```python
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


def test_escenarios_escala_lineal_con_la_tasa():
    t = negocio.tabla_escenarios(importe_mes=100.0, n_clientes=10, tasas=(0.10, 0.20))
    assert len(t) == 2
    assert t.anual.iloc[1] == t.anual.iloc[0] * 2


def test_escenarios_anualiza_multiplicando_por_doce():
    t = negocio.tabla_escenarios(importe_mes=100.0, n_clientes=10, tasas=(1.0,))
    assert t.anual.iloc[0] == 100.0 * 10 * 12
```

- [ ] **Paso 2: correr y ver que falla**

Ejecutar: `./.venv/bin/python -m pytest tests/test_negocio.py -v`
Esperado: FALLA con `ModuleNotFoundError: No module named 'poc.negocio'`

- [ ] **Paso 3: implementar**

Crear `src/poc/negocio.py`:

```python
"""Traducción de las métricas a lenguaje de negocio.

Advertencia que debe acompañar siempre a estos números: los datos dicen si el
modelo ACIERTA qué comprará el cliente, no si la sugerencia lo CAUSÓ. Por eso el
impacto se entrega como escenarios con la tasa de conversión a la vista, nunca
como una cifra única. Solo un piloto con grupo de control mide impacto real.
"""
import pandas as pd

from .metricas import top_n


def aciertos_por_cliente(ds: pd.DataFrame, col: str, n: int) -> float:
    """Cuántas de las n sugerencias se compraron, en promedio por cliente."""
    t = top_n(ds, col, n)
    return float(t.groupby("cliente_id", observed=True).y.sum().mean())


def sku_extra_por_compra(ds: pd.DataFrame, col: str, n: int, compras_mes: float) -> float:
    """Aciertos mensuales repartidos entre las compras del mes."""
    return round(aciertos_por_cliente(ds, col, n) / compras_mes, 3)


def importe_de_aciertos(ds: pd.DataFrame, col: str, n: int, precio: pd.Series) -> float:
    """Importe medio por cliente de los productos acertados."""
    t = top_n(ds, col, n).copy()
    t["imp"] = t.y * t.sku.map(precio).fillna(0.0)
    return float(t.groupby("cliente_id", observed=True).imp.sum().mean())


def tabla_escenarios(importe_mes: float, n_clientes: int,
                     tasas=(0.10, 0.20, 0.30)) -> pd.DataFrame:
    """Impacto anual bajo distintos supuestos de conversión incremental.

    `tasa` = fracción de los aciertos que NO habría ocurrido sin la sugerencia.
    Es un supuesto, no un dato: por eso va como columna y no escondido.
    """
    return pd.DataFrame([{
        "tasa_conversion": t,
        "mensual": round(importe_mes * n_clientes * t, 0),
        "anual": round(importe_mes * n_clientes * t * 12, 0),
    } for t in tasas])
```

- [ ] **Paso 4: correr y ver que pasa**

Ejecutar: `./.venv/bin/python -m pytest tests/test_negocio.py -v`
Esperado: 5 passed

- [ ] **Paso 5: confirmar**

```bash
git add src/poc/negocio.py tests/test_negocio.py
git commit -m "poc: traduccion a negocio con escenarios de conversion"
```

---

### Tarea 8: Ranker LightGBM

**Archivos:**
- Crear: `src/poc/ranker.py`, `tests/test_ranker.py`

**Interfaces:**
- Consume: `features.COLUMNAS_MODELO`
- Produce:
  - `entrenar(ds_train, ds_val, columnas, semilla=7) -> lgb.Booster`
  - `puntuar(modelo, ds, columnas) -> np.ndarray`
  - `importancias(modelo, columnas) -> pd.DataFrame` — columnas `variable, ganancia, pct`

**Nota:** LightGBM exige que las filas lleguen **agrupadas por cliente** y que el vector
`group` tenga el tamaño de cada grupo en ese mismo orden. Ordenar mal es el error más común
y no produce excepción, solo un modelo malo.

- [ ] **Paso 1: escribir la prueba que falla**

Crear `tests/test_ranker.py`:

```python
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
    p = ranker.puntuar(m, ds, COLS)
    assert len(p) == len(ds)


def test_aprende_que_f1_es_la_variable_que_importa():
    m = ranker.entrenar(_ds(), _ds(semilla=1), COLS)
    imp = ranker.importancias(m, COLS).set_index("variable")
    assert imp.loc["f1", "ganancia"] > imp.loc["f2", "ganancia"]


def test_es_reproducible_con_la_misma_semilla():
    ds, val = _ds(), _ds(semilla=1)
    a = ranker.puntuar(ranker.entrenar(ds, val, COLS, semilla=7), ds, COLS)
    b = ranker.puntuar(ranker.entrenar(ds, val, COLS, semilla=7), ds, COLS)
    assert np.allclose(a, b)
```

- [ ] **Paso 2: correr y ver que falla**

Ejecutar: `./.venv/bin/python -m pytest tests/test_ranker.py -v`
Esperado: FALLA con `ModuleNotFoundError: No module named 'poc.ranker'`

- [ ] **Paso 3: implementar**

Crear `src/poc/ranker.py`:

```python
"""Ranker LightGBM (LambdaRank) sobre grupos cliente-mes.

Se eligió por encima de la factorización matricial porque la importancia de
variables es parte del entregable: el cliente pidió saber qué pistas aportan.
"""
import lightgbm as lgb
import numpy as np
import pandas as pd

PARAMS = {
    "objective": "lambdarank",
    "metric": "ndcg",
    "ndcg_eval_at": [8],
    "learning_rate": 0.08,
    "num_leaves": 63,
    "min_data_in_leaf": 50,
    "feature_fraction": 0.9,
    "bagging_fraction": 0.8,
    "bagging_freq": 1,
    "verbose": -1,
}


def ordenar(ds: pd.DataFrame) -> pd.DataFrame:
    """LightGBM exige filas contiguas por grupo. Ordenar mal no falla, solo empeora.

    Pública a propósito: el orquestador debe aplicarla al conjunto de prueba antes
    de puntuar, o las puntuaciones quedan desalineadas con las filas.
    """
    return ds.sort_values(["cliente_id", "sku"]).reset_index(drop=True)


def _grupos(ds: pd.DataFrame) -> np.ndarray:
    return ds.groupby("cliente_id", observed=True, sort=False).size().to_numpy()


def entrenar(ds_train: pd.DataFrame, ds_val: pd.DataFrame,
             columnas: list[str], semilla: int = 7) -> lgb.Booster:
    tr, va = ordenar(ds_train), ordenar(ds_val)
    d_tr = lgb.Dataset(tr[columnas], label=tr.y, group=_grupos(tr))
    d_va = lgb.Dataset(va[columnas], label=va.y, group=_grupos(va), reference=d_tr)
    params = PARAMS | {"seed": semilla, "bagging_seed": semilla,
                       "feature_fraction_seed": semilla, "deterministic": True}
    return lgb.train(params, d_tr, num_boost_round=400, valid_sets=[d_va],
                     callbacks=[lgb.early_stopping(40, verbose=False)])


def puntuar(modelo: lgb.Booster, ds: pd.DataFrame, columnas: list[str]) -> np.ndarray:
    return modelo.predict(ds[columnas], num_iteration=modelo.best_iteration)


def importancias(modelo: lgb.Booster, columnas: list[str]) -> pd.DataFrame:
    g = modelo.feature_importance("gain")
    tot = g.sum() or 1.0
    return (pd.DataFrame({"variable": columnas, "ganancia": g.round(1),
                          "pct": (g / tot * 100).round(1)})
              .sort_values("ganancia", ascending=False).reset_index(drop=True))
```

- [ ] **Paso 4: correr y ver que pasa**

Ejecutar: `./.venv/bin/python -m pytest tests/test_ranker.py -v`
Esperado: 4 passed

- [ ] **Paso 5: confirmar**

```bash
git add src/poc/ranker.py tests/test_ranker.py
git commit -m "poc: ranker LightGBM con importancia de variables"
```

---

### Tarea 9: Orquestador e informe

**Archivos:**
- Crear: `src/10_ejecutar_poc.py`
- Crear (lo genera el script): `informes/04-resultados-poc.md`, `resultados/poc.json`
- Modificar: `README.md` (añadir el paso a la tubería)

**Interfaces:**
- Consume: todos los módulos de `src/poc/`
- Produce: `informes/04-resultados-poc.md` y `resultados/poc.json`

- [ ] **Paso 1: escribir el orquestador**

Crear `src/10_ejecutar_poc.py`:

```python
"""Ejecuta el POC completo y escribe el informe.

Uso:  ./.venv/bin/python src/10_ejecutar_poc.py
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from comun import DERIVADO, INFORMES, RESULTADOS
from poc import baselines, candidatos, datos, features, metricas, negocio, ranker

N_TITULAR = 8
UMBRAL_B1 = 47.0          # hit-rate@8 de B1 con candidatos dormidos incluidos
MARGEN_EXIGIDO = 5.0
CLIENTES_ENTRENAMIENTO = 8000

print("1/6  cargando datos")
df = datos.cargar_compras()
base_recom = datos.recomendables_base()
dim = pd.read_parquet(DERIVADO / "dim_sku_flags.parquet")[["sku", "marca"]]

# Las 24 rutas que abren en jun-2026 tienen <=3 meses de historia: su B1 es
# inestable, así que se reportan aparte en vez de contaminar el promedio.
RUTAS_ESTABLES = set(df.loc[df.anio_mes == datos.MESES_TRAIN[0], "ruta_preventa"].dropna())

rng = np.random.default_rng(datos.SEMILLA)


def preparar(mes: str, submuestrear: bool) -> pd.DataFrame:
    """Conjunto de un mes con todas las variables, sin fuga."""
    hist = datos.historia_hasta(df, mes)
    clientes = None
    if submuestrear:
        todos = sorted(set(df[df.anio_mes == mes].cliente_id))
        if len(todos) > CLIENTES_ENTRENAMIENTO:
            clientes = set(rng.choice(todos, CLIENTES_ENTRENAMIENTO, replace=False))
    recom = datos.recomendables_al_mes(df, mes, base_recom)
    ds = candidatos.construir(df, mes, recom, clientes)
    if ds.empty:
        return ds
    afin = features.matriz_afinidad(hist)
    ds = features.agregar_ruta(ds, hist)
    ds = features.agregar_marca(ds, hist, dim)
    ds = features.agregar_afinidad(ds, hist, afin)
    ds = features.agregar_cliente(ds, hist)
    ds = features.agregar_producto(ds, hist)
    return ds


print("2/6  construyendo entrenamiento (últimos 3 meses de train)")
train = pd.concat([preparar(m, True) for m in datos.MESES_TRAIN[-3:]], ignore_index=True)
print(f"     {len(train):,} filas, {train.cliente_id.nunique():,} clientes")

print("3/6  construyendo validación y prueba")
val = preparar(datos.MES_VAL, True)
test = preparar(datos.MES_TEST, False)
print(f"     prueba: {len(test):,} filas, {test.cliente_id.nunique():,} clientes")

print("4/6  puntuando líneas base")
for nombre, fn in baselines.TODAS.items():
    test[nombre] = fn(test)

print("5/6  entrenando el ranker")
modelo = ranker.entrenar(train, val, features.COLUMNAS_MODELO, datos.SEMILLA)
test = ranker.ordenar(test)
test["P3"] = ranker.puntuar(modelo, test, features.COLUMNAS_MODELO)
imp = ranker.importancias(modelo, features.COLUMNAS_MODELO)

print("6/6  evaluando")
MODELOS = ["B0", "B1", "P1", "P2", "P3"]
curvas = {m: metricas.curva(test, m) for m in MODELOS}
hr8 = {m: metricas.hit_rate_at_n(test, m, N_TITULAR) for m in MODELOS}
ic = {m: metricas.bootstrap_ic(test, m, N_TITULAR) for m in MODELOS}

precio = (df.groupby("sku", observed=True)
            .apply(lambda g: g.importe_preventa.sum() / max(g.piezas_preventa.sum(), 1),
                   include_groups=False))
compras_mes = df[df.anio_mes == datos.MES_TEST].groupby(
    "cliente_id", observed=True).fecha.nunique().mean()

mejor = max(MODELOS[1:], key=lambda m: hr8[m])
negocio_mejor = {
    "modelo": mejor,
    "aciertos_por_cliente": round(negocio.aciertos_por_cliente(test, mejor, N_TITULAR), 3),
    "sku_extra_por_compra": negocio.sku_extra_por_compra(test, mejor, N_TITULAR, compras_mes),
    "importe_por_cliente": round(negocio.importe_de_aciertos(test, mejor, N_TITULAR, precio), 1),
}
escenarios = negocio.tabla_escenarios(negocio_mejor["importe_por_cliente"],
                                      test.cliente_id.nunique())

# desglose por antigüedad de ruta
ruta_test = datos.ruta_dominante(datos.historia_hasta(df, datos.MES_TEST))
test["ruta_estable"] = test.cliente_id.map(ruta_test).isin(RUTAS_ESTABLES)
por_ruta = {}
for etiqueta, sub in (("estables", test[test.ruta_estable]),
                      ("nuevas_jun2026", test[~test.ruta_estable])):
    if sub.cliente_id.nunique() < 100:
        continue
    por_ruta[etiqueta] = {
        "clientes": int(sub.cliente_id.nunique()),
        **{m: round(metricas.hit_rate_at_n(sub, m, N_TITULAR), 2) for m in MODELOS},
    }

OUT = {
    "mes_prueba": datos.MES_TEST,
    "hit_rate_8_por_antiguedad_de_ruta": por_ruta,
    "clientes_evaluados": int(test.cliente_id.nunique()),
    "candidatos_por_cliente": int(round(len(test) / test.cliente_id.nunique())),
    "hit_rate_8": {m: round(hr8[m], 2) for m in MODELOS},
    "intervalo_95": {m: [round(a, 2), round(b, 2)] for m, (a, b) in ic.items()},
    "curvas": {m: curvas[m].to_dict("records") for m in MODELOS},
    "importancias": imp.to_dict("records"),
    "negocio": negocio_mejor,
    "escenarios": escenarios.to_dict("records"),
    "umbral": {"b1_referencia_eda": UMBRAL_B1, "margen_exigido": MARGEN_EXIGIDO,
               "b1_medido": round(hr8["B1"], 2),
               "objetivo": round(hr8["B1"] + MARGEN_EXIGIDO, 2),
               "logrado": bool(hr8[mejor] >= hr8["B1"] + MARGEN_EXIGIDO)},
}
json.dump(OUT, open(RESULTADOS / "poc.json", "w"), indent=2, ensure_ascii=False)

for m in MODELOS:
    print(f"  {m}: hit-rate@8 = {hr8[m]:.2f}%  IC95 [{ic[m][0]:.2f}, {ic[m][1]:.2f}]")
for etiqueta, v in por_ruta.items():
    print(f"  rutas {etiqueta}: {v['clientes']:,} clientes | "
          + " ".join(f"{m}={v[m]}%" for m in MODELOS))
print(f"\n  mejor propuesta: {mejor} | objetivo {OUT['umbral']['objetivo']}% | "
      f"{'LOGRADO' if OUT['umbral']['logrado'] else 'NO LOGRADO'}")
print(f"  resultados en {RESULTADOS / 'poc.json'}")
```

- [ ] **Paso 2: correr la suite completa antes de ejecutar**

Ejecutar: `./.venv/bin/python -m pytest -v`
Esperado: 44 passed (6+6+10+6+7+5+4 de las tareas 1 a 8)

- [ ] **Paso 3: ejecutar el POC**

Ejecutar: `./.venv/bin/python src/10_ejecutar_poc.py`
Esperado: termina sin excepción e imprime el hit-rate@8 de los cinco modelos.
`B1` debe caer cerca de **47 %** — si se aleja más de 3 puntos, hay una diferencia entre
este conjunto de candidatos y el del diagnóstico: revisar antes de seguir.

- [ ] **Paso 4: confirmar el código**

```bash
git add src/10_ejecutar_poc.py resultados/poc.json
git commit -m "poc: orquestador que entrena, evalua y guarda resultados"
```

- [ ] **Paso 5: escribir el informe**

Redactar `informes/04-resultados-poc.md` leyendo `resultados/poc.json`. Debe contener,
en este orden:

1. **Qué se probó y contra qué** — una frase; B1 es el modelo actual reconstruido.
2. **Tabla de hit-rate@8** de los cinco modelos con su intervalo del 95 %.
3. **Veredicto** — si la mejor propuesta superó a B1 por ≥5 puntos. Si no, decirlo
   con la misma claridad: significa que el camino es mejores datos, no mejor modelo.
4. **Curvas completas** de N = 3 a 40 para B1 y la mejor propuesta.
5. **Importancia de variables** — la tabla, y qué pista resultó decisiva.
6. **Traducción a negocio** — SKU extra por compra, importe por cliente, y la tabla de
   escenarios con la tasa de conversión visible.
7. **Desglose por antigüedad de ruta** — resultados de las rutas estables y de las 24
   abiertas en junio de 2026 por separado. Si difieren mucho, decirlo: el modelo necesita
   historia y en rutas nuevas rinde menos.
8. **Recomendación de ingeniería** — si P3 no supera a P1 por margen propio, recomendar P1.
9. **Limitaciones** — copiar la §8 del spec, sin suavizarla. En particular: esto mide
   predicción, no causalidad; solo un piloto con grupo de control mide impacto real.

- [ ] **Paso 6: enlazar desde el README**

Añadir a la tabla «Por dónde empezar» de `README.md` la fila:

```markdown
| **Quien evalúa el resultado del POC** | [`informes/04-resultados-poc.md`](informes/04-resultados-poc.md) |
```

Y a la lista de la tubería:

```bash
./.venv/bin/python src/10_ejecutar_poc.py           # entrena y evalúa el POC
```

- [ ] **Paso 7: confirmar**

```bash
git add informes/04-resultados-poc.md README.md
git commit -m "poc: informe de resultados"
```

---

## Verificación final

- [ ] `./.venv/bin/python -m pytest -v` → todo en verde
- [ ] `resultados/poc.json` contiene `hit_rate_8` para los cinco modelos
- [ ] El `hit-rate@8` de B1 está a menos de 3 puntos del 47 % esperado
- [ ] Toda métrica del informe está desglosada entre `dormido` y `nunca`
- [ ] `informes/04-resultados-poc.md` tiene las nueve secciones
- [ ] El informe declara que B1 es una reconstrucción y que esto no mide causalidad
- [ ] El informe desglosa los resultados de las rutas abiertas en junio de 2026
- [ ] Ninguna variable del mes *t* se calculó con datos de *t* o posteriores
- [ ] El README enlaza el informe nuevo

---

## Desviaciones durante la ejecución

Registradas conforme ocurrieron, para que el plan no mienta sobre lo que se construyó.

| # | Qué cambió | Por qué |
|---|---|---|
| 1 | Cifras esperadas de la Tarea 1 | El plan decía «> 4.000.000 compras y 428 SKU»; los valores reales son 3.678.221 y 534. Había puesto el conteo *con* paquetes promocionales. |
| 2 | `recomendables()` se partió en `recomendables_base()` + `recomendables_al_mes()` | `activo_ult2m` está calculado sobre el periodo completo: usarlo como filtro en meses de entrenamiento metía futuro. |
| 3 | Prueba `test_solo_propone_recomendables` reescrita | La del plan evaluaba `RECOM \| {"s9"} - {"s9"}`, que por precedencia es `RECOM \| set()`: pasaba sin comprobar nada. |
| 4 | **Candidato pasó de «nunca comprado» a «no pedido en los últimos 2 meses»** | Cambio de diseño pedido por el negocio. Excluir lo dormido descartaba el 21 % de la canasta, y un dormido tiene 8,6 veces más probabilidad de comprarse. |
| 5 | Columna `origen` y variable `es_dormido` | Consecuencia de (4): el origen es la señal más fuerte del conjunto y el desglose es obligatorio. |
| 6 | Ventana de meses por calendario, no por «meses presentes en los datos» | La versión original estiraba la ventana en silencio si un mes venía vacío. Lo destapó una prueba. |
| 7 | **Dos políticas de asignación** (`libre` y `mixta` 5+3) en `metricas.seleccionar` | Pedido por el negocio. La cuota resultó ser por sí sola una mejora de 5,6 puntos sobre B1. |
| 8 | `agregar_afinidad` acumula por cliente, no por fila | Por fila habría tardado horas sobre el conjunto completo. La primera versión rellenaba por posición y habría fallado en silencio con las filas desordenadas; ahora se alinea por índice. |
| 9 | La vara de B1 se movió tres veces | 36,5 % (EDA) → 32,5 % (población completa) → ~47 % (candidatos dormidos). Fijada en el spec. |
