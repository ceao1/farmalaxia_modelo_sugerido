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
