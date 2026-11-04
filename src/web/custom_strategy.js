(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  if (root) root.CustomStrategyConfig = api;
})(typeof window !== 'undefined' ? window : globalThis, function () {
  const numeric = (value, name) => {
    const parsed = Number(value);
    if (!Number.isFinite(parsed) || parsed < 0) throw new Error(`${name} must be a non-negative number`);
    return parsed;
  };

  function dispatchConfigFromValues(values) {
    const weights = {
      price: numeric(values.price, 'price'),
      load: numeric(values.load, 'load'),
      carbon: numeric(values.carbon, 'carbon'),
      latency: numeric(values.latency, 'latency'),
    };
    if (Object.values(weights).every(value => value === 0)) throw new Error('at least one weight must be greater than zero');
    return {
      name: String(values.name || 'custom_weighted').trim() || 'custom_weighted',
      weights,
      allow_cross_region: Boolean(values.allowCrossRegion),
    };
  }

  function pricingConfigFromValues(values) {
    const result = {
      name: String(values.name || 'grid_responsive_price').trim() || 'grid_responsive_price',
      base_price: numeric(values.basePrice, 'base_price'),
      local_load_coefficient: numeric(values.localLoad, 'local_load_coefficient'),
      compute_load_coefficient: numeric(values.computeLoad, 'compute_load_coefficient'),
      voltage_deviation_coefficient: numeric(values.voltageDeviation, 'voltage_deviation_coefficient'),
      minimum_price: numeric(values.minimumPrice, 'minimum_price'),
      maximum_price: numeric(values.maximumPrice, 'maximum_price'),
    };
    if (result.minimum_price > result.maximum_price) throw new Error('minimum_price must not exceed maximum_price');
    return result;
  }

  function dispatchValuesFromConfig(config) {
    const weights = config?.weights || {};
    return {
      price: Number(weights.price),
      load: Number(weights.load),
      carbon: Number(weights.carbon),
      latency: Number(weights.latency),
      allowCrossRegion: Boolean(config?.allow_cross_region),
    };
  }

  function pricingValuesFromConfig(config) {
    return {
      basePrice: Number(config?.base_price),
      localLoad: Number(config?.local_load_coefficient),
      computeLoad: Number(config?.compute_load_coefficient),
      voltageDeviation: Number(config?.voltage_deviation_coefficient),
      minimumPrice: Number(config?.minimum_price),
      maximumPrice: Number(config?.maximum_price),
    };
  }

  function objectiveConfigFromValues(values) {
    const weights = {
      cost: numeric(values.cost, 'cost'),
      carbon: numeric(values.carbon, 'carbon'),
      delay: numeric(values.delay, 'delay'),
      peak_shaving: numeric(values.peakShaving, 'peak_shaving'),
      renewable_curtailment: numeric(values.renewableCurtailment, 'renewable_curtailment'),
      storage_degradation: numeric(values.storageDegradation, 'storage_degradation'),
    };
    if (Object.values(weights).every(value => value === 0)) throw new Error('at least one objective weight must be greater than zero');
    return {
      name: String(values.name || 'custom_multi_objective').trim() || 'custom_multi_objective',
      weights,
    };
  }

  function objectiveValuesFromConfig(config) {
    const weights = config?.weights || {};
    return {
      cost: Number(weights.cost),
      carbon: Number(weights.carbon),
      delay: Number(weights.delay),
      peakShaving: Number(weights.peak_shaving),
      renewableCurtailment: Number(weights.renewable_curtailment),
      storageDegradation: Number(weights.storage_degradation),
    };
  }

  return {
    dispatchConfigFromValues,
    dispatchValuesFromConfig,
    pricingConfigFromValues,
    pricingValuesFromConfig,
    objectiveConfigFromValues,
    objectiveValuesFromConfig,
  };
});
