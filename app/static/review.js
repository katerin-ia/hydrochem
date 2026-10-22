/* Presentation, view exports and browser-local comparison criteria. */
const STANDARD_STORAGE = 'hydrochem.criteria.v1';

function setStartupReady(ready) {
  S.optionsReady = ready;
  ['#btn-open', '#btn-open-2', '#btn-example', '#btn-example-2', '#btn-demo', '#btn-demo-2', '#btn-project-open', '#file-input', '#project-input'].forEach(selector => {
    const element = $(selector);
    if (element) element.disabled = !ready;
  });
  $('#drop')?.setAttribute('aria-disabled', String(!ready));
}

function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>"']/g, c =>
    ({'&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;'}[c]));
}

function renderPlot(el, traces, layout, config) {
  if (typeof el === 'string') el = document.getElementById(el);
  const promise = Plotly.react(el, traces, layout, {
    ...config, modeBarButtonsToRemove: [...new Set([
      ...(config?.modeBarButtonsToRemove || []), 'toImage'
    ])]
  });
  el._hcReady = Promise.resolve(promise);
  return promise;
}

function readCriteria() {
  try {
    const saved = JSON.parse(localStorage.getItem(STANDARD_STORAGE));
    if (!saved || saved.version !== 1) return null;
    if (saved.custom && (!Array.isArray(saved.custom.limits) || !saved.custom.limits.length)) return null;
    return saved;
  } catch { return null; }
}

function rememberCriteria(active, custom = S.customStandard) {
  try {
    localStorage.setItem(STANDARD_STORAGE, JSON.stringify({version: 1, active, custom}));
    return true;
  } catch {
    toast('Los límites se aplicaron, pero el navegador no permite guardarlos. Puedes exportar el proyecto para conservarlos.', true);
    return false;
  }
}

function syncStandardMenu(selected) {
  const select = $('#sel-standard');
  const standards = (S.standardCatalog || []).filter(s => s.key !== 'peru_drinking_template');
  if (S.data?.standard.key === 'peru_drinking_template') {
    const legacy = S.standardCatalog.find(s => s.key === 'peru_drinking_template');
    if (legacy) standards.push(legacy);
  }
  select.replaceChildren(...standards.map(s => new Option(s.name, s.key)));
  if (S.customStandard) select.add(new Option(S.customStandard.name + ' · personalizado', 'custom'));
  if ([...select.options].some(o => o.value === selected)) select.value = selected;
}

async function applyStandardSelection() {
  if (!S.data) return;
  const selected = $('#sel-standard').value;
  busy(true, 'Actualizando la comparación de límites…');
  try {
    adopt(await post('/api/standard', {standard: selected === 'custom' ? S.customStandard : selected}));
    rememberCriteria(selected);
  } catch (error) {
    syncStandardMenu(S.data.standard.key);
    toast(error.message, true);
  } finally { busy(false); }
}

