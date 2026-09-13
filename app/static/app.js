/* HydroChem - logica de la interfaz.
 *
 * Un unico estado compartido por todas las vistas. La seleccion es un conjunto
 * de ids de muestra, y tanto el Piper como el mapa como la tabla leen el mismo
 * array: eso es lo que hace posible la seleccion cruzada sin duplicar datos.
 */

const S = {
  data: null,          // respuesta completa del servidor
  samples: [],         // atajo a data.samples
  byId: new Map(),
  selection: new Set(),
  view: 'welcome',
  colorBy: 'facies',
  mapColorBy: 'facies',
  stiffMode: 'group',
  maps: {},            // instancias de Leaflet por contenedor
  markers: {},         // id -> [marcadores] por contenedor
  piperDrawn: new Set(),
  zerosDecided: false,
  zerosAsMissing: [],
  durovColorBy: 'facies',
  durovDrawn: false,
  showTrajectories: false,
  trajectories: null,
  mappingData: null
};

/* ---------------------------------------------------------------- utilidades */

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => Array.from(document.querySelectorAll(sel));

// Paleta retro de alta diferenciación: funciona sobre el papel cálido de la UI
// y conserva contraste cuando los grupos se superponen en los diagramas.
const PALETTE = ['#0d6e7b', '#b43c2b', '#5d4197', '#27704f', '#a94e10',
                 '#176ca5', '#9b2e63', '#69702c', '#4d557f', '#7c4630'];

const CBE_COLORS = { acceptable: '#176b50', marginal: '#9b4a14', rejected: '#a72d45', unknown: '#657189' };
const CBE_LABELS = { acceptable: 'Aceptable', marginal: 'Marginal', rejected: 'Rechazado', unknown: 'Sin datos' };

function fmt(v, d = 2) {
  if (v === null || v === undefined || Number.isNaN(v)) return '—';
  return Number(v).toLocaleString('es-ES', { minimumFractionDigits: d, maximumFractionDigits: d });
}

function toast(msg, isError) {
  const el = document.createElement('div');
  el.className = 'toast' + (isError ? ' err' : '');
  el.textContent = msg;
  document.body.appendChild(el);
  setTimeout(() => el.remove(), isError ? 6000 : 3000);
}

function busy(on) { $('#spinner').hidden = !on; }

function isDark() {
  return matchMedia('(prefers-color-scheme: dark)').matches;
}
const THEME = () => isDark()
  ? { ink: '#fff8e7', ink2: '#d1d8e4', ink3: '#aeb9ce', grid: '#40506d', edge: '#fff8e7', paper: '#202e49' }
  : { ink: '#18243b', ink2: '#435067', ink3: '#657189', grid: '#d6c8a9', edge: '#18243b', paper: '#fffdf7' };

/* ------------------------------------------------------------------- colores */

function groupColors() {
  const map = new Map();
  (S.data?.groups || []).forEach((g, i) => map.set(g, PALETTE[i % PALETTE.length]));
  return map;
}

function tdsScale() {
  const vals = S.samples.map(s => s.tds).filter(v => v !== null);
  return { min: Math.min(...vals), max: Math.max(...vals) };
}

const NORM_COLORS = { ok: '#176b50', aesthetic: '#9b4a14', health: '#a72d45' };
const NORM_LABELS = {
  ok: 'Cumple todos los umbrales',
  aesthetic: 'Supera algún umbral organoléptico',
  health: 'Supera un umbral sanitario'
};

function normClass(sample) {
  if (sample.exceeds_health) return 'health';
  if (sample.n_exceedances > 0) return 'aesthetic';
  return 'ok';
}

function colorFor(sample, mode) {
  if (mode === 'facies') {
    const table = S.data?.facies?.colors || {};
    return table[sample.facies] || '#7f9299';
  }
  if (mode === 'norm') return NORM_COLORS[normClass(sample)];
  if (mode === 'cbe') return CBE_COLORS[sample.cbe_flag] || CBE_COLORS.unknown;
  if (mode === 'tds') {
    const { min, max } = tdsScale();
    if (sample.tds === null || !isFinite(min)) return '#7f9299';
    const t = max > min ? (sample.tds - min) / (max - min) : 0.5;
    // rampa sobria teal -> ambar
    const c1 = [13, 110, 123], c2 = [180, 60, 43];
    return `rgb(${c1.map((v, i) => Math.round(v + t * (c2[i] - v))).join(',')})`;
  }
  return groupColors().get(sample.group) || '#7f9299';
}

function legendEntries(mode) {
  if (mode === 'facies') {
    const counts = S.data?.facies?.counts || [];
    const labels = S.data?.facies?.labels || {};
    const colors = S.data?.facies?.colors || {};
    return counts.map(c => ({
      color: colors[c.facies] || '#7f9299',
      label: `${labels[c.facies] || c.facies} (${c.n})`
    }));
  }
  if (mode === 'norm') {
    return Object.keys(NORM_LABELS).map(k => {
      const n = S.samples.filter(s => normClass(s) === k).length;
      return { color: NORM_COLORS[k], label: `${NORM_LABELS[k]} (${n})` };
    });
  }
  if (mode === 'cbe') {
    return Object.keys(CBE_LABELS).map(k => ({ color: CBE_COLORS[k], label: CBE_LABELS[k] }));
  }
  if (mode === 'tds') {
    const { min, max } = tdsScale();
    return [
      { color: colorFor({ tds: min }, 'tds'), label: `TDS ${fmt(min, 0)} mg/L` },
      { color: colorFor({ tds: max }, 'tds'), label: `TDS ${fmt(max, 0)} mg/L` }
    ];
  }
  const gc = groupColors();
  return (S.data?.groups || []).map(g => ({ color: gc.get(g), label: g }));
}

/* -------------------------------------------------------------- carga de datos */

async function post(url, body) {
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body || {})
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(detail.detail || 'Error inesperado');
  }
  return res.json();
}

async function loadExample() {
  busy(true);
  try { adopt(await post('/api/load-example', currentOptions())); }
  catch (e) { toast(e.message, true); }
  finally { busy(false); }
}

async function loadDemoCampaigns() {
  busy(true);
  try { adopt(await post('/api/demo-campaigns', currentOptions())); }
  catch (e) { toast(e.message, true); }
  finally { busy(false); }
}

async function uploadFile(file) {
  busy(true);
  const form = new FormData();
  form.append('file', file);
  try {
    const res = await fetch('/api/upload', { method: 'POST', body: form });
    if (!res.ok) {
      const d = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(d.detail);
    }
    adopt(await res.json());
  } catch (e) { toast(e.message, true); }
  finally { busy(false); }
}

function currentOptions(extra) {
  const o = {
    piper_convention: $('#sel-convention').value || undefined,
    stiff_template: $('#sel-stiff').value || undefined,
    facies_scheme: $('#sel-facies').value || undefined,
    standard: $('#sel-standard').value || undefined,
    crs: $('#sel-crs').value || undefined
  };
  // Solo se manda si el usuario ha decidido: sin la clave, el servidor aplica
  // su criterio por defecto (tratar los ceros sospechosos como no medidos).
  if (S.zerosDecided) o.zeros_as_missing_for = S.zerosAsMissing;
  return Object.assign(o, extra || {});
}

async function setZeroPolicy(ions) {
  S.zerosDecided = true;
  S.zerosAsMissing = ions;
  await reanalyse();
}

async function reanalyse() {
  busy(true);
  try { adopt(await post('/api/reanalyse', currentOptions())); }
  catch (e) { toast(e.message, true); }
  finally { busy(false); }
}

function adopt(payload) {
  S.data = payload;
  S.samples = payload.samples;
  S.byId = new Map(S.samples.map(s => [s.id, s]));
  S.selection.clear();
  S.piperDrawn.clear();
  S.zerosAsMissing = payload.zeros_as_missing_for || [];
  const selEstacion = $('#sel-station');
  if (selEstacion) selEstacion.dataset.filled = '';
  S.trajectories = null;
  S.durovDrawn = false;
  const np = $('#sel-normparam');
  if (np) np.dataset.filled = '';

  $('#file-chip').hidden = false;
  $('#file-name').textContent = payload.source;
  document.body.dataset.demo = payload.is_synthetic_demo ? 'si' : 'no';
  $('#file-meta').textContent = ` · ${payload.n_samples} muestras`;
  $$('#rail button').forEach(b => { b.disabled = false; });
  const tempBtn = document.querySelector('#rail button[data-view="temporal"]');
  if (tempBtn) tempBtn.disabled = false;  // la vista explica su propio estado vacio
  if (!payload.has_coordinates) {
    $$('#rail button').forEach(b => {
      if (b.dataset.view === 'map' || b.dataset.view === 'cross') b.disabled = true;
    });
  }

  syncSelects();
  renderStatus();
  renderTable('#data-table', S.samples);
  renderTable('#cross-table', S.samples);
  renderValidation();
  renderExport();
  if (S.view === 'welcome') showView('validation');
  else refreshView();
}

