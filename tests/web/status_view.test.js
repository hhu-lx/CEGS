const test = require('node:test');
const assert = require('node:assert/strict');

const { buildGridStatusView } = require('../../src/web/status_view.js');

test('healthy operating point shows conclusions only and does not warn about CPF boundary', () => {
  const view = buildGridStatusView({
    total_load: 6300,
    reserve_capacity_mw: 1656.87,
    cpf_result: {
      converged: true,
      stop_reason: 'power_flow_failure',
      failure_lambda: 1.15,
      voltage_margin_pct: 10,
    },
    grid_voltage_health: { status: 'normal', min_voltage_pu: 0.96, max_voltage_pu: 1.04 },
    grid_line_health: { status: 'normal', max_loading_pct: 77.08 },
  });

  assert.deepEqual(view.statusLines, {
    flow: '● 潮流状态：已收敛',
    voltage: '● 电压状态：正常',
    line: '● 线路状态：正常',
    reserve: '● 备用容量：充足',
  });
  assert.deepEqual(view.alerts, []);
});

test('real grid violations move their measurements into alerts', () => {
  const view = buildGridStatusView({
    total_load: 6300,
    reserve_capacity_mw: 500,
    cpf_result: { converged: true },
    grid_voltage_health: {
      status: 'out_of_range', violating_buses: 3,
      min_voltage_pu: 0.91, max_voltage_pu: 1.07,
    },
    grid_line_health: { status: 'overloaded', max_loading_pct: 123.45 },
  });

  assert.equal(view.statusLines.voltage, '● 电压状态：越限');
  assert.equal(view.statusLines.line, '● 线路状态：过载');
  assert.equal(view.statusLines.reserve, '● 备用容量：不足');
  assert.deepEqual(view.alerts, [
    '电压越限：3 个节点，0.91–1.07 pu',
    '线路过载：最大负载率 123.45%',
    '备用容量不足：500.00 MW（需求不低于 1260.00 MW）',
  ]);
});

test('missing reserve telemetry stays unavailable instead of becoming zero', () => {
  const view = buildGridStatusView({
    total_load: 6300,
    reserve_capacity_mw: null,
    cpf_result: { converged: true },
    grid_voltage_health: { status: 'normal' },
    grid_line_health: { status: 'normal' },
  });

  assert.equal(view.statusLines.reserve, '● 备用容量：暂无数据');
  assert.deepEqual(view.alerts, []);
});
