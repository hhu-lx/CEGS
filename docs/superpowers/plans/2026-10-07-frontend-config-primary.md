# 前端上传配置主路径实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the front-end uploaded configuration the primary source for user-editable simulation resources while retaining `platform.yaml` as the fallback, and make the effective configuration visible before a run starts.

**Architecture:** Add one shared Web-config validation and merge path that overlays user configuration and UI-owned inputs onto the platform defaults. Keep the CLI loader's current compatibility behavior separate. The `/config/apply` response and engine startup will use the same resolved configuration, with task and tariff files continuing through their dedicated upload controls.

**Tech Stack:** Python 3.10+, FastAPI, Pydantic/YAML loader, vanilla JavaScript, pytest.

**Spec:** `docs/superpowers/specs/2026-10-07-frontend-config-primary-design.md`

## Global Constraints

- Front-end user upload is the primary source for this run; `config/platform.yaml` provides fallback defaults.
- Uploaded `data_centers` and `storages` replace their respective platform collections; object-valued settings merge by field.
- The dedicated task-file and TOU CSV uploads remain the Web sources for those inputs.
- This change does not modify task scheduling, optimization algorithms, equipment power curves, or bandwidth constraints.
- CLI `--config` and `--user-config` compatibility must not be changed unintentionally.

## Review Focus

- Old uploaded configs with duplicated file-path fields must fail with a specific migration message; test in Task 1.
- Partial user config must keep platform fallback values while uploaded resource collections replace defaults; test in Task 1 and Task 2.
- UI-selected optimization mode and dedicated file uploads must take precedence over conflicting user-config values; test in Task 2 and Task 3.
- API preview and actual engine startup must resolve the same data-center values and provenance; test in Task 3.
- Missing optional task upload must follow the documented platform fallback behavior without accidentally submitting both sources; test in Task 3.

---

### Task 1: Define and test the Web user-config schema and merge behavior

**Files:**
- Modify: `src/loaders/user_config_loader.py`
- Test: `tests/loaders/test_user_config_loader.py`

**Interfaces:**
- Produces: `validate_frontend_user_config(config: dict) -> None`, which accepts only `simulation`, `optimization`, `data_centers`, and `storages` at the root and raises a field-specific `ValueError` for duplicate Web inputs such as `data_sources`, `tasks`, `pricing`, `electricity_pricing`, or `topology`.
- Produces: `merge_frontend_config(base: dict, user: dict, ui: dict) -> tuple[dict, dict]`, returning the fully resolved config and section provenance (`user_upload` or `platform_default`). Mapping sections merge recursively; `data_centers` and `storages` replace as complete lists when present. UI-owned controls override matching fields.
- Existing `load_user_config` / `validate_user_config` remain available to CLI callers without this Web-only restriction.

- [ ] **Step 1: Add failing schema and merge tests**

Add tests asserting that legacy Web path keys are rejected with the offending field in the error; omitted user sections retain platform values; uploaded center/storage lists replace the defaults; mapping-valued simulation/optimization fields retain unspecified defaults; and UI mode overrides uploaded optimization mode.

- [ ] **Step 2: Run the focused loader tests and confirm the new assertions fail**

Run: `F:\miniconda\envs\cesynergy\python.exe -m pytest tests/loaders/test_user_config_loader.py -q`
Expected: new tests fail because the Web validator and merge helper do not exist.

- [ ] **Step 3: Implement the Web-only validator and shared merge helper**

Keep legacy CLI validation unchanged. Include section-level provenance for `data_centers` and `storages`; preserve platform defaults for omitted sections and apply explicit UI overrides last.

- [ ] **Step 4: Run the focused loader tests**

Run: `F:\miniconda\envs\cesynergy\python.exe -m pytest tests/loaders/test_user_config_loader.py -q`
Expected: all loader tests pass.

### Task 2: Use the shared resolver in the simulation engine and simplify the example config

**Files:**
- Modify: `src/simulation/engine.py`
- Modify: `config/user_config.example.json`
- Modify: `tests/simulation/test_user_config_engine.py`
- Modify: `tests/integration/test_json_configuration_compatibility.py`

**Interfaces:**
- Consumes: `validate_frontend_user_config` and `merge_frontend_config` from Task 1.
- Produces: the engine's effective runtime configuration resolved from `platform.yaml`, partial uploaded config, and explicit frontend controls; direct `SimulationEngine(user_config=...)` must keep existing behavior except that Web-config callers use the shared resolver.

