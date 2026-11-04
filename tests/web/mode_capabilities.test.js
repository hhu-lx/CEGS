const test = require('node:test');
const assert = require('node:assert/strict');

const {
  capabilitiesFor,
  selectionForMode,
  payloadForMode,
  statusLabel,
} = require('../../src/web/mode_capabilities.js');


test('shows only choices supported by the selected optimization model', () => {
  assert.deepEqual(capabilitiesFor('heuristic'), {
    fixedDispatch: null,
    dispatchManagedBy: null,
    dispatchStrategies: ['lowest_price', 'low_carbon', 'custom'],
    objectives: ['min_cost', 'min_curtailment', 'weighted', 'custom'],
  });
  assert.deepEqual(capabilitiesFor('local').dispatchStrategies, [
    'lowest_price', 'low_carbon', 'custom',
  ]);
  assert.equal(capabilitiesFor('global').fixedDispatch, 'optimizer_managed');
  assert.deepEqual(capabilitiesFor('global').objectives, ['min_cost', 'min_curtailment', 'weighted', 'custom']);
});


test('restores a mode-specific selection without leaking incompatible choices', () => {
  const previous = {
    local: { dispatch: 'custom', objective: 'min_cost' },
    heuristic: { dispatch: 'low_carbon', objective: 'min_cost' },
  };

  assert.deepEqual(selectionForMode(previous, 'heuristic'), {
    dispatch: 'low_carbon', objective: 'min_cost', dispatchManagedBy: null,
  });
  assert.deepEqual(selectionForMode(previous, 'local'), {
    dispatch: 'custom', objective: 'min_cost', dispatchManagedBy: null,
  });
  assert.deepEqual(selectionForMode(previous, 'global'), {
    dispatch: 'optimizer_managed', objective: 'min_cost', dispatchManagedBy: 'joint_optimizer',
  });
});


test('keeps heuristic custom dispatch while excluding delay weight', () => {
  const payload = payloadForMode({
    mode: 'heuristic',
    dispatch: 'custom',
    objective: 'custom',
    customDispatchConfig: { weights: { price: 1 } },
    customDispatchFile: { name: 'dispatch.json' },
    customObjectiveConfig: {
      weights: {
        cost: 1, carbon: 1, delay: 9, peak_shaving: 2,
        renewable_curtailment: 3, storage_degradation: 0.1,
      },
    },
  });

  assert.equal(payload.dispatch, 'custom');
  assert.equal(payload.objective, 'custom');
  assert.deepEqual(payload.customDispatchConfig, { weights: { price: 1 } });
  assert.deepEqual(payload.customDispatchFile, { name: 'dispatch.json' });
  assert.equal(payload.customObjectiveConfig.weights.delay, 0);
});


test('keeps local custom dispatch and global optimizer-managed dispatch', () => {
  const local = payloadForMode({
    mode: 'local', dispatch: 'custom', objective: 'min_cost',
    customDispatchConfig: { weights: { price: 1 } },
  });
  const globalMode = payloadForMode({
    mode: 'global', dispatch: 'custom', objective: 'weighted',
    customDispatchConfig: { weights: { price: 1 } },
  });

  assert.deepEqual(local.customDispatchConfig, { weights: { price: 1 } });
  assert.equal(local.dispatch, 'custom');
  assert.equal(globalMode.dispatch, 'optimizer_managed');
  assert.equal(globalMode.customDispatchConfig, undefined);
});


test('rejects an unknown optimization model', () => {
  assert.throws(() => capabilitiesFor('other'), /unknown optimization model/i);
});


test('formats the effective coordination mode without using stale form values', () => {
  assert.equal(statusLabel({ mode: 'heuristic', status: 'optimal' }), 'Baseline · Optimal');
  assert.equal(
    statusLabel({ mode: 'local', status: 'optimal', coordination_iterations: 3 }),
    'Power-Guided · 3 rounds · Optimal',
  );
  assert.equal(statusLabel({ mode: 'global', status: 'infeasible' }), 'Computing-Power Synergy · Infeasible');
});
