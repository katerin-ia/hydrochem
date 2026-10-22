// Run with: node tests/frontend-regressions.cjs
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

async function main() {
  const plot = {clientWidth: 1150, on() {}, removeAllListeners() {}};
  const station = {value: 'A', dataset: {filled: 'example'}};
  const elements = {'#stiff-note': {}, '#stiff-plot': plot, '#sel-station': station,
    '#temporal-note': {}, '#temporal-plot': {}};
  let layout;
  let requests = 0;
  const context = vm.createContext({
    document: {querySelector: key => elements[key], querySelectorAll: () => []},
    Plotly: {react: (el, traces, value) => {layout = value;}},
    fetch: async () => {requests++; return {ok: true, json: async () => ({station: 'A'})};},
    console
  });
  vm.runInContext(fs.readFileSync(path.join(__dirname, '../app/static/review.js'), 'utf8'), context);
  const source = fs.readFileSync(path.join(__dirname, '../app/static/app.js'), 'utf8');
  vm.runInContext(source.replace(/init\(\);\s*$/, ''), context);
  vm.runInContext(`
    S.data = {source: 'example', groups: ['a','b','c','d','e','f','g'],
      stiff: {labels: [['Na','Cl'],['Ca','HCO3'],['Mg','SO4']]},
      temporal: {has_dates: true, can_plot_series: true, repeated_stations: ['A','B'],
        message: '', can_discuss_trend: true}};
    S.samples = S.data.groups.map((group, i) => ({id: 's'+i, station: group,
      group, stiff: [[1,2],[3,4],[1,1]]}));
    drawStiff();
  `, context);
  assert.equal(Object.keys(layout).filter(k => /^xaxis/.test(k)).length, 7);
  assert.ok(layout.height >= 990, 'seven groups wrap into three rows');
  assert.ok(layout.xaxis4.domain[0] === layout.xaxis.domain[0]);
  assert.ok(layout.annotations.filter(a => a.text.startsWith('<b>'))[3].y < layout.yaxis.domain[0] - 0.01, 'row titles stay clear of the preceding axes');
  assert.ok(layout.xaxis.ticktext.every(v => !v.startsWith('-')));
  await vm.runInContext("fetchSeries('A')", context);
  await vm.runInContext("fetchSeries('A')", context);
  assert.equal(requests, 1, 'switching chart mode reuses station data');

  vm.runInContext(`
    var pending = [], rendered = [];
    fetchSeries = station => new Promise(resolve => pending.push({station, resolve}));
    renderTemporal = (data, station) => rendered.push(station);
    S.view = 'temporal';
    drawTemporal();
  `, context);
  station.value = 'B';
  vm.runInContext('drawTemporal(); pending[1].resolve({});', context);
  await Promise.resolve();
  vm.runInContext('pending[0].resolve({});', context);
  await Promise.resolve();
  assert.equal(vm.runInContext("rendered.join(',')", context), 'B',
    'a delayed response must not replace the current station');
  console.log('Frontend regressions: OK');
}
main().catch(error => {console.error(error); process.exitCode = 1;});
