"""Analisis temporal.

El dataset real no tiene fechas, asi que la mayor parte de estas pruebas usa un
fixture **sintetico** construido aqui mismo. Existe para ejercitar el codigo, no
para sustituir datos reales: ninguna conclusion hidroquimica sale de el.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from _fixture import FIXTURE_IONS, load_amargosa
from hydrochem.pipeline import AnalysisOptions, analyse
from hydrochem.temporal import (
    MIN_CAMPAIGNS_FOR_TREND,
    build_index,
    change_summary,
    mann_kendall_sen,
    normalise_dates,
    parameter_series,
    stiff_series,
    trajectories,
    trend_summary,
    vertex_labels,
    vertex_series,
)

CAMPAIGNS = [
    "2021-03-15", "2021-09-20", "2022-03-18", "2022-09-25",
    "2023-03-15", "2023-09-20", "2024-03-18", "2024-09-25",
]


def synthetic_campaigns(n_stations: int = 5, n_campaigns: int = 8) -> pd.DataFrame:
    """Datos SINTETICOS con varias campanas, solo para probar el modulo.

    Se parte de estaciones reales y se aplica una deriva suave y determinista
    hacia el sodio y el cloruro, que es la evolucion que cabe esperar de un
    acuifero que se saliniza. No representa ninguna medida real.
    """
    base = load_amargosa().head(n_stations).reset_index(drop=True)
    blocks = []
    for k in range(n_campaigns):
        block = base.copy()
        block["Sampled_Date"] = CAMPAIGNS[k % len(CAMPAIGNS)]
        drift = 1.0 + 0.18 * k
        block["Na_mgL"] = block["Na_mgL"] * drift
        block["Cl_mgL"] = block["Cl_mgL"] * drift
        block["Ca_mgL"] = block["Ca_mgL"] * (1.0 - 0.05 * k)
        blocks.append(block)
    return pd.concat(blocks, ignore_index=True)


def analysed_synthetic():
    return analyse(synthetic_campaigns(), AnalysisOptions())


# -- sin fechas: el caso real -----------------------------------------------


def test_real_dataset_has_no_temporal_axis():
    idx = build_index(load_amargosa().rename(columns={"Site": "station_code"}))
    assert not idx.has_dates
    assert idx.campaigns == []
    assert not idx.can_plot_series


def test_message_explains_what_is_missing():
    idx = build_index(pd.DataFrame({"station_code": ["A"]}))
    msg = idx.message_es()
    assert "no inventan fechas" in msg or "no traen fecha" in msg


def test_every_function_is_empty_without_dates():
    ds = analyse("tests/fixtures/PiperStiff-QW-2019.v9.xlsm")
    assert vertex_series(ds.data).empty
    assert stiff_series(ds.data).empty
    assert parameter_series(ds.data, ["tds_mgl"]).empty
    assert trajectories(ds.data) == {}
    assert change_summary(ds.data).empty


def test_pipeline_reports_no_campaigns_for_the_real_data():
    ds = analyse("tests/fixtures/PiperStiff-QW-2019.v9.xlsm")
    assert ds.has_dates is False
    assert ds.campaigns == []
    assert ds.temporal.has_dates is False


# -- con fechas: el fixture sintetico ---------------------------------------


def test_dates_are_recognised_and_normalised():
    ds = analysed_synthetic()
    assert ds.has_dates
    assert ds.campaigns == CAMPAIGNS
    assert pd.api.types.is_datetime64_any_dtype(ds.data["sampled_at"])


def test_index_counts_campaigns_and_repeated_stations():
    idx = analysed_synthetic().temporal
    assert idx.has_dates
    assert idx.n_campaigns == 8
    assert len(idx.stations) == 5
    assert len(idx.repeated_stations) == 5, "las 5 se miden en las 8 campanas"
    assert idx.can_plot_series
    assert idx.can_discuss_trend


def test_index_refuses_to_talk_about_trend_with_two_campaigns():
    df = synthetic_campaigns(n_stations=3, n_campaigns=2)
    idx = analyse(df, AnalysisOptions()).temporal
    assert idx.n_campaigns == 2
    assert idx.can_plot_series
    assert not idx.can_discuss_trend
    assert str(MIN_CAMPAIGNS_FOR_TREND) in idx.message_es()


def test_single_campaign_has_no_repeated_stations():
    idx = analyse(synthetic_campaigns(n_stations=4, n_campaigns=1), AnalysisOptions()).temporal
    assert idx.has_dates
    assert idx.repeated_stations == []
    assert not idx.can_plot_series
    assert "ninguna estacion se repite" in idx.message_es()


# -- las esquinas del diagrama en el tiempo ---------------------------------


def test_vertex_series_has_one_row_per_vertex_and_campaign():
    ds = analysed_synthetic()
    s = vertex_series(ds.data)
    assert set(s["vertex"]) == {
        "pct_cat_left", "pct_cat_right", "pct_cat_apex",
        "pct_an_left", "pct_an_right", "pct_an_apex",
    }
    assert len(s) == 5 * len(CAMPAIGNS) * 6, "5 estaciones x campanas x 6 vertices"
    assert s["side"].isin(["cation", "anion"]).all()


def test_vertex_percentages_sum_to_one_hundred_per_side():
    s = vertex_series(analysed_synthetic().data)
    by = s.groupby(["station_code", "sampled_at", "side"])["pct"].sum()
    assert np.allclose(by.to_numpy(), 100.0, atol=1e-6)


def test_vertex_labels_follow_the_convention():
    clasica = vertex_labels("classic")
    notebook = vertex_labels("notebook")
    assert clasica["pct_cat_apex"] == "Mg²⁺"
    assert notebook["pct_cat_apex"] == "Na⁺ + K⁺"
    assert clasica != notebook


def test_vertex_series_is_relabelled_when_the_convention_changes():
    ds = analysed_synthetic()
    a = vertex_series(ds.data, convention="classic")
    b = vertex_series(ds.data, convention="notebook")
    etiqueta = lambda s: s.loc[s["vertex"] == "pct_cat_apex", "label"].iloc[0]
    assert etiqueta(a) != etiqueta(b)


def test_the_synthetic_drift_is_visible_in_the_vertex_series():
    """Comprobacion de extremo a extremo: si el sodio sube, el vertice Na+K
    del triangulo cationico tiene que subir con el."""
    ds = analysed_synthetic()
    s = vertex_series(ds.data, convention="classic")
    nak = s[(s["vertex"] == "pct_cat_right") & (s["station_code"] == s["station_code"].iloc[0])]
    valores = nak.sort_values("sampled_at")["pct"].tolist()
    assert valores == sorted(valores), f"deberia crecer de forma monotona: {valores}"
    assert valores[-1] - valores[0] > 3, "la deriva debe notarse"


def test_change_summary_reports_the_difference_in_points():
    ds = analysed_synthetic()
    resumen = change_summary(ds.data)
    assert len(resumen) == 5 * 6
    nak = resumen[resumen["vertex"] == "pct_cat_right"]
    assert (nak["delta_pp"] > 0).all(), "el sodio sube en todas las estaciones"
    ca = resumen[resumen["vertex"] == "pct_cat_left"]
    assert (ca["delta_pp"] < 0).all(), "y el calcio baja"
    assert (resumen["n_campaigns"] == len(CAMPAIGNS)).all()


def test_change_summary_skips_stations_with_a_single_campaign():
    df = synthetic_campaigns(n_stations=3, n_campaigns=1)
    assert change_summary(analyse(df, AnalysisOptions()).data).empty


# -- Stiff y parametros en el tiempo ----------------------------------------


def test_stiff_series_covers_every_row_and_side():
    ds = analysed_synthetic()
    s = stiff_series(ds.data)
    assert set(s["row"]) == {0, 1, 2}
    assert set(s["side"]) == {"left", "right"}
    assert len(s) == 5 * len(CAMPAIGNS) * 3 * 2


def test_stiff_series_accepts_labels():
    from hydrochem.geometry.stiff import row_labels

    s = stiff_series(analysed_synthetic().data, labels=row_labels("standard"))
    fila0 = s[(s["row"] == 0) & (s["side"] == "left")]
    assert fila0["label"].iloc[0] == "Na⁺ + K⁺"


def test_parameter_series_for_tds_and_balance():
    ds = analysed_synthetic()
    s = parameter_series(ds.data, ["tds_mgl", "CBE_pct", "no_existe"])
    assert set(s["parameter"]) == {"tds_mgl", "CBE_pct"}
    assert len(s) == 5 * len(CAMPAIGNS) * 2


# -- trayectorias en el Piper -----------------------------------------------


def test_trajectories_are_ordered_by_date():
    tr = trajectories(analysed_synthetic().data)
    assert len(tr) == 5
    for station, puntos in tr.items():
        fechas = [p["date"] for p in puntos]
        assert fechas == sorted(fechas)
        assert len(puntos) == len(CAMPAIGNS)
        assert all(len(p["diamond"]) == 2 for p in puntos)


def test_trajectories_move_towards_sodium_and_chloride():
    """Con la deriva sintetica, el punto del rombo debe desplazarse hacia el
    vertice Na-Cl, que en la convencion clasica es el de la derecha."""
    tr = trajectories(analysed_synthetic().data)
    for puntos in tr.values():
        assert puntos[-1]["diamond"][0] > puntos[0]["diamond"][0]


def test_a_station_measured_once_has_no_trajectory():
    df = synthetic_campaigns(n_stations=3, n_campaigns=1)
    assert trajectories(analyse(df, AnalysisOptions()).data) == {}


def test_can_filter_by_station():
    ds = analysed_synthetic()
    una = ds.data["station_code"].iloc[0]
    tr = trajectories(ds.data, stations=[una])
    assert list(tr) == [una]
    assert set(vertex_series(ds.data, stations=[una])["station_code"]) == {una}


# -- robustez ---------------------------------------------------------------


def test_unparseable_dates_are_counted_not_guessed():
    df = synthetic_campaigns(n_stations=2, n_campaigns=2)
    df.loc[0, "Sampled_Date"] = "no es una fecha"
    idx = analyse(df, AnalysisOptions()).temporal
    assert idx.has_dates
    assert idx.n_undated == 1, "la fila ilegible se cuenta, no se adivina"


def test_normalise_dates_is_a_no_op_without_the_column():
    df = pd.DataFrame({"station_code": ["A"]})
    assert normalise_dates(df).equals(df)


# -- tendencias Mann-Kendall y Sen ------------------------------------------


def test_mann_kendall_sen_detects_monotonic_increase():
    dates = [f"2020-0{i+1}-01" for i in range(8)]
    values = [10.0 + 2.0 * i for i in range(8)]
    res = mann_kendall_sen(dates, values)
    assert res["status"] == "increasing"
    assert res["p_value"] < 0.05
    assert res["sen_slope_year"] > 0


def test_mann_kendall_sen_detects_insufficient_data():
    dates = ["2020-01-01", "2020-02-01", "2020-03-01"]
    values = [10, 12, 14]
    res = mann_kendall_sen(dates, values, min_campaigns=8)
    assert res["status"] == "insufficient"


def test_trend_summary_runs_on_synthetic_data():
    ds = analysed_synthetic()
    summary = trend_summary(ds.data, ["Na_mgL", "Cl_mgL"])
    assert not summary.empty
    assert "station_code" in summary.columns
    assert "sen_slope_year" in summary.columns
    assert set(summary["parameter"]) == {"Na_mgL", "Cl_mgL"}