function syncSelects() {
  const conv = $('#sel-convention');
  if (conv.options.length) conv.value = S.data.piper.convention;
  const st = $('#sel-stiff');
  if (st.options.length) st.value = S.data.stiff.template;
  $('#piper-note').textContent = S.data.piper.note;
  $('#stiff-note').textContent = S.data.stiff.note;
  const f = $('#sel-facies');
  if (f.options.length) f.value = S.data.facies.scheme;
  const norma = $('#sel-standard');
  if (norma.options.length && S.data.standard.key) norma.value = S.data.standard.key;
  const c = $('#sel-crs');
  if (c.options.length) c.value = S.data.crs_declared ? String(S.data.crs.epsg) : '';
}

/* ------------------------------------------------------------------- barra estado */

function renderStatus() {
  if (!S.data) return;
  $('#st-samples').innerHTML = `<b>${S.data.n_samples}</b> muestras · ${S.data.groups.length} grupos`;
  $('#st-sel').textContent = `${S.selection.size} seleccionadas`;
  $('#st-conv').textContent = `Piper: ${S.data.piper.name}`;
  $('#st-campaign').textContent = S.data.has_dates
    ? `${S.data.campaigns.length} campañas`
    : 'campaña única — sin fecha registrada';
}

/* ------------------------------------------------------------------ navegacion */

function showView(name) {
  S.view = name;
  $$('.view').forEach(v => v.dataset.active = String(v.dataset.view === name));
  $$('#rail button').forEach(b => b.setAttribute('aria-current', String(b.dataset.view === name)));
  refreshView();
}

function refreshView() {
  if (!S.data) return;
  if (S.view === 'piper') drawPiper('piper-plot');
  if (S.view === 'stiff') drawStiff();
  if (S.view === 'temporal') drawTemporal();
  if (S.view === 'durov') drawDurov();
  if (S.view === 'norm') drawNorm();
  if (S.view === 'map') { ensureMap('map'); paintMarkers('map', S.mapColorBy); }
  if (S.view === 'cross') {
    ensureMap('map2'); paintMarkers('map2', S.mapColorBy); drawPiper('piper-plot2');
  }
}

/* ---------------------------------------------------------------------- Piper */

function piperTraces(divId) {
  const bg = S.data.piper.background;
  const th = THEME();
  const traces = [];

  // rejilla
  const gx = [], gy = [];
  bg.gridlines.forEach(([x0, y0, x1, y1]) => { gx.push(x0, x1, null); gy.push(y0, y1, null); });
  traces.push({
    x: gx, y: gy, mode: 'lines', type: 'scatter', hoverinfo: 'skip', showlegend: false,
    line: { color: th.grid, width: 0.7 }
  });

  // contornos
  bg.outlines.forEach(poly => {
    traces.push({
      x: poly.map(p => p[0]), y: poly.map(p => p[1]), mode: 'lines', type: 'scatter',
      hoverinfo: 'skip', showlegend: false, line: { color: th.edge, width: 1.4 }
    });
  });

  // Una serie por categoria del criterio de color: asi la leyenda de Plotly
  // sirve de filtro sobre lo que se esta mirando, no sobre el grupo siempre.
  const porFacies = S.colorBy === 'facies';
  const cats = porFacies
    ? (S.data.facies.counts || []).map(c => c.facies)
    : (S.data.groups.length ? S.data.groups : ['Sin grupo']);
  const nombreCat = c => porFacies
    ? (S.data.facies.labels[c] || c) : c;

  cats.forEach(cat => {
    const g = nombreCat(cat);
    const subset = S.samples.filter(s => (porFacies ? s.facies : s.group) === cat);
    if (!subset.length) return;
    const colors = subset.map(s => colorFor(s, S.colorBy));
    const sizes = subset.map(s => S.selection.has(s.id) ? 15 : 8);
    const opac = subset.map(s => (S.selection.size === 0 || S.selection.has(s.id)) ? 0.95 : 0.18);
    const lw = subset.map(s => S.selection.has(s.id) ? 2 : 0.6);
    const text = subset.map(s => hoverText(s));
    const common = {
      type: 'scattergl', mode: 'markers', name: g, legendgroup: g,
      customdata: subset.map(s => s.id), text,
      hovertemplate: '%{text}<extra></extra>',
      marker: { color: colors, size: sizes, opacity: opac,
                line: { color: isDark() ? '#0c1418' : '#ffffff', width: lw } }
    };
    traces.push({ ...common,
      x: subset.map(s => s.piper.cat[0]), y: subset.map(s => s.piper.cat[1]) });
    traces.push({ ...common, showlegend: false,
      x: subset.map(s => s.piper.an[0]), y: subset.map(s => s.piper.an[1]) });
    traces.push({ ...common, showlegend: false,
      marker: { ...common.marker, symbol: 'diamond' },
      x: subset.map(s => s.piper.diamond[0]), y: subset.map(s => s.piper.diamond[1]) });
  });
  if (S.showTrajectories && S.trajectories) {
    Object.entries(S.trajectories).forEach(([estacion, puntos]) => {
      ['diamond', 'cat', 'an'].forEach(parte => {
        traces.push({
          x: puntos.map(p => p[parte][0]), y: puntos.map(p => p[parte][1]),
          type: 'scatter', mode: 'lines+markers',
          line: { color: th.ink2, width: 1.4, dash: 'dot' },
          marker: { size: 4, color: th.ink2 },
          showlegend: false, hoverinfo: 'skip',
          name: estacion
        });
        // punta de flecha en la ultima campana
        const ult = puntos[puntos.length - 1][parte];
        traces.push({
          x: [ult[0]], y: [ult[1]], type: 'scatter', mode: 'markers',
          marker: { symbol: 'circle-open', size: 13, color: th.ink,
                    line: { width: 1.6 } },
          showlegend: false,
          hovertemplate: `<b>${estacion}</b><br>ultima campana<extra></extra>`
        });
      });
    });
  }

  return traces;
}

async function loadTrajectories() {
  const t = S.data.temporal;
  if (!t.has_dates || !t.repeated_stations.length) { S.trajectories = null; return; }
  const acumulado = {};
  // Solo la estacion seleccionada, o todas si no hay seleccion y son pocas
  let estaciones = [];
  if (S.selection.size) {
    estaciones = Array.from(new Set(
      Array.from(S.selection).map(id => S.byId.get(id)?.station).filter(Boolean)
    )).filter(e => t.repeated_stations.includes(e));
  }
  if (!estaciones.length) estaciones = t.repeated_stations.slice(0, 12);
  try {
    const data = await (await fetch('/api/series', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ stations: estaciones })
    })).json();
    S.trajectories = data.trajectories || null;
  } catch (e) { S.trajectories = null; }
}

function hoverText(s) {
  const pct = (a, b) => a === null || b === null ? '—' : fmt(a, 2);
  return [
    `<b>${s.station}</b>`,
    s.group,
    s.facies_label ? `<i>${s.facies_label}</i>` : '',
    `TDS ${fmt(s.tds, 0)} mg/L`,
    s.n_exceedances ? `<b>supera ${s.n_exceedances} umbral(es)</b>` : '',
    `Balance ${fmt(s.cbe, 1)} % (${CBE_LABELS[s.cbe_flag] || '—'})`,
    s.imputed.length ? `<i>estimados: ${s.imputed.join(', ')}</i>` : ''
  ].filter(Boolean).join('<br>');
}

