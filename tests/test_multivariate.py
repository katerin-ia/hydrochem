"""Pruebas para analisis multivariante (PCA y clustering)."""

import pandas as pd
from hydrochem.chemistry.multivariate import run_pca_and_clustering


def test_pca_and_clustering_runs():
    df = pd.DataFrame({
        "station_code": [f"PZ-{i}" for i in range(1, 6)],
        "Ca_mgL": [40.0, 50.0, 60.0, 80.0, 90.0],
        "Mg_mgL": [10.0, 15.0, 20.0, 25.0, 30.0],
        "Na_mgL": [20.0, 35.0, 50.0, 75.0, 100.0],
        "Cl_mgL": [15.0, 30.0, 45.0, 60.0, 80.0],
        "SO4_mgL": [30.0, 40.0, 50.0, 60.0, 70.0],
        "HCO3_mgL": [120.0, 140.0, 160.0, 180.0, 200.0],
        "tds_mgl": [300.0, 350.0, 400.0, 500.0, 600.0],
    })
    res = run_pca_and_clustering(df, n_clusters=2)
    assert res["status"] == "ok"
    assert len(res["explained_variance"]) == 2
    assert len(res["loadings"]) > 0
    assert len(res["samples"]) == 5
    assert len(res["clusters_summary"]) > 0