function openCriteriaEditor() {
  const standard = S.data?.standard;
  if (!standard) return;
  const limits = standard.limits || [];
  const available = new Map(limits.map(lim => [lim.parameter, lim]));
  // Include the other supported ions so a user's criterion is not limited to the preset.
  (S.criteriaParameters || []).forEach(field => {
    if (!available.has(field.key)) available.set(field.key, {
      parameter: field.key, label: field.label, unit: field.unit,
      minimum: null, maximum: null, kind: 'health', note: ''
    });
  });
  S.criteriaDraft = [...available.values()];
  $('#criteria-name').value = standard.key === 'custom' ? standard.name : 'Mis criterios de comparación';
  $('#criteria-table').innerHTML = `<thead><tr><th>Usar</th><th>Parámetro</th><th>Unidad</th>
    <th>Mínimo</th><th>Máximo</th><th>Tipo de criterio</th></tr></thead><tbody>` +
    S.criteriaDraft.map((lim, i) => `<tr data-limit="${i}">
      <td><input type="checkbox" class="limit-enabled" aria-label="Incluir ${escapeHtml(lim.label)}" ${limits.some(l => l.parameter === lim.parameter) ? 'checked' : ''}></td>
      <td>${escapeHtml(lim.label)}</td><td>${escapeHtml(lim.unit)}</td>
      <td><input type="number" step="any" class="limit-min" aria-label="Mínimo ${escapeHtml(lim.label)}" value="${lim.minimum ?? ''}"></td>
      <td><input type="number" step="any" class="limit-max" aria-label="Máximo ${escapeHtml(lim.label)}" value="${lim.maximum ?? ''}"></td>
      <td><select class="limit-kind" aria-label="Tipo ${escapeHtml(lim.label)}">${[
        ['health','Sanitario'], ['aesthetic','Organoléptico'], ['operational','Operativo']
      ].map(([key, label]) => `<option value="${key}" ${lim.kind === key ? 'selected' : ''}>${label}</option>`).join('')}</select></td>
    </tr>`).join('') + '</tbody>';
  $('#criteria-error').textContent = '';
  $('#criteria-sheet').hidden = false;
}

async function saveCriteria() {
  const limits = [];
  try {
    $('#criteria-table').querySelectorAll('tbody tr').forEach(tr => {
      if (!tr.querySelector('.limit-enabled').checked) return;
      const base = S.criteriaDraft[Number(tr.dataset.limit)];
      const number = cls => {
        const input = tr.querySelector(cls);
        if (input.validity.badInput) throw new Error('Revisa los valores numéricos.');
        if (!input.value.trim()) return null;
        const value = Number(input.value);
        if (!Number.isFinite(value)) throw new Error('Los límites deben ser números finitos.');
        return value;
      };
      const minimum = number('.limit-min'), maximum = number('.limit-max');
      if (minimum === null && maximum === null) throw new Error(`Indica un límite para ${base.label} o desmarca el parámetro.`);
      if (minimum !== null && maximum !== null && minimum > maximum) throw new Error(`Revisa el intervalo de ${base.label}: el mínimo supera al máximo.`);
      limits.push({parameter: base.parameter, label: base.label, unit: base.unit,
        minimum, maximum, kind: tr.querySelector('.limit-kind').value});
    });
    if (!limits.length) throw new Error('Incluye al menos un parámetro.');
    const name = $('#criteria-name').value.trim();
    if (!name) throw new Error('Escribe un nombre para tus criterios.');
    busy(true, 'Aplicando los límites personalizados…');
    const custom = {name, limits};
    const payload = await post('/api/standard', {standard: custom});
    S.customStandard = custom;
    syncStandardMenu('custom');
    adopt(payload);
    const saved = rememberCriteria('custom', custom);
    $('#criteria-sheet').hidden = true;
    toast(saved ? 'Límites aplicados y guardados en este navegador.' : 'Límites aplicados en esta sesión.');
  } catch (error) {
    $('#criteria-error').textContent = error.message;
  } finally { busy(false); }
}

function currentViewFigure(view, plotId) {
  const optionText = selector => $(selector)?.selectedOptions?.[0]?.textContent || '';
  const views = {
    piper: {id: 'piper-plot', title: 'Diagrama de Piper',
      detail: `${S.data.piper.name} · Color: ${optionText('#sel-colorby')}`},
    cross: {id: 'piper-plot2', title: 'Diagrama de Piper', detail: S.data.piper.name},
    stiff: {id: 'stiff-plot', title: S.stiffMode === 'each' ? 'Diagramas de Stiff por muestra' : 'Diagramas de Stiff por grupo',
      detail: `${S.data.stiff.name} · Escala común en meq/L`},
    durov: {id: 'durov-plot', title: 'Diagrama de Durov', detail: `Color: ${optionText('#sel-durovcolor')}`},
    temporal: {id: 'temporal-plot', title: optionText('#sel-temporal-mode'),
      detail: `Estación: ${$('#sel-station')?.value || ''}`},
    norm: {id: 'norm-plot', title: 'Muestras fuera del criterio de comparación', detail: S.data.standard.name},
    fluoride: {id: plotId || 'fluoride-boxplot',
      title: plotId === 'fluoride-scatter' ? 'Fluoruro frente a calcio' : 'Distribución de fluoruro por grupo',
      detail: S.data.standard.name}
  };
  return views[view];
}

