const test = require('node:test');
const assert = require('node:assert/strict');

let trendCharts = {};
try {
  trendCharts = require('../../src/web/trend_charts.js');
} catch (_error) {
  // The first TDD run intentionally reaches this branch until the asset exists.
}

test('trend chart module exposes the dashboard series builder', () => {
  assert.equal(typeof trendCharts.buildTrendSeries, 'function');
});

test('trend chart module exposes rolling, aggregation and combined-chart builders', () => {
  assert.equal(typeof trendCharts.upsertRollingHistory, 'function');
  assert.equal(typeof trendCharts.upsertLongTermHistory, 'function');
  assert.equal(typeof trendCharts.buildComputeOverview, 'function');
  assert.equal(typeof trendCharts.buildLongTermPowerSeries, 'function');
});

test('dashboard series combines supply and demand and exposes renewable absorption', () => {
  const series = trendCharts.buildTrendSeries([
    {
      total_load: 6300,
      total_generation: 6340,
      renewable_available_mw: 240,
      renewable_consumed_mw: 210,
      renewable_curtailed_mw: 30,
    },
    {
      total_load: 6350,
      total_generation: 6390,
      renewable_available_mw: 260,
      renewable_consumed_mw: 250,
      renewable_curtailed_mw: 10,
    },
  ]);

  assert.deepEqual(series.power, [
    { label: '总负荷', color: '#274c5e', values: [6300, 6350] },
    { label: '总发电', color: '#b35f3f', values: [6340, 6390] },
  ]);
  assert.deepEqual(series.renewable, [
    { label: '可用绿电', color: '#1478e8', values: [240, 260] },
    { label: '实际消纳', color: '#159d93', values: [210, 250] },
    { label: '弃电', color: '#e3a33d', values: [30, 10] },
  ]);
});

test('rolling history replaces duplicate seconds and discards the oldest point', () => {
  let history = [];
  for (const second of [1, 2, 3, 4]) {
    history = trendCharts.upsertRollingHistory(history, { second, total_load: second * 10 }, 3);
  }
  history = trendCharts.upsertRollingHistory(history, { second: 4, total_load: 44 }, 3);

  assert.deepEqual(history.map(record => [record.second, record.total_load]), [
    [2, 20], [3, 30], [4, 44],
  ]);
});

test('long-term history averages five-minute buckets and keeps a bounded 24-hour window', () => {
  let history = [];
  history = trendCharts.upsertLongTermHistory(history, {
    second: 0, total_load: 100, total_generation: 110, grid_exchange_mw: 80,
    wind_generation_mw: 10, pv_generation_mw: 5, storage_power_mw: 2,
  }, 300, 2);
  history = trendCharts.upsertLongTermHistory(history, {
    second: 60, total_load: 200, total_generation: 210, grid_exchange_mw: 120,
    wind_generation_mw: 30, pv_generation_mw: 15, storage_power_mw: 4,
  }, 300, 2);

  assert.deepEqual({
    bucket_start: history[0].bucket_start,
    samples: history[0].samples,
    total_load: history[0].total_load,
    total_generation: history[0].total_generation,
    grid_exchange_mw: history[0].grid_exchange_mw,
    wind_generation_mw: history[0].wind_generation_mw,
    pv_generation_mw: history[0].pv_generation_mw,
    storage_power_mw: history[0].storage_power_mw,
    max_total_load: history[0].max_total_load,
  }, {
    bucket_start: 0, samples: 2, total_load: 150, total_generation: 160,
    grid_exchange_mw: 100, wind_generation_mw: 20, pv_generation_mw: 10,
    storage_power_mw: 3, max_total_load: 200,
  });

  history = trendCharts.upsertLongTermHistory(history, { second: 300, total_load: 300 }, 300, 2);
  history = trendCharts.upsertLongTermHistory(history, { second: 600, total_load: 400 }, 300, 2);
  assert.deepEqual(history.map(bucket => bucket.bucket_start), [300, 600]);
});

test('combined compute data discovers every user-defined data center dynamically', () => {
  const overview = trendCharts.buildComputeOverview([
    {
      compute_power_mw: 2,
      running_compute_by_datacenter: {
        alpha: { name: '自定义中心甲', compute_tflops: 10 },
        omega: { name: '边缘节点', compute_tflops: 5 },
      },
    },
    {
      compute_power_mw: 3,
      running_compute_by_datacenter: {
        omega: { name: '边缘节点', compute_tflops: 8 },
        extra: { name: '新增中心', compute_tflops: 4 },
      },
    },
  ]);

  assert.deepEqual(overview.centers, [
    { id: 'alpha', name: '自定义中心甲' },
    { id: 'omega', name: '边缘节点' },
    { id: 'extra', name: '新增中心' },
  ]);
  assert.deepEqual(overview.computeByCenter, {
    alpha: [10, 0], omega: [5, 8], extra: [0, 4],
  });
  assert.deepEqual(overview.powerMw, [2, 3]);
});

test('long-term power series separates balancing generation from renewable output', () => {
  const series = trendCharts.buildLongTermPowerSeries([{
    total_load: 100,
    total_generation: 110,
    grid_exchange_mw: 70,
    wind_generation_mw: 20,
    pv_generation_mw: 10,
    storage_power_mw: 5,
  }]);

  assert.deepEqual(series.generation, [
    { label: '平衡电源', color: '#7895ad', values: [75] },
    { label: '风电', color: '#159d93', values: [20] },
    { label: '光伏', color: '#e3a33d', values: [10] },
    { label: '储能放电', color: '#8064a2', values: [5] },
  ]);
  assert.deepEqual(series.lines, [
    { label: '总负荷', color: '#1478e8', values: [100] },
    { label: '电网交换', color: '#df6b5b', values: [70] },
  ]);
});