function piperAnnotations() {
  const bg = S.data.piper.background;
  const th = THEME();
  const anchor = (ha) => ha === 'left' ? 'left' : ha === 'right' ? 'right' : 'center';
  const yanchor = (va) => va === 'top' ? 'top' : va === 'bottom' ? 'bottom' : 'middle';
  return [
    ...bg.ticks.map(t => ({
      x: t.x, y: t.y, text: t.text, showarrow: false,
      font: { size: 9, color: th.ink3 }, xanchor: anchor(t.ha), yanchor: yanchor(t.va)
    })),
    ...bg.axis_labels.map(t => ({
      x: t.x, y: t.y, text: `<b>${t.text}</b>`, showarrow: false,
      font: { size: 12, color: th.ink }, xanchor: anchor(t.ha), yanchor: yanchor(t.va)
    }))
  ];
}

function drawPiper(divId) {
  const el = document.getElementById(divId);
  if (!el) return;
  const b = S.data.piper.background.bounds;
  const th = THEME();
  const layout = {
    margin: { l: 10, r: 10, t: 10, b: 10 },
    xaxis: { range: [b[0], b[2]], visible: false, fixedrange: false },
    yaxis: { range: [b[1], b[3]], visible: false, scaleanchor: 'x', scaleratio: 1 },
    annotations: piperAnnotations(),
    showlegend: true,
    legend: { x: 0, y: 1, bgcolor: 'rgba(0,0,0,0)', font: { size: 10, color: th.ink2 } },
    paper_bgcolor: th.paper, plot_bgcolor: th.paper,
    hoverlabel: { align: 'left' },
    dragmode: 'lasso'
  };
  const config = { displaylogo: false, responsive: true,
                   modeBarButtonsToRemove: ['autoScale2d', 'toggleSpikelines'] };

  Plotly.react(el, piperTraces(divId), layout, config);

  if (!S.piperDrawn.has(divId)) {
    S.piperDrawn.add(divId);
    el.on('plotly_click', ev => {
      const id = ev.points?.[0]?.customdata;
      if (id) setSelection([id]);
    });
    el.on('plotly_selected', ev => {
      if (!ev || !ev.points) return;
      setSelection(ev.points.map(p => p.customdata).filter(Boolean));
    });
    el.on('plotly_deselect', () => setSelection([]));
  }
}

/* ---------------------------------------------------------------------- Stiff */

function stiffLimit(pool) {
  let limit = 0;
  pool.forEach(s => s.stiff.forEach(([l, r]) => { limit = Math.max(limit, l ?? 0, r ?? 0); }));
  return Math.max(limit * 1.15, 0.5);
}

function stiffPolygon(s, nRows) {
  const left = [], right = [];
  s.stiff.forEach(([l, r], i) => {
    const y = nRows - 1 - i;
    left.push([-(l ?? 0), y]);
    right.push([r ?? 0, y]);
  });
  return left.slice().reverse().concat(right, [left[left.length - 1]]);
}

/* Un panel por grupo, todos con la misma escala: es la figura "Superposed Stiff
   Diagrams by Group" del notebook. La escala comun es lo que permite comparar
   el tamano de un grupo con el de otro. */
function drawStiff() {
  const el = $('#stiff-plot');
  const th = THEME();
  const labels = S.data.stiff.labels;
  const nRows = labels.length;
  const gc = groupColors();

  const porMuestra = S.stiffMode === 'each';
  const pool = S.selection.size ? S.samples.filter(s => S.selection.has(s.id)) : S.samples;
  const limit = stiffLimit(pool);

  let paneles;
  if (porMuestra) {
    paneles = pool.slice(0, 24).map(s => ({ titulo: s.station, muestras: [s] }));
  } else {
    const porGrupo = new Map();
    pool.forEach(s => {
      if (!porGrupo.has(s.group)) porGrupo.set(s.group, []);
      porGrupo.get(s.group).push(s);
    });
    paneles = Array.from(porGrupo, ([g, m]) => ({ titulo: g, muestras: m }));
  }
  if (!paneles.length) { Plotly.purge(el); return; }

  const n = paneles.length;
  const cols = porMuestra ? Math.min(n, 6) : n;
  const filas = Math.ceil(n / cols);
  const traces = [];
  const layout = {
    margin: { l: 84, r: 24, t: 40, b: 46 },
    paper_bgcolor: th.paper, plot_bgcolor: th.paper,
    showlegend: false, hovermode: 'closest', annotations: []
  };

  const anchoCol = 1 / cols, altoFila = 1 / filas;
  const hx = 0.016, hy = 0.10;

  paneles.forEach((panel, k) => {
    const col = k % cols, fila = Math.floor(k / cols);
    const ejeX = k === 0 ? 'xaxis' : 'xaxis' + (k + 1);
    const ejeY = k === 0 ? 'yaxis' : 'yaxis' + (k + 1);
    const refX = k === 0 ? 'x' : 'x' + (k + 1);
    const refY = k === 0 ? 'y' : 'y' + (k + 1);

    const x0 = col * anchoCol + hx, x1 = (col + 1) * anchoCol - hx;
    const y1 = 1 - fila * altoFila - hy * 0.35;
    const y0 = 1 - (fila + 1) * altoFila + hy * 0.65;

    layout[ejeX] = {
      domain: [x0, x1], anchor: refY, range: [-limit, limit],
      zeroline: true, zerolinecolor: th.ink3, zerolinewidth: 1,
      gridcolor: th.grid, tickfont: { size: 9, color: th.ink3 },
      tickformat: '.1f', nticks: 5
    };
    layout[ejeY] = {
      domain: [y0, y1], anchor: refX, range: [-0.55, nRows - 0.45],
      tickmode: 'array',
      tickvals: labels.map((_, i) => nRows - 1 - i),
      // Solo en la primera columna: repetidas en cada panel ocupan mas sitio
      // que los propios diagramas.
      ticktext: col === 0 ? labels.map(pp => pp[0] || '—') : labels.map(() => ''),
      tickfont: { size: 9, color: th.ink2 }, gridcolor: th.grid
    };

    const sufijo = panel.muestras.length > 1 ? ' (' + panel.muestras.length + ')' : '';
    layout.annotations.push({
      x: (x0 + x1) / 2, y: Math.min(y1 + 0.03, 1), xref: 'paper', yref: 'paper',
      text: '<b>' + panel.titulo + '</b>' + sufijo,
      showarrow: false, font: { size: 10.5, color: th.ink },
      xanchor: 'center', yanchor: 'bottom'
    });

    if (col === cols - 1 || porMuestra) {
      labels.forEach((par, i) => {
        if (!par[1]) return;
        layout.annotations.push({
          x: limit, y: nRows - 1 - i, xref: refX, yref: refY,
          text: par[1], showarrow: false, xanchor: 'left', xshift: 4,
          font: { size: 9, color: th.ink2 }
        });
      });
    }

    const varios = panel.muestras.length > 1;
    panel.muestras.forEach(s => {
      const poly = stiffPolygon(s, nRows);
      const color = gc.get(s.group) || '#0e6b75';
      const sel = S.selection.has(s.id);
      traces.push({
        x: poly.map(pt => pt[0]), y: poly.map(pt => pt[1]),
        xaxis: refX, yaxis: refY,
        type: 'scatter', mode: 'lines', fill: 'toself',
        opacity: sel ? 0.9 : (varios ? 0.22 : 0.5),
        line: { color: color, width: sel ? 2.2 : (varios ? 1.1 : 1.6) },
        fillcolor: color, showlegend: false,
        customdata: Array(poly.length).fill(s.id),
        hovertemplate: '<b>' + s.station + '</b><br>' + s.group + '<extra></extra>'
      });
    });
  });

  layout.height = Math.max(el.clientHeight, filas * (porMuestra ? 215 : 330));

  Plotly.react(el, traces, layout, { displaylogo: false, responsive: true });
  el.removeAllListeners?.('plotly_click');
  el.on('plotly_click', ev => {
    const id = ev.points?.[0]?.customdata;
    if (id) setSelection([id]);
  });
}

/* ------------------------------------------------------------------ temporal */

async function fetchSeries(station) {
  const res = await fetch('/api/series', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ stations: [station] })
  });
  if (!res.ok) throw new Error((await res.json()).detail || 'Error');
  return res.json();
}

