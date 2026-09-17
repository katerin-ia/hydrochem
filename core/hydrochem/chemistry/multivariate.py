"""Analisis multivariante para hidroquimica: PCA y K-Means Clustering.

Permite identificar patrones hidrogeoquimicos y agrupamientos naturales
sin supervisar, basandose en las concentraciones de los iones principales.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.decomposition import PCA
from sklearn.preprocessing import StandardScaler
from sklearn.cluster import KMeans

# Columnas candidatas para el analisis multivariante
MULTIVARIATE_FEATURES = [
    "Ca_mgL", "Mg_mgL", "Na_mgL", "K_mgL",
    "HCO3_mgL", "SO4_mgL", "Cl_mgL", "tds_mgl", "ph", "F_mgL"
]


def run_pca_and_clustering(df: pd.DataFrame, n_clusters: int = 3) -> dict:
    """Ejecuta PCA (2 componentes principales) y agrupamiento K-Means.

    Devuelve un diccionario estructurado con coordenadas de muestras,
    varianza explicada, cargas factoriales (loadings) y resumen por cluster.
    """
    if len(df) < 3:
        return {
            "status": "insufficient",
            "message": "Se necesitan al menos 3 muestras para el analisis multivariante.",
            "samples": [], "loadings": [], "explained_variance": [0.0, 0.0]
        }

    # Seleccionar columnas presentes que tengan valores numericos
    present = [c for c in MULTIVARIATE_FEATURES if c in df.columns]
    if len(present) < 3:
        return {
            "status": "insufficient",
            "message": "Se requieren al menos 3 variables hidroquimicas.",
            "samples": [], "loadings": [], "explained_variance": [0.0, 0.0]
        }

    sub = df[present].apply(pd.to_numeric, errors="coerce")
    # Imputar faltantes con la mediana de cada columna
    sub_clean = sub.fillna(sub.median()).fillna(0.0)

    # Filtrar columnas sin variacion (desviacion estandar cero)
    std = sub_clean.std()
    valid_cols = [c for c in present if std[c] > 1e-6]
    if len(valid_cols) < 2:
        return {
            "status": "insufficient",
            "message": "No hay variacion suficiente en las variables.",
            "samples": [], "loadings": [], "explained_variance": [0.0, 0.0]
        }

    X = sub_clean[valid_cols].to_numpy()
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    # 1. PCA
    pca = PCA(n_components=2)
    coords = pca.fit_transform(X_scaled)
    var_exp = [round(float(v) * 100.0, 1) for v in pca.explained_variance_ratio_]

    # Loadings (cargas de cada variable en PC1 y PC2)
    loadings = []
    for idx_col, col in enumerate(valid_cols):
        clean_name = col.replace("_mgL", "").replace("_mgl", "").upper()
        if col == "tds_mgl": clean_name = "TDS"
        elif col == "ph": clean_name = "pH"
        loadings.append({
            "variable": clean_name,
            "pc1": round(float(pca.components_[0, idx_col]), 3),
            "pc2": round(float(pca.components_[1, idx_col]), 3),
        })

    # 2. K-Means
    k = max(2, min(n_clusters, len(df) - 1, 5))
    kmeans = KMeans(n_clusters=k, random_state=42, n_init=10)
    clusters = kmeans.fit_predict(X_scaled)

    sample_rows = []
    for i in range(len(df)):
        sample_rows.append({
            "id": f"s{i}",
            "pc1": round(float(coords[i, 0]), 3),
            "pc2": round(float(coords[i, 1]), 3),
            "cluster": int(clusters[i]) + 1,
        })

    # Resumen por cluster
    summary = []
    df_temp = df.copy()
    df_temp["cluster"] = clusters + 1
    for cl_id, block in df_temp.groupby("cluster"):
        tds_mean = block["tds_mgl"].mean() if "tds_mgl" in block.columns else None
        facies_mode = block["facies_label"].mode().iloc[0] if "facies_label" in block.columns and not block["facies_label"].dropna().empty else "Mixta"
        summary.append({
            "cluster": int(cl_id),
            "count": int(len(block)),
            "dominant_facies": str(facies_mode),
            "mean_tds": round(float(tds_mean), 1) if tds_mean is not None and not np.isnan(tds_mean) else None
        })

    return {
        "status": "ok",
        "features": valid_cols,
        "explained_variance": var_exp,
        "loadings": loadings,
        "samples": sample_rows,
        "clusters_summary": summary,
    }