async function descargarVista(view, plotId) {
  if (S.exportingView) return;
  if (view === 'validation') return descargarFigura('balance');
  const spec = S.data && currentViewFigure(view, plotId);
  const el = spec && document.getElementById(spec.id);
  if (!el?.data?.length || (view === 'temporal' && (S.temporalLoading || $('#sel-temporal-mode').value === 'trends'))) {
    toast('Espera a que se dibuje la gráfica que deseas descargar.', true);
    return;
  }
  const snapshot = document.createElement('div');
  snapshot.style.cssText = 'position:fixed;left:-20000px;top:0;pointer-events:none;';
  document.body.appendChild(snapshot);
  S.exportingView = true;
  busy(true, 'Preparando PNG de la vista actual…');
  try {
    await el._hcReady;
    const width = Math.max(1100, Math.min(1500, el.clientWidth || 1100));
    const height = Math.max(580, Math.round((el.layout.height || el.clientHeight || 520) * width / (el.clientWidth || width)) + 100);
    if (height > 6000) throw new Error('Selecciona menos muestras para obtener una imagen legible.');
    const layout = JSON.parse(JSON.stringify(el.layout));
    Object.assign(layout, {width, height, autosize: false, paper_bgcolor: '#ffffff', plot_bgcolor: '#ffffff'});
    layout.margin = {...layout.margin, t: Math.max(110, (layout.margin?.t || 20) + 80)};
    const count = view === 'stiff' ? Math.min(S.selection.size || S.data.n_samples, S.stiffMode === 'each' ? 24 : Infinity) : S.data.n_samples;
    let countText = count !== S.data.n_samples ? `${count} de ${S.data.n_samples} muestras representadas` : `${count} muestras`;
    if (view === 'temporal') {
      const campaigns = new Set(S.samples.filter(s => s.station === $('#sel-station').value).map(s => s.sampled_at).filter(Boolean));
      countText = `${campaigns.size} campañas`;
      layout.annotations = (layout.annotations || []).filter(a => !/^Estaci[oó]n/.test(a.text || ''));
    }
    if (view === 'fluoride') {
      const measured = fluorideSamples().filter(s => spec.id !== 'fluoride-scatter' || s.mgl.Ca !== null && s.mgl.Ca !== undefined);
      countText = `${measured.length} muestras medidas`;
    }
    const demo = S.data.is_synthetic_demo ? '<br><sup>Datos sintéticos de demostración</sup>' : '';
    layout.title = {text: `<b>${escapeHtml(spec.title)}</b><br><sup>${escapeHtml(spec.detail)} · ${countText}${S.selection.size ? ` · ${S.selection.size} seleccionadas` : ''}</sup>${demo}`,
      x: 0.5, xanchor: 'center', y: 1, yref: 'container', yanchor: 'top', pad: {t: 18}, font: {size: 18, color: '#16241d'}};
    if (layout.legend) layout.legend = {...layout.legend, bgcolor: '#ffffff'};
    await Plotly.newPlot(snapshot, JSON.parse(JSON.stringify(el.data)), layout, {staticPlot: true});
    const url = await Plotly.toImage(snapshot, {format: 'png', width, height, scale: height > 3500 ? 1 : 2});
    const name = `${S.data.source.replace(/\.[^.]+$/, '')}_${spec.id}_${view === 'temporal' ? $('#sel-temporal-mode').value : 'vista'}`
      .normalize('NFD').replace(/[\u0300-\u036f]/g, '').replace(/[^a-zA-Z0-9_-]+/g, '_');
    const bytes = Uint8Array.from(atob(url.split(',')[1]), character => character.charCodeAt(0));
    guardarBlob(new Blob([bytes], {type: 'image/png'}), `${name}.png`);
    toast('PNG descargado con las opciones de la vista actual.');
  } catch (error) {
    toast(`No se pudo descargar esta vista: ${error.message}`, true);
  } finally {
    Plotly.purge(snapshot); snapshot.remove(); S.exportingView = false; busy(false);
  }
}