function temporalEmptyState() {
  const t = S.data.temporal;
  $('#temporal-note').textContent = t.message;
  $('#temporal-body').innerHTML =
    '<div class="empty" style="padding:44px 24px;max-width:600px;margin:0 auto">' +
    '<p style="font-size:14px;color:var(--ink-2)">' + t.message + '</p>' +
    '<p style="margin-top:16px">Para que esta pantalla funcione, tu archivo necesita:</p>' +
    '<ul style="text-align:left;display:inline-block;margin-top:4px">' +
    '<li>una columna de <b>fecha</b> (vale <code>Fecha</code>, <code>Sampled_Date</code>, <code>Date</code>...)</li>' +
    '<li>la <b>misma estacion</b> medida en <b>dos o mas</b> fechas distintas</li>' +
    '</ul>' +
    '<p style="margin-top:20px"><button class="btn" id="btn-demo-3">Ver la demo sintetica con 8 campanas</button></p>' +
    '</div>';
  const b = $('#btn-demo-3');
  if (b) b.addEventListener('click', loadDemoCampaigns);
}

function drawTemporal() {
  const t = S.data.temporal;
  if (!t.has_dates || !t.can_plot_series) { temporalEmptyState(); return; }

  const sel = $('#sel-station');
  if (sel.dataset.filled !== S.data.source) {
    sel.innerHTML = t.repeated_stations
      .map(e => '<option value="' + e + '">' + e + '</option>').join('');
    sel.dataset.filled = S.data.source;
  }
  const estacion = sel.value || t.repeated_stations[0];
  $('#temporal-note').textContent = t.message + ' Mostrando ' + estacion + '.' +
    (t.can_discuss_trend ? ''
      : ' Con menos de ' + t.min_campaigns_for_trend + ' campanas, lee la evolucion con cautela.');

  if (!$('#temporal-plot')) {
    $('#temporal-body').innerHTML = '<div class="plot" id="temporal-plot"></div>';
  }

  fetchSeries(estacion)
    .then(data => renderTemporal(data, estacion))
    .catch(e => toast(e.message, true));
}

function renderTemporal(data, estacion) {
  const th = THEME();
  const modo = $('#sel-temporal-mode').value;
  const el = $('#temporal-plot');
  if (!el) return;
  if (modo === 'vertices') return renderVertexPanels(el, data, estacion, th);
  if (modo === 'stiff') return renderStiffSeries(el, data, estacion, th);
  return renderParamSeries(el, data, estacion, th);
}

/* Un panel por vertice del Piper: las "esquinas" del diagrama en el tiempo. */
function renderVertexPanels(el, data, estacion, th) {
  const orden = ['pct_cat_left', 'pct_cat_right', 'pct_cat_apex',
                 'pct_an_left', 'pct_an_right', 'pct_an_apex'];
  const cols = 3, filas = 2;
  const traces = [];
  const layout = {
    margin: { l: 54, r: 18, t: 52, b: 46 },
    paper_bgcolor: th.paper, plot_bgcolor: th.paper,
    showlegend: false, hovermode: 'x unified', annotations: []
  };
  const cambios = new Map(data.changes.map(c => [c.vertex, c]));

  orden.forEach((v, k) => {
    const puntos = data.vertices.filter(r => r.vertex === v);
    if (!puntos.length) return;
    const col = k % cols, fila = Math.floor(k / cols);
    const refX = k === 0 ? 'x' : 'x' + (k + 1), refY = k === 0 ? 'y' : 'y' + (k + 1);
    const ejeX = k === 0 ? 'xaxis' : 'xaxis' + (k + 1);
    const ejeY = k === 0 ? 'yaxis' : 'yaxis' + (k + 1);
    const x0 = col / cols + 0.045, x1 = (col + 1) / cols - 0.018;
    const y1 = 1 - fila / filas - 0.09, y0 = 1 - (fila + 1) / filas + 0.09;

    const esCation = v.indexOf('cat') >= 0;
    const color = esCation ? '#0e6b75' : '#b5651d';
    const c = cambios.get(v);
    const delta = c ? c.delta_pp : null;

    layout[ejeX] = { domain: [x0, x1], anchor: refY, type: 'date',
                     tickfont: { size: 9, color: th.ink3 }, gridcolor: th.grid, nticks: 4 };
    layout[ejeY] = { domain: [y0, y1], anchor: refX, ticksuffix: ' %',
                     tickfont: { size: 9, color: th.ink3 }, gridcolor: th.grid, nticks: 4 };

    let signo = '';
    if (delta !== null) {
      const flecha = delta > 0.5 ? ' ▲' : (delta < -0.5 ? ' ▼' : ' ▬');
      const col2 = delta > 0 ? '#b5651d' : '#0e6b75';
      signo = '  <span style="color:' + col2 + '">' +
              (delta > 0 ? '+' : '') + delta.toFixed(1) + ' pp' + flecha + '</span>';
    }
    layout.annotations.push({
      x: (x0 + x1) / 2, y: y1 + 0.012, xref: 'paper', yref: 'paper',
      text: '<b>' + puntos[0].label + '</b>' + signo, showarrow: false,
      font: { size: 10.5, color: th.ink }, xanchor: 'center', yanchor: 'bottom'
    });

    traces.push({
      x: puntos.map(r => r.sampled_at), y: puntos.map(r => r.pct),
      xaxis: refX, yaxis: refY, type: 'scatter', mode: 'lines+markers',
      line: { color: color, width: 2 }, marker: { size: 6, color: color },
      hovertemplate: '%{y:.1f} %<extra></extra>', name: puntos[0].label
    });
  });

  layout.annotations.push({
    x: 0, y: 1.045, xref: 'paper', yref: 'paper', xanchor: 'left',
    text: 'Estacion <b>' + estacion + '</b> · cationes en verde, aniones en ambar ' +
          '· pp = puntos porcentuales entre la primera y la ultima campana',
    showarrow: false, font: { size: 10, color: th.ink3 }
  });
  layout.height = Math.max(el.clientHeight, 440);
  Plotly.react(el, traces, layout, { displaylogo: false, responsive: true });
}

function renderStiffSeries(el, data, estacion, th) {
  const colores = ['#0e6b75', '#b5651d', '#3f6386', '#8a2f43', '#4c7a3f', '#6b5b95', '#a2322c'];
  const traces = [];
  (data.stiff || []).forEach(() => {});
  const porSerie = new Map();
  (data.stiff || []).forEach(r => {
    const clave = r.row + '|' + r.side;
    if (!porSerie.has(clave)) porSerie.set(clave, { label: r.label, puntos: [] });
    porSerie.get(clave).puntos.push(r);
  });
  let i = 0;
  porSerie.forEach(serie => {
    if (!serie.label) return;
    traces.push({
      x: serie.puntos.map(r => r.sampled_at), y: serie.puntos.map(r => r.meq),
      type: 'scatter', mode: 'lines+markers', name: serie.label,
      line: { color: colores[i % colores.length], width: 2 }, marker: { size: 5 }
    });
    i++;
  });
  Plotly.react(el, traces, {
    margin: { l: 62, r: 20, t: 44, b: 46 },
    paper_bgcolor: th.paper, plot_bgcolor: th.paper,
    xaxis: { type: 'date', gridcolor: th.grid, tickfont: { size: 10, color: th.ink3 } },
    yaxis: { title: { text: 'meq/L', font: { size: 11, color: th.ink3 } },
             gridcolor: th.grid, tickfont: { size: 10, color: th.ink3 } },
    legend: { font: { size: 10, color: th.ink2 }, orientation: 'h', y: 1.12 },
    hovermode: 'x unified', height: Math.max(el.clientHeight, 420)
  }, { displaylogo: false, responsive: true });
}

