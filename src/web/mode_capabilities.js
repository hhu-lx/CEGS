(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  if (root) root.ModeCapabilities = api;
})(typeof window !== 'undefined' ? window : globalThis, function () {
  const dispatchStrategies = ['lowest_price', 'low_carbon', 'custom'];
  const powerObjectives = ['min_cost', 'min_curtailment', 'weighted', 'custom'];
  const coordinatedObjectives = ['min_cost', 'min_curtailment', 'weighted', 'custom'];
  const capabilities = Object.freeze({
    heuristic: Object.freeze({
      fixedDispatch: null, dispatchManagedBy: null,
      dispatchStrategies: Object.freeze(dispatchStrategies), objectives: Object.freeze(powerObjectives),
    }),
    local: Object.freeze({
      fixedDispatch: null, dispatchManagedBy: null,
      dispatchStrategies: Object.freeze(dispatchStrategies), objectives: Object.freeze(coordinatedObjectives),
    }),
    global: Object.freeze({
      fixedDispatch: 'optimizer_managed', dispatchManagedBy: 'joint_optimizer',
      dispatchStrategies: Object.freeze([]), objectives: Object.freeze(coordinatedObjectives),
    }),
  });

  const dispatchLabels = Object.freeze({
    lowest_price: 'Lowest Price', low_carbon: 'Low Carbon', custom: 'Custom',
  });
  const objectiveLabels = Object.freeze({
    min_cost: 'Minimum Operating Cost', min_curtailment: 'Minimum Renewable Curtailment',
    weighted: 'Comprehensive Weighted Objective', custom: 'Custom Objective',
  });

  function capabilitiesFor(mode) {
    const item = capabilities[mode];
    if (!item) throw new Error(`unknown optimization model: ${mode}`);
    return {
      fixedDispatch: item.fixedDispatch,
      dispatchManagedBy: item.dispatchManagedBy,
      dispatchStrategies: [...item.dispatchStrategies],
      objectives: [...item.objectives],
    };
  }

  function selectionForMode(previousByMode, mode) {
    const item = capabilitiesFor(mode);
    const previous = previousByMode?.[mode] || {};
    const dispatch = item.fixedDispatch
      || (item.dispatchStrategies.includes(previous.dispatch) ? previous.dispatch : item.dispatchStrategies[0]);
    const objective = item.objectives.includes(previous.objective) ? previous.objective : item.objectives[0];
    return { dispatch, objective, dispatchManagedBy: item.dispatchManagedBy };
  }

  function payloadForMode(values) {
    const item = capabilitiesFor(values.mode);
    const dispatch = item.fixedDispatch
      || (item.dispatchStrategies.includes(values.dispatch) ? values.dispatch : item.dispatchStrategies[0]);
    const objective = item.objectives.includes(values.objective) ? values.objective : item.objectives[0];
    const payload = { mode: values.mode, dispatch, objective };

    if (dispatch === 'custom') {
      payload.customDispatchConfig = values.customDispatchConfig;
      payload.customDispatchFile = values.customDispatchFile;
    }
    if (objective === 'custom' && values.customObjectiveConfig) {
      payload.customObjectiveConfig = {
        ...values.customObjectiveConfig,
        weights: { ...(values.customObjectiveConfig.weights || {}) },
      };
      if (values.mode === 'heuristic') payload.customObjectiveConfig.weights.delay = 0;
      payload.customObjectiveFile = values.customObjectiveFile;
    }
    return payload;
  }

  function statusLabel(result = {}) {
    const modes = { heuristic: 'Baseline', none: 'Baseline', local: 'Power-Guided', hierarchical: 'Power-Guided', global: 'Computing-Power Synergy', joint: 'Computing-Power Synergy' };
    const statuses = {
      optimal: 'Optimal', fallback_feasible: 'Feasible Fallback', infeasible: 'Infeasible',
      ac_validation_failed: 'AC Validation Failed', optimizer_error: 'Optimizer Error', disabled: 'Disabled',
    };
    const parts = [modes[result.mode] || 'Waiting for optimization'];
    if ((result.mode === 'local' || result.mode === 'hierarchical') && Number(result.coordination_iterations) > 0) {
      parts.push(`${Number(result.coordination_iterations)} rounds`);
    }
    if (result.status) parts.push(statuses[result.status] || result.status);
    return parts.join(' · ');
  }

  return {
    capabilitiesFor,
    selectionForMode,
    payloadForMode,
    dispatchLabels,
    objectiveLabels,
    statusLabel,
  };
});