function renderNormChart(std) {
  const el = $('#norm-plot');
  if (!el) return;
  const rows = std.rows.filter(r => r.n_measured > 0);
  renderPlot(el, [{type: 'bar', orientation: 'h',
    x: rows.map(r => r.pct), y: rows.map(r => r.label),
    text: rows.map(r => `${r.n_exceeding} / ${r.n_measured}`), textposition: 'auto',
    marker: {color: rows.map(r => r.n_exceeding ? (r.kind === 'health' ? '#a32020' : '#8a6a00') : '#0f7d52')},
    hovertemplate: '%{y}: %{x:.1f} %<extra></extra>'}], {
    height: Math.max(270, rows.length * 38 + 100), margin: {l: 100, r: 30, t: 25, b: 65},
    paper_bgcolor: '#ffffff', plot_bgcolor: '#ffffff', showlegend: false,
    xaxis: {range: [0, 100], title: {text: 'Muestras medidas fuera del criterio (%)'}, gridcolor: '#dbe9e1'},
    yaxis: {autorange: 'reversed', automargin: true}, font: {family: 'Arial, sans-serif', size: 12, color: '#16241d'}
  }, {responsive: true, displaylogo: false});
}

function renderTrendTable(data, station) {
  const labels = data.parameter_labels || {};
  $('#temporal-body').innerHTML = `<div class="body-scroll"><h3>Tendencias por parámetro · ${escapeHtml(station)}</h3>
    <p>Prueba de Mann–Kendall y pendiente de Sen por año. No corrige estacionalidad ni autocorrelación.</p>
    <table><thead><tr><th>Parámetro</th><th>Campañas</th><th>p</th><th>Pendiente por año</th><th>Resultado</th></tr></thead><tbody>${(data.trends || []).map(r =>
      `<tr><td>${escapeHtml(labels[r.parameter] || r.parameter)}</td><td>${r.n_campaigns}</td><td>${fmt(r.p_value, 4)}</td><td>${fmt(r.sen_slope_year, 3)}</td><td>${escapeHtml(r.message)}</td></tr>`).join('')}</tbody></table></div>`;
}

async function downloadKmz() {
  const query = new URLSearchParams({colour_by: $('#sel-kmz-color').value, detailed: $('#sel-kmz-detail').value});
  busy(true, 'Preparando KMZ…');
  try {
    const response = await fetch(`/api/export/kmz?${query}`);
    if (!response.ok) throw new Error((await response.json()).detail || 'No se pudo generar el KMZ.');
    guardarBlob(await response.blob(), nombreDeArchivo(response, 'hydrochem.kmz'));
    const skipped = Number(response.headers.get('X-Skipped') || 0);
    toast(`KMZ descargado.${skipped ? ` ${skipped} muestras omitidas por coordenadas ausentes o inválidas.` : ''}`);
  } catch (error) { toast(error.message, true); }
  finally { busy(false); }
}

async function openProjectFile(file) {
  if (!file) return;
  busy(true, 'Abriendo proyecto…');
  try {
    const form = new FormData(); form.append('file', file);
    const response = await fetch('/api/project', {method: 'POST', body: form});
    if (!response.ok) throw new Error((await response.json()).detail || 'No se pudo abrir el proyecto.');
    adopt(await response.json());
    rememberCriteria(S.data.standard.key);
    toast('Proyecto recuperado con sus datos y criterios.');
  } catch (error) { toast(error.message, true); }
  finally { busy(false); }
}