function renderParamSeries(el, data, estacion, th) {
  const etiquetas = data.parameter_labels || {};
  const porParam = new Map();
  data.parameters.forEach(r => {
    if (!porParam.has(r.parameter)) porParam.set(r.parameter, []);
    porParam.get(r.parameter).push(r);
  });
  const nombres = Array.from(porParam.keys());
  if (!nombres.length) { Plotly.purge(el); return; }
  const cols = Math.min(3, nombres.length);
  const filas = Math.ceil(nombres.length / cols);
  const traces = [];
  const layout = {
    margin: { l: 60, r: 18, t: 44, b: 46 },
    paper_bgcolor: th.paper, plot_bgcolor: th.paper,
    showlegend: false, hovermode: 'x unified', annotations: []
  };
  nombres.forEach((nombre, k) => {
    const puntos = porParam.get(nombre);
    const col = k % cols, fila = Math.floor(k / cols);
    const refX = k === 0 ? 'x' : 'x' + (k + 1), refY = k === 0 ? 'y' : 'y' + (k + 1);
    const ejeX = k === 0 ? 'xaxis' : 'xaxis' + (k + 1);
    const ejeY = k === 0 ? 'yaxis' : 'yaxis' + (k + 1);
    const x0 = col / cols + 0.05, x1 = (col + 1) / cols - 0.018;
    const y1 = 1 - fila / filas - 0.085, y0 = 1 - (fila + 1) / filas + 0.095;
    layout[ejeX] = { domain: [x0, x1], anchor: refY, type: 'date',
                     tickfont: { size: 9, color: th.ink3 }, gridcolor: th.grid, nticks: 4 };
    layout[ejeY] = { domain: [y0, y1], anchor: refX,
                     tickfont: { size: 9, color: th.ink3 }, gridcolor: th.grid, nticks: 4 };
    layout.annotations.push({
      x: (x0 + x1) / 2, y: y1 + 0.012, xref: 'paper', yref: 'paper',
      text: '<b>' + (etiquetas[nombre] || nombre) + '</b>', showarrow: false,
      font: { size: 10.5, color: th.ink }, xanchor: 'center', yanchor: 'bottom'
    });
    traces.push({
      x: puntos.map(r => r.sampled_at), y: puntos.map(r => r.value),
      xaxis: refX, yaxis: refY, type: 'scatter', mode: 'lines+markers',
      line: { color: '#3f6386', width: 2 }, marker: { size: 5, color: '#3f6386' }
    });
  });
  layout.annotations.push({
    x: 0, y: 1.045, xref: 'paper', yref: 'paper', xanchor: 'left',
    text: 'Estacion <b>' + estacion + '</b>', showarrow: false,
    font: { size: 10, color: th.ink3 }
  });
  layout.height = Math.max(el.clientHeight, 420);
  Plotly.react(el, traces, layout, { displaylogo: false, responsive: true });
}

/* ----------------------------------------------------------------------- mapa */

function ensureMap(containerId) {
  if (S.maps[containerId]) { setTimeout(() => S.maps[containerId].invalidateSize(), 60); return; }
  const map = L.map(containerId, { zoomControl: true, attributionControl: true });
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    maxZoom: 19,
    attribution: '&copy; OpenStreetMap'
  }).addTo(map);
  map.setView([0, 0], 2);
  S.maps[containerId] = map;
  S.markers[containerId] = new Map();
  setTimeout(() => map.invalidateSize(), 80);
}

function paintMarkers(containerId, mode) {
  const map = S.maps[containerId];
  if (!map) return;
  const store = S.markers[containerId];
  store.forEach(m => map.removeLayer(m));
  store.clear();

  const pts = S.samples.filter(s => s.lon !== null && s.lat !== null);
  if (!pts.length) return;

  pts.forEach(s => {
    const sel = S.selection.has(s.id);
    const dim = S.selection.size > 0 && !sel;
    const marker = L.circleMarker([s.lat, s.lon], {
      radius: sel ? 9 : 5.5,
      color: sel ? (isDark() ? '#e6eef0' : '#12232a') : 'rgba(0,0,0,.35)',
      weight: sel ? 2 : 1,
      fillColor: colorFor(s, mode),
      fillOpacity: dim ? 0.25 : 0.9,
      opacity: dim ? 0.3 : 1
    });
    marker.bindTooltip(`<b>${s.station}</b><br>${s.group}`, { direction: 'top' });
    marker.on('click', () => setSelection([s.id]));
    marker.addTo(map);
    store.set(s.id, marker);
  });

  // Encuadrar solo cuando el contenedor ya tiene alto: si se hace con alto 0,
  // Leaflet calcula un zoom absurdo y el mapa queda inutilizable.
  const sized = map.getSize().y > 0;
  if (sized && !map._fittedOnce) {
    map.invalidateSize();
    map.fitBounds(L.latLngBounds(pts.map(s => [s.lat, s.lon])), { padding: [30, 30] });
    map._fittedOnce = true;
  }
  if (containerId === 'map') renderLegend(mode);
}

function renderLegend(mode) {
  $('#map-legend').innerHTML = legendEntries(mode)
    .map(e => `<div><i style="background:${e.color}"></i>${e.label}</div>`).join('');
}

/* ------------------------------------------------------------------ seleccion */

function setSelection(ids) {
  S.selection = new Set(ids);
  renderStatus();
  // todas las vistas leen del mismo estado
  if (S.piperDrawn.has('piper-plot')) drawPiper('piper-plot');
  if (S.piperDrawn.has('piper-plot2')) drawPiper('piper-plot2');
  if (S.view === 'stiff') drawStiff();
  if (S.view === 'durov') drawDurov();
  if (S.view === 'norm') drawNorm();
  Object.keys(S.maps).forEach(k => paintMarkers(k, S.mapColorBy));
  markTableRows();
  renderDetail();

  // llevar el mapa al punto elegido desde el Piper
  if (ids.length === 1) {
    const s = S.byId.get(ids[0]);
    if (s && s.lon !== null && s.lat !== null) {
      Object.values(S.maps).forEach(m => m.panTo([s.lat, s.lon], { animate: true }));
    }
  }
}

function markTableRows() {
  $$('#data-table tbody tr, #cross-table tbody tr').forEach(tr => {
    tr.setAttribute('aria-selected', String(S.selection.has(tr.dataset.id)));
  });
  const first = $(`#cross-table tbody tr[aria-selected="true"]`);
  if (first) first.scrollIntoView({ block: 'nearest' });
  $('#cross-count').textContent = S.selection.size
    ? `· ${S.selection.size} seleccionada(s)` : '';
}

/* -------------------------------------------------------------------- tablas */

function renderTable(sel, rows) {
  const ions = S.data.measured_ions;
  const labels = S.data.ion_labels;
  const head = `<thead><tr>
    <th>Estacion</th><th>Grupo</th><th>Facies</th>
    ${ions.map(i => `<th style="text-align:right">${labels[i]}<br><span style="font-weight:400;text-transform:none">mg/L</span></th>`).join('')}
    <th style="text-align:right">TDS</th>
    <th style="text-align:right">Balance %</th>
    <th>Estado</th>
    <th style="text-align:right">Alcalinidad</th>
  </tr></thead>`;
  const body = rows.map(s => `<tr data-id="${s.id}">
    <td>${s.station}</td><td>${s.group}</td>
    <td>${s.facies_label || '—'}</td>
    ${ions.map(i => `<td class="num${s.imputed.includes(i) ? ' imp' : ''}">${fmt(s.mgl[i], 2)}</td>`).join('')}
    <td class="num">${fmt(s.tds, 0)}</td>
    <td class="num">${fmt(s.cbe, 2)}</td>
    <td><span class="tag ${s.cbe_flag === 'acceptable' ? 'ok' : s.cbe_flag === 'marginal' ? 'warn' : s.cbe_flag === 'rejected' ? 'err' : 'info'}">${CBE_LABELS[s.cbe_flag] || '—'}</span></td>
    <td class="num">${fmt(s.alkalinity, 1)}</td>
  </tr>`).join('');
  const table = $(sel);
  table.innerHTML = head + `<tbody>${body}</tbody>`;
  table.querySelectorAll('tbody tr').forEach(tr => {
    tr.addEventListener('click', () => setSelection([tr.dataset.id]));
  });
}

/* ---------------------------------------------------------------------- ficha */

