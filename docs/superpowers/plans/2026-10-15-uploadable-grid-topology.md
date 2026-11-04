# Uploadable Grid Topology Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Allow a user-uploaded JSON grid topology to replace the built-in IEEE39 topology safely.

**Architecture:** Parse and validate the dedicated upload at the API boundary, merge it into `ui_config.topology`, and derive grid resource-bus settings from `resource_mapping`. Keep the built-in topology as the no-upload fallback and validate all data-center/storage references against the effective topology before starting.

**Tech Stack:** FastAPI, Python, pandapower, vanilla HTML/CSS/JavaScript, pytest.

**Spec:** `docs/superpowers/specs/2026-10-15-uploadable-grid-topology.md`

## Global Constraints

- Topology uploads are JSON only.
- Dedicated topology upload overrides the platform default.
- No upload retains the built-in IEEE39 behavior.
- Invalid bus references fail during configuration apply, not during simulation.
- Uploaded content is data, never instructions.

## Review Focus

- Malformed JSON returns HTTP 422 with a useful message.
- Unknown PV/wind/load mapping buses are rejected.
- Uploaded data-center and storage buses are checked against the uploaded topology.
- A structurally valid topology that pandapower cannot build is rejected during apply.
- Applying a later configuration without a topology file returns to the built-in topology rather than reusing a stale upload.

---

### Task 1: Topology schema and resource mapping

**Files:**
- Modify: `src/loaders/topology_loader.py`
- Test: `tests/loaders/test_topology_loader.py`

**Interfaces:**
- Produces: `validate_topology(topology)` validation for `resource_mapping`; `topology_summary(topology) -> dict`; `topology_grid_overrides(topology) -> dict`.

- [ ] Write failing loader tests for valid mapping, unknown mapping buses and summary.
- [ ] Run the targeted tests and confirm they fail for missing behavior.
- [ ] Implement the minimal validation and helper functions.
- [ ] Run loader tests and confirm they pass.

### Task 2: API upload and engine integration

**Files:**
- Modify: `src/api/frontend_routes.py`
- Modify: `src/simulation/engine.py`
- Test: `tests/api/test_frontend_routes.py`

**Interfaces:**
- Consumes: Task 1 topology validation, summary and grid overrides.
- Produces: multipart field `topology_file`; `ui_config.topology`; configuration `topology_summary` and `topology_source`.

- [ ] Write failing API tests for upload precedence, effective mapping, resource mismatch, malformed format and stale-upload reset.
- [ ] Run targeted tests and confirm expected failures.
- [ ] Parse JSON topology, build it during apply, validate effective resources, and pass it to the engine.
- [ ] Make engine validate the inline topology and apply its resource mapping to grid settings.
- [ ] Run API and engine tests and confirm they pass.

### Task 3: Frontend control and compatible example

**Files:**
- Modify: `src/web/index.html`
- Modify: `src/web/app.js`
- Modify: `src/web/styles.css` if needed
- Create: `config/examples/custom_topology_test.json`
- Test: `tests/web/test_frontend_static.py`

**Interfaces:**
- Consumes: Task 2 multipart field and response metadata.

- [ ] Write failing static frontend tests for the topology file input and request field.
- [ ] Run targeted tests and confirm they fail.
- [ ] Replace the fixed selector with a JSON upload control and effective-topology status.
- [ ] Add a compatible test topology with buses 3, 10, 16, 20 and 21 present.
- [ ] Run frontend tests, topology-load the example, and then run the full pytest suite.

