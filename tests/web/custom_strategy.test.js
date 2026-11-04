const test = require('node:test');
const assert = require('node:assert/strict');

const {
  dispatchConfigFromValues,
  dispatchValuesFromConfig,
  pricingConfigFromValues,
  pricingValuesFromConfig,
  objectiveConfigFromValues,
  objectiveValuesFromConfig,
} = require('../../src/web/custom_strategy.js');

test('builds a dispatch configuration from frontend values', () => {
  assert.deepEqual(dispatchConfigFromValues({
    name: 'price_load_mix', price: '0.5', load: '0.3', carbon: '0.1', latency: '0.1', allowCrossRegion: true,
  }), {
    name: 'price_load_mix',
    weights: { price: 0.5, load: 0.3, carbon: 0.1, latency: 0.1 },
    allow_cross_region: true,
  });
});

test('rejects an all-zero dispatch configuration before upload', () => {
  assert.throws(() => dispatchConfigFromValues({ price: 0, load: 0, carbon: 0, latency: 0 }), /at least one/i);
});

test('builds and validates a custom pricing configuration', () => {
  assert.deepEqual(pricingConfigFromValues({
    name: 'grid_responsive_price', basePrice: '0.45', localLoad: '0.0002', computeLoad: '0.002',
    voltageDeviation: '1.5', minimumPrice: '0.2', maximumPrice: '1.5',
  }), {
    name: 'grid_responsive_price', base_price: 0.45, local_load_coefficient: 0.0002,
    compute_load_coefficient: 0.002, voltage_deviation_coefficient: 1.5,
    minimum_price: 0.2, maximum_price: 1.5,
  });
});

test('maps effective uploaded configurations back to frontend values', () => {
  assert.deepEqual(dispatchValuesFromConfig({
    weights: { price: 0.5, load: 0.3, carbon: 0.1, latency: 0.1 },
    allow_cross_region: false,
  }), {
    price: 0.5, load: 0.3, carbon: 0.1, latency: 0.1, allowCrossRegion: false,
  });
  assert.deepEqual(pricingValuesFromConfig({
    base_price: 0.45,
    local_load_coefficient: 0.0002,
    compute_load_coefficient: 0.002,
    voltage_deviation_coefficient: 1.5,
    minimum_price: 0.2,
    maximum_price: 1.5,
  }), {
    basePrice: 0.45,
    localLoad: 0.0002,
    computeLoad: 0.002,
    voltageDeviation: 1.5,
    minimumPrice: 0.2,
    maximumPrice: 1.5,
  });
});

test('builds and restores a safe custom optimization objective', () => {
  const config = objectiveConfigFromValues({
    name: 'custom_multi_objective', cost: '1', carbon: '0.5', delay: '0.2',
    peakShaving: '2', renewableCurtailment: '3', storageDegradation: '0.1',
  });
  assert.deepEqual(config, {
    name: 'custom_multi_objective',
    weights: {
      cost: 1, carbon: 0.5, delay: 0.2, peak_shaving: 2,
      renewable_curtailment: 3, storage_degradation: 0.1,
    },
  });
  assert.deepEqual(objectiveValuesFromConfig(config), {
    cost: 1, carbon: 0.5, delay: 0.2, peakShaving: 2,
    renewableCurtailment: 3, storageDegradation: 0.1,
  });
});