function detailHtml(s) {
  const ions = S.data.measured_ions;
  const labels = S.data.ion_labels;
  const flag = s.cbe_flag === 'acceptable' ? 'ok' : s.cbe_flag === 'marginal' ? 'warn' : s.cbe_flag === 'rejected' ? 'err' : 'info';
  return `<div class="detail">
    <h3>${s.station}</h3>
    <div class="sub">${s.group}${s.sampled_at ? ' · ' + String(s.sampled_at).slice(0, 10) : ''}</div>
    ${s.facies_label ? `<p style="margin:0 0 10px"><span class="tag info">${s.facies_label}</span>
      ${s.n_exceedances ? `<span class="tag ${s.exceeds_health ? 'err' : 'warn'}">supera ${s.n_exceedances} umbral(es)</span>` : ''}</p>` : ''}
    <dl class="kv">
      <dt>TDS</dt><dd>${fmt(s.tds, 0)} mg/L</dd>
      <dt>Balance</dt><dd>${fmt(s.cbe, 2)} % <span class="tag ${flag}">${CBE_LABELS[s.cbe_flag] || '—'}</span></dd>
      <dt>Alcalinidad</dt><dd>${fmt(s.alkalinity, 1)} mg/L CaCO₃</dd>
      <dt>Σ cationes</dt><dd>${fmt(s.sum_cat, 3)} meq/L</dd>
      <dt>Σ aniones</dt><dd>${fmt(s.sum_an, 3)} meq/L</dd>
      ${s.ph !== null ? `<dt>pH</dt><dd>${fmt(s.ph, 2)}</dd>` : ''}
      ${s.lon !== null ? `<dt>Coords</dt><dd>${fmt(s.lat, 5)}, ${fmt(s.lon, 5)}</dd>` : ''}
    </dl>
    <table>
      <thead><tr><th>Ion</th><th style="text-align:right">mg/L</th><th style="text-align:right">meq/L</th></tr></thead>
      <tbody>${ions.map(i => `<tr><td>${labels[i]}</td>
        <td class="num${s.imputed.includes(i) ? ' imp' : ''}">${fmt(s.mgl[i], 2)}</td>
        <td class="num">${fmt(s.meq[i], 3)}</td></tr>`).join('')}</tbody>
    </table>
    ${s.imputed.length ? `<p style="font-size:11.5px;color:var(--warn);margin-top:8px">
      En cursiva, valores estimados (no medidos): ${s.imputed.join(', ')}.</p>` : ''}
  </div>`;
}

function renderDetail() {
  const targets = ['#detail-data', '#detail-piper', '#detail-map', '#detail-durov'];
  if (S.selection.size === 1) {
    const s = S.byId.get(Array.from(S.selection)[0]);
    targets.forEach(t => { const el = $(t); if (el) el.innerHTML = detailHtml(s); });
  } else if (S.selection.size > 1) {
    const html = `<div class="empty">${S.selection.size} muestras seleccionadas.<br>
      Elige una sola para ver su ficha completa.</div>`;
    targets.forEach(t => { const el = $(t); if (el) el.innerHTML = html; });
  } else {
    $('#detail-data').innerHTML = '<div class="empty">Elige una fila de la tabla.</div>';
    $('#detail-piper').innerHTML = '<div class="empty">Pasa el raton o haz clic sobre un punto.</div>';
    $('#detail-map').innerHTML = '<div class="empty">Haz clic en un punto del mapa.</div>';
    const dd = $('#detail-durov');
    if (dd) dd.innerHTML = '<div class="empty">Haz clic sobre un punto.</div>';
  }
}

/* ----------------------------------------------------------------- validacion */

function renderValidation() {
  const r = S.data.report;
  const sevClass = { error: 'error', warning: 'warning', info: 'info' };
  const sevName = { error: 'Error', warning: 'Aviso', info: 'Nota' };
  const issues = r.issues.map(i => `
    <div class="issue ${sevClass[i.severity]}">
      <h4>${sevName[i.severity]}${i.field ? ` · ${i.field}` : ''}${i.n_rows ? ` · ${i.n_rows} muestra(s)` : ''}</h4>
      <p>${i.message}</p>
      ${i.hint ? `<p class="hint">${i.hint}</p>` : ''}
      ${i.n_rows && i.n_rows <= 400 ? `<p class="hint"><a href="#" data-rows="${i.rows.join(',')}">Ver esas muestras</a></p>` : ''}
    </div>`).join('');

  const stats = r.column_stats.filter(c => c.n_numeric > 0);
  $('#validation-body').innerHTML = `
    <p style="margin-top:0"><b>${S.data.summary}</b></p>
    ${demoBanner()}
    ${zeroPolicyBanner()}
    ${r.notes.length ? `<div class="banner info" style="border-radius:3px;margin-bottom:12px">${r.notes.join('<br>')}</div>` : ''}
    ${issues || '<p>Sin hallazgos.</p>'}
    <h4 style="margin:20px 0 8px;font-size:12px;letter-spacing:.08em;text-transform:uppercase;color:var(--ink-3)">Resumen por columna</h4>
    <table><thead><tr><th>Columna</th><th style="text-align:right">Con dato</th>
      <th style="text-align:right">Vacias</th><th style="text-align:right">Min</th>
      <th style="text-align:right">Mediana</th><th style="text-align:right">Max</th></tr></thead>
      <tbody>${stats.map(c => `<tr style="cursor:default"><td>${c.column}</td>
        <td class="num">${c.n_present}</td><td class="num">${c.n_missing}</td>
        <td class="num">${fmt(c.min, 2)}</td><td class="num">${fmt(c.median, 2)}</td>
        <td class="num">${fmt(c.max, 2)}</td></tr>`).join('')}</tbody></table>`;

  const toggle = $('#zero-toggle');
  if (toggle) {
    toggle.addEventListener('click', ev => {
      ev.preventDefault();
      const activo = S.data.zeros_as_missing_for.length > 0;
      setZeroPolicy(activo ? [] : S.data.suspicious_zero_ions);
    });
  }

  $('#validation-body').querySelectorAll('a[data-rows]').forEach(a => {
    a.addEventListener('click', ev => {
      ev.preventDefault();
      const rows = a.dataset.rows.split(',').filter(Boolean).map(Number);
      setSelection(rows.map(r => `s${r}`).filter(id => S.byId.has(id)));
      showView('data');
    });
  });
}

function demoBanner() {
  if (!S.data.is_synthetic_demo) return '';
  return '<div class="banner" style="border-radius:3px;margin-bottom:12px">' +
    '<b>Datos sinteticos.</b> Este archivo se genero para poder ensenar el modulo ' +
    'temporal: las concentraciones parten de estaciones reales y se les aplico una ' +
    'deriva inventada. No sirve para sacar ninguna conclusion hidroquimica.</div>';
}

function zeroPolicyBanner() {
  const detectados = S.data.suspicious_zero_ions || [];
  if (!detectados.length) return '';
  const activos = S.data.zeros_as_missing_for || [];
  const nombres = detectados.map(i => S.data.ion_labels[i] || i).join(', ');
  if (activos.length) {
    return `<div class="banner info" style="border-radius:3px;margin-bottom:12px">
      <b>Ajuste activo:</b> los valores de ${nombres} que venian como 0,00 exacto se
      estan tratando como <b>no medidos</b>, no como ausencia real en el agua.
      Se excluyen de las medias y de los recuentos de excedencia.
      <a href="#" id="zero-toggle">Usarlos como cero real</a>.</div>`;
  }
  return `<div class="banner" style="border-radius:3px;margin-bottom:12px">
    <b>Ajuste desactivado:</b> los 0,00 de ${nombres} se estan contando como medidas
    reales, lo que rebaja las medias y el porcentaje de excedencias.
    <a href="#" id="zero-toggle">Tratarlos como no medidos</a>.</div>`;
}

/* ------------------------------------------------------------------ exportar */

/* ------------------------------------------------------------------- Durov */

