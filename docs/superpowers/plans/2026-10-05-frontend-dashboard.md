# 算电协同仿真平台前端 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a usable Chinese dashboard frontend for configuring and controlling the existing simulation engine and viewing/exporting its four result series.

**Architecture:** Serve a dependency-free static dashboard from FastAPI. Add a small API session layer for multipart configuration upload, simulation lifecycle, status polling, and export. Keep the existing engine and query endpoints as the source of simulation data; only adapt configuration and lifecycle at the API boundary.

**Tech Stack:** Python/FastAPI, stdlib CSV/JSON/zipfile, vanilla HTML/CSS/JavaScript, browser Fetch API, inline SVG charts.

**Spec:** `docs/superpowers/specs/2026-10-05-frontend-dashboard-design.md`

## Global Constraints

- No new npm runtime dependency or frontend build step.
- Only start/end controls; no pause.
- No frontend generation/load time-series uploads.
- Peak/valley price is CSV import.
- Mapping is read-only predefined linear mapping.
- Exactly four result charts are shown.

## Review Focus

- Configuration upload errors must return readable 4xx details and leave the last valid session intact.
- Start must not proceed before configuration has been applied.
- Stop must be idempotent and preserve the latest result snapshot.
- Empty/latest engine stats must render zero-state cards without JavaScript errors.
- Export must not expose arbitrary filesystem paths.

### Task 1: Add frontend API session and lifecycle routes

**Files:**
- Create: `src/api/frontend_routes.py`
- Modify: `src/app.py`
- Test: `tests/api/test_frontend_routes.py`

**Interfaces:**
- Produces `POST /config/apply`, `POST /simulation/start`, `POST /simulation/stop`, `GET /simulation/status`, `GET /export`.
- Consumes the current engine methods `stop`, `get_latest_stats`, `get_total_carbon_summary`, `get_optimization_result`, and `get_pricing` when present.

- [ ] Write tests for root-independent configuration application, required CSV validation, start gating, stop idempotency, status zero-state, and export response.
- [ ] Run the focused tests and observe expected route-not-found/failure.
- [ ] Implement an app-scoped `FrontendSession` with last-valid configuration, file metadata/content in memory, engine factory callback, and safe export generation.
- [ ] Register routes in `create_app` and map validation errors to 4xx responses.
- [ ] Run focused tests, then the full pytest suite.

### Task 2: Serve the dashboard shell and controls

**Files:**
- Create: `src/web/index.html`
- Create: `src/web/styles.css`
- Create: `src/web/app.js`
- Modify: `src/app.py`
- Test: `tests/api/test_frontend_static.py`

**Interfaces:**
- `GET /` serves the page and `/static/*` serves assets.
- JavaScript submits multipart configuration, starts/stops simulation, polls status, and requests export.

- [ ] Write static-content tests asserting required labels, three editable strategy groups, read-only mapping, upload controls, four chart IDs, and no pause control.
- [ ] Run tests and observe missing page/assets.
- [ ] Implement semantic dashboard markup with accessible labels and file inputs.
- [ ] Implement responsive two-column styling, status/KPI cards, upload feedback, and four SVG chart containers.
- [ ] Implement Fetch-based state management, validation feedback, polling, zero-state rendering, and export selection.
- [ ] Run static tests and full pytest suite.

### Task 3: End-to-end verification and documentation

**Files:**
- Modify: `README.md`
- Test: `tests/api/test_frontend_routes.py`

- [ ] Add a short run section describing the root page and configuration flow.
- [ ] Run the complete test suite and a Python import/compile check.
- [ ] Start the app in a bounded local process, request `/`, and verify the HTML response and static asset response.
- [ ] Review the UI source against every spec constraint and record any deferred minor issues.

