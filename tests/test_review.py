"""Regression coverage for editable criteria and reproducible exports."""
import io
import json
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fastapi.testclient import TestClient
from app.main import app, SESSIONS, COOKIE_NAME, _options_from
from _fixture import load_amargosa
from hydrochem.pipeline import analyse, AnalysisOptions, with_standard
from hydrochem.quality.standards import custom_standard, get_standard
from hydrochem.geo.exporters.kmz import build


def custom():
    return {"name": "Criterios de ensayo", "limits": [
        {"parameter": "F_mgL", "label": "Fluoruro", "maximum": 0.8, "kind": "health"},
        {"parameter": "ph", "label": "pH", "minimum": 6.5, "maximum": 8.5, "kind": "operational"},
    ]}


def test_limits_reject_nonfinite_reversed_negative_and_duplicate_values():
    invalid = [
        [{"parameter": "F_mgL", "maximum": value}] for value in [float('nan'), float('inf'), -1, True]
    ] + [
        [{"parameter": "ph", "minimum": 9, "maximum": 7}],
        [{"parameter": "ph", "maximum": 15}],
        [{"parameter": "F_mgL"}],
        [{"parameter": "arbitrary", "maximum": 1}],
        [{"parameter": "F_mgL", "maximum": 1}] * 2,
    ]
    for limits in invalid:
        try:
            custom_standard('X', limits)
        except (ValueError, TypeError):
            pass
        else:
            raise AssertionError(f"Accepted invalid criteria: {limits}")


def test_peru_verified_preset_has_annex_references_and_distinct_fluoride_limit():
    std = get_standard('peru_drinking')
    assert std.verified
    assert std.limit_for('F_mgL').maximum == 1
    assert std.limit_for('ph').minimum == 6.5
    assert all(lim.source_url.startswith('https://www.digesa.minsa.gob.pe/') for lim in std.limits)


def test_custom_options_are_portable_and_always_user_defined():
    options = _options_from({'standard': {**custom(), 'verified': True}})
    portable = json.loads(json.dumps(options.to_dict(), allow_nan=False))
    restored = _options_from(portable)
    assert restored.standard.key == 'custom'
    assert not restored.standard.verified
    assert restored.standard.limit_for('F_mgL').maximum == 0.8


def test_built_in_criteria_keep_their_identity_in_saved_options():
    for key in ['who_drinking', 'peru_drinking']:
        options = AnalysisOptions(standard=get_standard(key))
        portable = json.loads(json.dumps(options.to_dict()))
        assert portable['standard'] == key
        assert get_standard(_options_from(portable).standard).verified


def test_reanalysis_reuses_the_original_read_without_changing_measurements():
    source = Path(__file__).parent / 'fixtures' / 'PiperStiff-QW-2019.v9.xlsm'
    first = analyse(source, AnalysisOptions())
    with patch('hydrochem.pipeline.read_table', side_effect=AssertionError('Excel reread')):
        second = analyse(first.read_result, AnalysisOptions(zeros_as_missing_for=('F',)))
    assert second.source == first.source
    assert second.read_result.notes == first.read_result.notes
    assert second.data['Ca_meq'].equals(first.data['Ca_meq'])
    assert second.data['F_mgL'].isna().sum() == 32
    assert first.read_result.data.equals(second.read_result.data)


def test_changing_criteria_preserves_chemistry_and_removes_obsolete_flags():
    ds = analyse(load_amargosa().head(5), AnalysisOptions())
    updated = with_standard(ds, custom_standard(**custom()))
    assert 'Cl_mgL__exceeds' not in updated.data
    assert updated.data['Ca_meq'].equals(ds.data['Ca_meq'])
    assert updated.data['x_diamond'].equals(ds.data['x_diamond'])
    assert updated.source == ds.source
    assert ds.options.standard == 'who_drinking'
    assert updated.options.standard.key == 'custom'


def test_custom_limits_apply_to_upload_state_project_and_invalid_requests():
    with TestClient(app) as client:
        client.get('/')
        try:
            response = client.post('/api/upload',
                files={'file': ('test.csv', load_amargosa().head(5).to_csv(index=False).encode(), 'text/csv')},
                data={'analysis_options': json.dumps({'standard': custom()})})
            assert response.status_code == 200, response.text
            assert response.json()['standard']['key'] == 'custom'
            project = client.get('/api/project').json()
            assert project['options']['standard']['limits'][0]['maximum'] == 0.8
            response = client.post('/api/project', files={'file': ('test.json', json.dumps(project).encode(), 'application/json')})
            assert response.status_code == 200, response.text
            assert response.json()['standard']['key'] == 'custom'
            response = client.post('/api/standard', json={'standard': 'peru_drinking'})
            assert response.status_code == 200, response.text
            assert client.get('/api/state').json()['standard']['key'] == 'peru_drinking'
            response = client.post('/api/standard', json={'standard': {'name':'bad', 'limits':[{'parameter':'F_mgL','maximum':-1}]}})
            assert response.status_code == 400
            assert client.get('/api/state').json()['standard']['key'] == 'peru_drinking'
        finally:
            SESSIONS.drop(client.cookies.get(COOKIE_NAME))


def test_compact_kmz_filters_invalid_coordinates_and_preserves_criteria():
    ds = analyse(load_amargosa().head(5), AnalysisOptions())
    ds.data.loc[ds.data.index[0], 'lon_wgs84'] = 200
    std = custom_standard(**custom())
    result = build(ds.data, standard=std, detailed_popups=False)
    assert result.n_skipped == 1 and result.n_placemarks == 4
    archive = zipfile.ZipFile(io.BytesIO(result.content))
    xml = archive.read('doc.kml').decode()
    ET.fromstring(xml)
    assert '<LookAt>' in xml
    assert not any(name.startswith('files/popup_') for name in archive.namelist())
    assert 'escala común' in xml
    metadata = json.loads(archive.read('metadatos.json'))
    assert metadata['standard']['key'] == 'custom'
    assert metadata['standard']['limits'][0]['maximum'] == 0.8
    assert metadata['scale_meq_per_side'] > 0