function drawDurov() {
  const el = $('#durov-plot');
  const d = S.data.durov;
  const th = THEME();
  const modo = S.durovColorBy || $('#sel-durovcolor').value;

  const traces = [];
  const gx = [], gy = [];
  d.gridlines.forEach(([x0, y0, x1, y1]) => { gx.push(x0, x1, null); gy.push(y0, y1, null); });
  traces.push({ x: gx, y: gy, mode: 'lines', type: 'scatter', hoverinfo: 'skip',
                showlegend: false, line: { color: th.grid, width: 0.7 } });
  d.outlines.forEach(poly => {
    traces.push({ x: poly.map(p => p[0]), y: poly.map(p => p[1]), mode: 'lines',
                  type: 'scatter', hoverinfo: 'skip', showlegend: false,
                  line: { color: th.edge, width: 1.3 } });
  });

  const colores = S.samples.map(s => colorFor(s, modo));
  const tamanos = S.samples.map(s => S.selection.has(s.id) ? 14 : 7.5);
  const opac = S.samples.map(s => (S.selection.size === 0 || S.selection.has(s.id)) ? 0.95 : 0.18);
  const ids = S.samples.map(s => s.id);
  const texto = S.samples.map(s => hoverText(s));

  const comun = {
    type: 'scattergl', mode: 'markers', showlegend: false,
    customdata: ids, text: texto, hovertemplate: '%{text}<extra></extra>',
    marker: { color: colores, size: tamanos, opacity: opac,
              line: { color: isDark() ? '#0c1418' : '#ffffff', width: 0.6 } }
  };
  traces.push({ ...comun, x: d.square.map(p => p[0]), y: d.square.map(p => p[1]) });
  traces.push({ ...comun, x: d.cation.map(p => p[0]), y: d.cation.map(p => p[1]),
                marker: { ...comun.marker, size: tamanos.map(v => v * 0.75) } });
  traces.push({ ...comun, x: d.anion.map(p => p[0]), y: d.anion.map(p => p[1]),
                marker: { ...comun.marker, size: tamanos.map(v => v * 0.75) } });

  ['ph', 'tds'].forEach(clave => {
    const panel = d[clave];
    if (!panel.available) return;
    traces.push({ ...comun, x: panel.x, y: panel.y,
                  marker: { ...comun.marker, size: tamanos.map(v => v * 0.8) } });
  });

  const anotaciones = [
    ...d.tick_labels.map(t => ({
      x: t.x, y: t.y, text: t.text, showarrow: false,
      font: { size: 8.5, color: th.ink3 }, xanchor: anchorX(t.ha), yanchor: anchorY(t.va)
    })),
    ...d.axis_labels.map(t => ({
      x: t.x, y: t.y, text: `<b>${t.text}</b>`, showarrow: false,
      font: { size: 11, color: th.ink }, xanchor: anchorX(t.ha), yanchor: anchorY(t.va)
    }))
  ];

  const avisos = ['ph', 'tds'].filter(k => !d[k].available)
    .map(k => d[k].reason).join(' ');
  $('#durov-note').textContent = avisos
    ? avisos
    : `Cuadrado central: x = ${d.axis_titles.x} · y = ${d.axis_titles.y}`;

  const b = d.bounds;
  Plotly.react(el, traces, {
    margin: { l: 12, r: 12, t: 12, b: 12 },
    xaxis: { range: [b[0], b[2]], visible: false },
    yaxis: { range: [b[1], b[3]], visible: false, scaleanchor: 'x', scaleratio: 1 },
    annotations: anotaciones,
    paper_bgcolor: th.paper, plot_bgcolor: th.paper,
    showlegend: false, hoverlabel: { align: 'left' }, dragmode: 'lasso'
  }, { displaylogo: false, responsive: true });

  if (!S.durovDrawn) {
    S.durovDrawn = true;
    el.on('plotly_click', ev => {
      const id = ev.points?.[0]?.customdata;
      if (id) setSelection([id]);
    });
    el.on('plotly_selected', ev => {
      if (ev?.points) setSelection(ev.points.map(p => p.customdata).filter(Boolean));
    });
  }
}

function anchorX(ha) { return ha === 'left' ? 'left' : ha === 'right' ? 'right' : 'center'; }
function anchorY(va) { return va === 'top' ? 'top' : va === 'bottom' ? 'bottom' : 'middle'; }

/* --------------------------------------------------------------- normativa */

function drawNorm() {
  const std = S.data.standard;
  const sel = $('#sel-standard');
  if (sel.value !== (std.key || '')) sel.value = std.key || '';

  $('#norm-note').textContent = std.verified
    ? std.source
    : '⚠ ' + std.source;

  if (!std.rows.length) {
    $('#norm-body').innerHTML =
      '<div class="empty">Ningún parámetro de esta norma está medido en tus datos.</div>';
    return;
  }

  const tarjetas = std.rows.map(r => {
    const clase = r.n_exceeding === 0 ? 'ok' : (r.kind === 'health' ? 'bad' : 'warn');
    return `<div class="norm-card ${clase}">
      <h4>${r.label}</h4>
      <div class="big">${r.n_exceeding}<span class="sub"> / ${r.n_measured}</span></div>
      <div class="sub">${fmt(r.pct, 1)} % de las medidas</div>
      <div class="lim">Límite ${r.range_text} · ${r.kind_label}</div>
      <div class="lim">Observado ${fmt(r.min_observed, 2)} – ${fmt(r.max_observed, 2)} ${r.unit}</div>
      ${r.n_missing ? `<div class="lim" style="color:var(--ink-3)">${r.n_missing} sin medir</div>` : ''}
    </div>`;
  }).join('');

  // selector de parámetro para el detalle
  const psel = $('#sel-normparam');
  if (psel.dataset.filled !== std.key) {
    psel.innerHTML = std.rows.map(r =>
      `<option value="${r.parameter}">${r.label}</option>`).join('');
    psel.dataset.filled = std.key;
  }
  const param = psel.value || std.rows[0].parameter;
  const row = std.rows.find(r => r.parameter === param) || std.rows[0];

  const ion = param.replace('_mgL', '');
  const valorDe = s => (s.mgl && s.mgl[ion] !== undefined) ? s.mgl[ion] : s[
    { tds_mgl: 'tds', ph: 'ph', temp_c: 'temp' }[param] || param];

  const medidas = S.samples.filter(s => valorDe(s) !== null && valorDe(s) !== undefined);
  const incumplen = medidas.filter(s => {
    const v = valorDe(s);
    return (row.maximum !== null && v > row.maximum) ||
           (row.minimum !== null && v < row.minimum);
  }).sort((a, b) => valorDe(b) - valorDe(a));

  const filas = incumplen.map(s => `<tr data-id="${s.id}">
    <td>${s.station}</td><td>${s.group}</td>
    <td>${s.facies_label || '—'}</td>
    <td class="num" style="color:var(--err);font-weight:600">${fmt(valorDe(s), 2)}</td>
    <td class="num">${fmt(valorDe(s) / (row.maximum || 1), 2)}×</td>
  </tr>`).join('');

  $('#norm-body').innerHTML = `
    <div class="norm-grid">${tarjetas}</div>
    <h4 style="margin:6px 0 8px;font-size:12px;letter-spacing:.08em;text-transform:uppercase;color:var(--ink-3)">
      ${row.label}: muestras que superan el límite (${incumplen.length} de ${medidas.length} medidas)
    </h4>
    ${incumplen.length ? `<table><thead><tr>
        <th>Estación</th><th>Grupo</th><th>Facies</th>
        <th style="text-align:right">${row.unit}</th>
        <th style="text-align:right">Veces el límite</th>
      </tr></thead><tbody>${filas}</tbody></table>`
      : '<p style="color:var(--ok)">Ninguna muestra supera este límite.</p>'}
    <p class="hint" style="color:var(--ink-3);font-size:11.5px;margin-top:12px">
      El denominador son las muestras <b>con medida</b> (${medidas.length}), no el total
      (${S.data.n_samples}). Contar las no medidas como cumplidoras rebaja el porcentaje
      y es el error más habitual.</p>`;

  $('#norm-body').querySelectorAll('tbody tr').forEach(tr => {
    tr.addEventListener('click', () => { setSelection([tr.dataset.id]); showView('map'); });
  });
}

/* ------------------------------------------------------- mapeo de columnas */

async function openMapping() {
  try {
    const m = await (await fetch('/api/mapping')).json();
    S.mappingData = m;
    const opciones = ['<option value="">— sin asignar —</option>']
      .concat(m.source_columns.map(c => `<option value="${c}">${c}</option>`)).join('');
    const filas = m.rows.map(r => `<tr data-required="${r.obligatorio}">
      <td>${r.etiqueta}<br><span style="color:var(--ink-3);font-size:11px">${r.campo}${r.unidad ? ' · ' + r.unidad : ''}</span></td>
      <td>${r.tipo}</td>
      <td><select data-field="${r.campo}">${opciones}</select></td>
    </tr>`).join('');
    $('#mapping-table').innerHTML = `<thead><tr>
      <th>Campo</th><th>Tipo</th><th>Columna de tu archivo</th></tr></thead><tbody>${filas}</tbody>`;
    // preseleccionar lo detectado
    Object.entries(m.mapping).forEach(([campo, col]) => {
      const s = $(`#mapping-table select[data-field="${campo}"]`);
      if (s) s.value = col;
    });
    $('#mapping-note').innerHTML =
      `Se reconocieron <b>${Object.keys(m.mapping).length}</b> de ${m.rows.length} campos. ` +
      (m.unmatched.length
        ? `Sin asignar en tu archivo: ${m.unmatched.map(c => `<code>${c}</code>`).join(', ')}.`
        : 'Todas las columnas de tu archivo se reconocieron.') +
      ' Los campos con * son obligatorios.';
    $('#mapping-sheet').hidden = false;
  } catch (e) { toast(e.message, true); }
}

