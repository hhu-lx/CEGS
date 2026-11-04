# Marginal Price Feedback Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the existing marginal-price strategy apply normalized system and node data-center load feedback on the shared time-of-use tariff.

**Architecture:** `PandapowerAdapter` will total its existing `extra_loads` and pass that value to `MarginalElectricityPricing`. The strategy will retain its public defaults and return the TOU base price multiplied by an equal-weight system/node feedback factor.

**Tech Stack:** Python, Pandapower, pytest.

**Spec:** `docs/superpowers/specs/2026-10-25-marginal-price-feedback-design.md`

## Global Constraints

- Do not add an electricity strategy, configuration file, web option, or run mode.
- Keep `base_price`, `sensitivity`, and `scale` constructor parameters compatible.
- Fixed-TOU and OPF pricing behavior must remain unchanged.

## Review Focus

- With zero system and node extra load, the price exactly equals the active TOU price; test in Task 1.
- A load at another node raises the queried node price through the system term; test in Task 1.
- The queried node's own positive load adds the node term; test in Task 1.
- Negative storage/other load values cannot reduce the marginal feedback term; test in Task 1.
- Adapter aggregation passes all positive configured compute loads, not just the queried node load; test in Task 2.

---

### Task 1: Implement and unit-test normalized feedback pricing

**Files:**
- Modify: `src/strategies/electricity/marginal.py`
- Test: `tests/strategies/test_marginal_pricing.py`

**Interfaces:**
- Consumes: `get_node_price(network, bus_id, extra_load_mw, system_extra_load_mw=0.0) -> float`.
- Produces: the TOU base price multiplied by `1 + sensitivity * 0.5 * (max(0, system_extra_load_mw)/scale + max(0, extra_load_mw)/scale)`.

- [x] **Step 1: Write failing tests**

```python
def test_marginal_price_uses_shared_tou_base_when_no_extra_load():
    assert pricing.get_node_price(None, 3, 0.0, 0.0) == 1.0

def test_marginal_price_combines_system_and_node_load_feedback():
    assert pricing.get_node_price(None, 3, 100.0, 300.0) == 1.02
```

- [x] **Step 2: Run the new tests and verify they fail**

Run: `F:\python\python.exe -m pytest tests/strategies/test_marginal_pricing.py -q`

Expected: FAIL because `get_node_price` does not accept `system_extra_load_mw`.

- [x] **Step 3: Implement the compatible optional `system_extra_load_mw` parameter in `src/strategies/electricity/marginal.py`**

Use equal 0.5 weights for normalized positive system and node load, leaving forecast behavior unchanged.

- [x] **Step 4: Run the strategy tests and verify they pass**

Run: `F:\python\python.exe -m pytest tests/strategies/test_marginal_pricing.py -q`

Expected: PASS.

### Task 2: Pass aggregate compute load through the grid adapter

**Files:**
- Modify: `src/infrastructure/pandapower_adapter.py`
- Test: `tests/strategies/test_marginal_pricing.py`

**Interfaces:**
- Consumes: `PandapowerAdapter.extra_loads: dict[int, float]`.
- Produces: `get_bus_marginal_price(bus_id)` calls the active strategy with the queried node load and the sum of positive extra loads.

- [x] **Step 1: Write a failing adapter aggregation test**

```python
def test_adapter_passes_total_positive_compute_load_to_marginal_strategy():
    adapter.extra_loads = {3: 100.0, 16: 200.0, 21: -50.0}
    assert adapter.get_bus_marginal_price(3) == 1.02
```

- [x] **Step 2: Run the new test and verify it fails**

Run: `F:\python\python.exe -m pytest tests/strategies/test_marginal_pricing.py -q`

Expected: FAIL because the adapter supplies only the queried node's load.

- [x] **Step 3: Modify `get_bus_marginal_price` in `src/infrastructure/pandapower_adapter.py`**

Sum only positive values from `extra_loads`, then pass the total as the optional strategy argument.

- [x] **Step 4: Run focused and full verification**

Run: `F:\python\python.exe -m pytest tests/strategies/test_marginal_pricing.py tests/strategies/test_fixed_tou_pricing.py -q`

Expected: PASS.

Run: `F:\python\python.exe -m pytest -q --disable-warnings`

Expected: PASS.
