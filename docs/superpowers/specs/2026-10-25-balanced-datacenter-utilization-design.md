# Balanced Data-Center Utilization Design

## Intent

Avoid long-lived idle data centers in local and global optimization while
preserving feasible task scheduling.  Calibrate the 24-hour scenario so wind
and PV output is about 20% of total load, while computing tasks account for
about 2% of total load. Shanghai is currently underused because its smaller
compute/GPU fleet gives comparable tasks a higher modeled power draw and
therefore a higher effective energy cost.

## Chosen approach

Apply the approved combined configuration change:

1. Make Shanghai comparable with Beijing by setting its configured compute
   capacity to 250 TFLOPS and its H100 inventory to three units.
2. Improve Shanghai's modeled task energy efficiency by lowering its
   `power_per_tflops` from 0.45 to 0.40 MW/TFLOPS.  PUE remains 1.15, so
   facility overhead remains represented consistently across centers.
3. Set each center's `power_scale` to 2.87.  With the 24-hour task table and
   balanced placement, this produces about 125.1 MW mean compute demand,
   equal to 2% of the 6,254.2 MW mean background load.
4. Set both `pv_capacity_mw` and `wind_capacity_mw` to 2,450 MW.  With the
   retained wind/PV profiles this produces about 1,275.2 MW mean renewable
   output, or 20.0% of the 6,379.3 MW total mean load after compute demand.
5. Raise `optimization.load_balance_weight` from 1.0 to 3.0.  This remains a
   soft range penalty, so it cannot override GPU, compute, bandwidth,
   user-specified placement, or deadline feasibility constraints.

## Goals

- Make Shanghai competitive on modeled energy cost for comparable tasks.
- Make local and joint optimization prefer balanced projected utilization when
  feasible.
- Match the specified ratios as 24-hour mean MW ratios; instantaneous values
  are intentionally allowed to vary with the renewable and task time series.
- Keep the five-minute coordinated task batching and deadline bypass unchanged.

## Non-goals

- Do not impose a hard minimum utilization or force infeasible task placement.
- Do not change electricity tariffs, renewable profiles, task data, or the
  optimizer formulation.

## Verification

- Load the platform configuration and assert the Shanghai resource, ratio and
  balance values.
- Compute 24-hour means from the configured profiles and assert renewable/load
  is approximately 20% and compute/load is approximately 2%.
- Compute a representative task's power at all three centers and assert that
  Shanghai is no longer the highest-power placement.
- Run the existing local/joint balance regression tests and configuration tests.
