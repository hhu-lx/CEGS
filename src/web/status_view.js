(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  if (root) root.GridStatusView = api;
})(typeof window !== 'undefined' ? window : globalThis, function () {
  const finite = (value) => value !== null && value !== undefined && Number.isFinite(Number(value));
  const number = (value) => finite(value) ? Number(value).toFixed(2) : '0.00';

  function buildGridStatusView(stats) {
    const cpf = stats.cpf_result || {};
    const voltage = stats.grid_voltage_health || {};
    const line = stats.grid_line_health || {};
    const totalLoad = finite(stats.total_load) ? Number(stats.total_load) : null;
    const reserve = finite(stats.reserve_capacity_mw) ? Number(stats.reserve_capacity_mw) : null;
    const reserveRequired = finite(totalLoad) && totalLoad > 0 ? totalLoad * 0.20 : null;
    const reserveKnown = finite(reserve) && finite(reserveRequired);
    const reserveSufficient = reserveKnown && reserve >= reserveRequired;

    const flowLabel = cpf.converged === true ? 'Converged' : cpf.converged === false ? 'Not Converged' : 'Calculating';
    const voltageLabel = voltage.status === 'normal' ? 'Normal' : voltage.status === 'out_of_range' ? 'Out of Range' : cpf.converged === false ? 'Calculation Failed' : 'No Data';
    const lineLabel = line.status === 'overloaded' ? 'Overloaded' : line.status === 'watch' ? 'Watch' : line.status === 'normal' ? 'Normal' : cpf.converged === false ? 'Watch' : 'No Data';
    const reserveLabel = reserveKnown ? (reserveSufficient ? 'Sufficient' : 'Insufficient') : 'No Data';

    const alerts = [];
    if (cpf.converged === false) alerts.push('Power flow did not converge at the current operating point');
    if (voltage.status === 'out_of_range') {
      const range = finite(voltage.min_voltage_pu) && finite(voltage.max_voltage_pu)
        ? `，${number(voltage.min_voltage_pu)}–${number(voltage.max_voltage_pu)} pu`
        : '';
      alerts.push(`Voltage out of range: ${voltage.violating_buses || 0} buses${range}`);
    }
    if (line.status === 'overloaded') {
      const loading = finite(line.max_loading_pct) ? `: maximum loading ${number(line.max_loading_pct)}%` : '';
      alerts.push(`Line overload${loading}`);
    }
    if (reserveKnown && !reserveSufficient) {
      alerts.push(`ReserveInsufficient：${number(reserve)} MW (required at least ${number(reserveRequired)} MW)`);
    }

    return {
      statusLines: {
        flow: `● Power Flow：${flowLabel}`,
        voltage: `● Voltage：${voltageLabel}`,
        line: `● linesStatus：${lineLabel}`,
        reserve: `● Reserve：${reserveLabel}`,
      },
      alerts,
    };
  }

  return { buildGridStatusView };
});


