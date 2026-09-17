"""Analisis multivariante para hidroquimica: PCA y K-Means Clustering.

Permite identificar patrones hidrogeoquimicos y agrupamientos naturales
sin supervisar, basandose en las concentraciones de los iones principales.

scikit-learn es OPCIONAL y por eso no se importa aqui arriba. Son mas de
100 MB con scipy, y en el alojamiento gratuito no esta instalado. Importarlo
al cargar el modulo tumbaba la aplicacion entera al arrancar -no solo esta
pantalla- porque ``app/main.py`` importa este modulo. El import va dentro de
la funcion, y cuando falta se devuelve un resultado que lo dice en vez de
reventar; la interfaz ya sabe leer ese ``status``.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

# Columnas candidatas para el analisis multivariante
MULTIVARIATE_FEATURES = [
    "Ca_mgL", "Mg_mgL", "Na_mgL", "K_mgL",
    "HCO3_mgL", "SO4_mgL", "Cl_mgL", "tds_mgl", "ph", "F_mgL"
]


def available() -> bool:
    """Si scikit-learn esta instalado en este entorno."""
    try:
        import sklearn  # noqa: F401
    except ImportError:
        return False
    return True


def _no_disponible(mensaje: str, status: str = "insufficient") -> dict:
    """Respuesta con la forma de siempre para que la interfaz no se entere."""
    return {
        "status": status,
        "message": mensaje,
        "samples": [], "loadings": [], "explained_variance": [0.0, 0.0],
    }


def run_pca_and_clustering(df: pd.DataFrame, n_clusters: int = 3) -> dict:
    """Ejecuta PCA (2 componentes principales) y agrupamiento K-Means.

    Devuelve un diccionario estructurado con coordenadas de muestras,
    varianza explicada, cargas factoriales (loadings) y resumen por cluster.

    Si falta scikit-learn devuelve ``status="unavailable"``: el resto de la
    aplicacion tiene que seguir funcionando sin el.
    """
    try:
        from sklearn.cluster import KMeans
        from sklearn.decomposition import PCA
        from sklearn.preprocessing import StandardScaler
    except ImportError:
        return _no_disponible(
            "El analisis multivariante (PCA y agrupamiento) necesita "
            "scikit-learn, que no esta instalado en este servidor. Todo lo "
            "demas funciona igual.",
            status="unavailable",
        )

    if len(df) < 3:
        return _no_disponible("Se necesitan al menos 3 muestras para el analisis multivariante.")

    # Seleccionar columnas presentes que tengan valores numericos
    present = [c for c in MULTIVARIATE_FEATURES if c in df.columns]
    if len(present) < 3:
        return _no_disponible("Se requieren al menos 3 variables hidroquimicas.")

    sub = df[present].apply(pd.to_numeric, errors="coerce")
    # Imputar faltantes con la mediana de cada columna
    sub_clean = sub.fillna(sub.median()).fillna(0.0)

    # Filtrar columnas sin variacion (desviacion estandar cero)
    std = sub_clean.std()
    valid_cols = [c for c in present if std[c] > 1e-6]
    if len(valid_cols) < 2:
        return _no_disponible("No hay variacion suficiente en las variables.")

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