- [ ] **Step 1: Add failing engine tests**

Replace the old Web-config custom-topology assertion with tests proving uploaded DC values override platform defaults, omitted DC/storage sections retain platform defaults (DC compute 250/200/300 TFLOPS), UI optimization mode is authoritative while uploaded objective/weights are preserved, and inline `topology` is rejected for Web uploads. Keep CLI compatibility tests accepting the example config.

- [ ] **Step 2: Run the focused engine/config tests and confirm failures**

Run: `F:\miniconda\envs\cesynergy\python.exe -m pytest tests/simulation/test_user_config_engine.py tests/integration/test_json_configuration_compatibility.py -q`
Expected: new precedence assertions fail before integration.

- [ ] **Step 3: Resolve engine config through the shared helper**

Replace the separate Web merge behavior in `src/simulation/engine.py` with the shared resolver while preserving the CLI `--config` / `--user-config` path. Web-supplied inline topology is disallowed; CLI topology compatibility remains. Ensure user-provided center/storage lists are complete replacements and omitted sections fall back to `platform.yaml`.

- [ ] **Step 4: Simplify `config/user_config.example.json`**

Keep simulation settings, optimization objective/weights, data centers, and storages. Set example compute to DC1 250, DC2 200, DC3 300 TFLOPS. Remove duplicate file paths, pricing definitions, topology, and task-source entries.

- [ ] **Step 5: Run the focused engine/config tests**

Run: `F:\miniconda\envs\cesynergy\python.exe -m pytest tests/simulation/test_user_config_engine.py tests/integration/test_json_configuration_compatibility.py -q`
Expected: all focused tests pass, including legacy CLI compatibility.

### Task 3: Return and display the effective configuration in the Web UI

**Files:**
- Modify: `src/api/frontend_routes.py`
- Modify: `src/web/app.js`
- Modify: `src/web/index.html`
- Modify: `tests/api/test_frontend_routes.py`
- Modify: `tests/api/test_frontend_static.py`

**Interfaces:**
- Consumes: `merge_frontend_config` and Web validation from Task 1; resolved runtime config behavior from Task 2.
- Produces: `/config/apply` response fields `effective_data_centers` (`id`, `name`, `total_compute`, `total_bandwidth`, compute-device quantity) and `configuration_sources`; the UI renders these values and their source after successful application.

- [ ] **Step 1: Add failing route and static UI tests**

Assert an upload containing custom centers returns those effective values with source `user_upload`; no uploaded center list returns the platform defaults with source `platform_default`; legacy duplicate path keys return HTTP 422 with a migration message; no task upload falls back to the platform task file exactly once; and the static page includes an accessible element for the effective-resource summary.

- [ ] **Step 2: Run focused API tests and confirm the new assertions fail**

Run: `F:\miniconda\envs\cesynergy\python.exe -m pytest tests/api/test_frontend_routes.py tests/api/test_frontend_static.py -q`
Expected: new response/UI assertions fail before integration.

- [ ] **Step 3: Resolve and return the effective preview from `FrontendSession.apply`**

Load the platform defaults, validate the uploaded Web config, apply UI controls and dedicated upload metadata using the shared merge helper, and include the resolved resource summary/provenance in the response. If no task file was uploaded, retain the platform task-file fallback; otherwise submit only the uploaded task file. Pass the same partial user config and UI-owned fields to engine startup.

- [ ] **Step 4: Render the effective resource summary in the frontend**

After `/config/apply` succeeds, display each data center's name, compute, bandwidth, compute-device quantity, and whether values came from the upload or platform defaults. Do not clear or rewrite the user's uploaded files.

- [ ] **Step 5: Update README configuration guidance**

Document the precedence and the permitted user-config sections; explain that task and TOU CSV files use their dedicated upload controls and that duplicate path fields in old Web configs must be removed.

- [ ] **Step 6: Run focused and full verification**

Run: `F:\miniconda\envs\cesynergy\python.exe -m pytest tests/loaders/test_user_config_loader.py tests/simulation/test_user_config_engine.py tests/integration/test_json_configuration_compatibility.py tests/api/test_frontend_routes.py tests/api/test_frontend_static.py -q`
Then run: `F:\miniconda\envs\cesynergy\python.exe -m pytest -q --disable-warnings`
Expected: focused tests and full test suite pass; startup log and `/config/apply` preview show identical capacities.