async function applyMapping() {
  const mapping = {};
  $$('#mapping-table select').forEach(s => {
    if (s.value) mapping[s.dataset.field] = s.value;
  });
  busy(true);
  try {
    const res = await fetch('/api/mapping', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(Object.assign({ mapping }, currentOptions()))
    });
    if (!res.ok) throw new Error((await res.json()).detail);
    adopt(await res.json());
    $('#mapping-sheet').hidden = true;
    toast('Mapeo aplicado.');
  } catch (e) { toast(e.message, true); }
  finally { busy(false); }
}

/* -------------------------------------------------------------- exportacion */

function renderExport() {
  const geo = S.data.has_coordinates;
  const sinCoords = '<p style="color:var(--ink-3);font-size:12px">Necesita coordenadas y tus datos no las traen.</p>';
  $('#export-body').innerHTML = `
    <p style="margin-top:0">Todo lo calculado: meq/L, balance de carga, alcalinidad,
       facies y las coordenadas de cada muestra en los diagramas.</p>

    <h4 style="margin:18px 0 6px;font-size:12px;letter-spacing:.08em;text-transform:uppercase;color:var(--ink-3)">Tablas</h4>
    <div class="controls">
      <a class="btn primary" href="/api/export/xlsx" download>Excel (.xlsx)</a>
      <a class="btn" href="/api/export/csv" download>CSV</a>
    </div>
    <p style="color:var(--ink-3);font-size:12px;margin-top:6px">El Excel trae una hoja
       por bloque: resultados, facies, umbrales, validación y pesos equivalentes.</p>

    <h4 style="margin:20px 0 6px;font-size:12px;letter-spacing:.08em;text-transform:uppercase;color:var(--ink-3)">Google Earth y SIG</h4>
    ${geo ? `<div class="controls">
      <a class="btn primary" href="/api/export/kmz?colour_by=facies" download>KMZ con diagramas de Stiff</a>
      <a class="btn" href="/api/export/kml?colour_by=facies" download>KML ligero</a>
      <a class="btn" href="/api/export/geojson" download>GeoJSON</a>
    </div>
    <p style="color:var(--ink-3);font-size:12px;margin-top:6px">
      En el <b>KMZ</b> el icono de cada punto es su propio diagrama de Stiff, agrupado
      por grupo y con la ficha completa en el globo. Son ${S.data.n_samples} imágenes,
      así que tarda unos segundos. El <b>KML</b> pesa mil veces menos pero lleva
      círculos de color en vez de diagramas. El <b>GeoJSON</b> es el que abre QGIS.</p>`
      : sinCoords}

    <h4 style="margin:20px 0 6px;font-size:12px;letter-spacing:.08em;text-transform:uppercase;color:var(--ink-3)">Todavía no disponible</h4>
    <p style="color:var(--ink-3)">Informe en PDF y guardado de proyectos.</p>`;
}

/* -------------------------------------------------------------------- eventos */

function wire() {
  $('#rail').addEventListener('click', ev => {
    const b = ev.target.closest('button');
    if (b && !b.disabled) showView(b.dataset.view);
  });

  const pick = () => $('#file-input').click();
  $('#btn-open').addEventListener('click', pick);
  $('#btn-open-2').addEventListener('click', pick);
  $('#file-input').addEventListener('change', ev => {
    if (ev.target.files[0]) uploadFile(ev.target.files[0]);
    ev.target.value = '';
  });
  $('#btn-example').addEventListener('click', loadExample);
  $('#btn-example-2').addEventListener('click', loadExample);
  $('#btn-demo').addEventListener('click', loadDemoCampaigns);
  $('#btn-demo-2').addEventListener('click', loadDemoCampaigns);

  const drop = $('#drop');
  ['dragenter', 'dragover'].forEach(e =>
    drop.addEventListener(e, ev => { ev.preventDefault(); drop.classList.add('over'); }));
  ['dragleave', 'drop'].forEach(e =>
    drop.addEventListener(e, ev => { ev.preventDefault(); drop.classList.remove('over'); }));
  drop.addEventListener('drop', ev => {
    const f = ev.dataTransfer.files[0];
    if (f) uploadFile(f);
  });

  $('#sel-convention').addEventListener('change', reanalyse);
  $('#sel-facies').addEventListener('change', reanalyse);
  $('#sel-standard').addEventListener('change', reanalyse);
  $('#sel-crs').addEventListener('change', reanalyse);
  $('#sel-normparam').addEventListener('change', drawNorm);
  $('#sel-durovcolor').addEventListener('change', ev => {
    S.durovColorBy = ev.target.value; drawDurov();
  });
  $('#btn-mapping').addEventListener('click', openMapping);
  $('#mapping-close').addEventListener('click', () => { $('#mapping-sheet').hidden = true; });
  $('#mapping-apply').addEventListener('click', applyMapping);
  $('#mapping-sheet').addEventListener('click', ev => {
    if (ev.target.id === 'mapping-sheet') $('#mapping-sheet').hidden = true;
  });
  $('#chk-traj').addEventListener('change', async ev => {
    S.showTrajectories = ev.target.checked;
    if (S.showTrajectories) await loadTrajectories();
    drawPiper('piper-plot');
    if (S.piperDrawn.has('piper-plot2')) drawPiper('piper-plot2');
    if (!S.data.temporal.has_dates && S.showTrajectories) {
      toast('Tus datos no tienen fechas: no hay trayectoria que dibujar.');
    }
  });
  $('#sel-stiff').addEventListener('change', reanalyse);
  $('#sel-colorby').addEventListener('change', ev => {
    S.colorBy = ev.target.value;
    drawPiper('piper-plot');
    if (S.piperDrawn.has('piper-plot2')) drawPiper('piper-plot2');
  });
  $('#sel-mapcolor').addEventListener('change', ev => {
    S.mapColorBy = ev.target.value;
    Object.keys(S.maps).forEach(k => paintMarkers(k, S.mapColorBy));
  });
  $('#sel-colorby').value = S.colorBy;
  $('#sel-mapcolor').value = S.mapColorBy;
  $('#sel-station').addEventListener('change', drawTemporal);
  $('#sel-temporal-mode').addEventListener('change', drawTemporal);
  $('#sel-stiff-mode').addEventListener('change', ev => {
    S.stiffMode = ev.target.value;
    drawStiff();
  });

  matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => refreshView());
  addEventListener('resize', () => {
    Object.values(S.maps).forEach(m => m.invalidateSize());
  });
}

async function init() {
  wire();
  try {
    const opts = await (await fetch('/api/options')).json();
    $('#sel-convention').innerHTML = opts.piper_conventions
      .map(c => `<option value="${c.key}">${c.name}</option>`).join('');
    $('#sel-stiff').innerHTML = opts.stiff_templates
      .map(t => `<option value="${t.key}">${t.name}</option>`).join('');
    $('#sel-facies').innerHTML = opts.facies_schemes
      .map(f => `<option value="${f.key}">${f.name}</option>`).join('');
    $('#sel-standard').innerHTML = opts.standards
      .map(st => `<option value="${st.key}">${st.name}</option>`).join('');
    $('#sel-crs').innerHTML = '<option value="">Detectar automáticamente</option>' +
      opts.crs_options.map(c =>
        `<option value="${c.epsg}">${c.name}</option>`).join('');
    if (!opts.example_available) {
      $('#btn-example').disabled = true;
      $('#btn-example-2').disabled = true;
    }
    // El servidor guarda el dataset en memoria: si la pagina se recarga, se
    // recupera en lugar de dejar la interfaz vacia sobre datos que siguen ahi.
    const previo = await (await fetch('/api/state')).json();
    if (previo.loaded) {
      adopt(previo);
      toast(`Recuperado: ${previo.source}`);
    }
  } catch (e) {
    toast('No se pudo contactar con el servidor local.', true);
  }
}

init();
