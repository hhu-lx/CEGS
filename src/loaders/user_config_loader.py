"""Load and validate configuration submitted by the frontend."""

import copy
import json
from pathlib import Path
from typing import Any

from src.strategies.electricity.fixed_tou import FixedTimeOfUsePricing
from src.strategies.electricity.custom_parameterized import GridResponsivePricing


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _deep_merge(base: dict, override: dict) -> dict:
    result = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


_FRONTEND_CONFIG_SECTIONS = {"simulation", "optimization", "data_centers", "storages"}
_FRONTEND_DUPLICATE_INPUTS = {
    "data_sources": "use the dedicated file upload controls or platform defaults",
    "tasks": "use the dedicated task-file upload control",
    "pricing": "use the dedicated time-of-use CSV upload control",
    "electricity_pricing": "use the dedicated time-of-use CSV upload control",
    "topology": "topology is managed by platform defaults",
}

_PREDEFINED_FALLBACK_POWER_PER_TFLOPS_MW = 0.001


def _apply_predefined_power_mapping(base_centers: list, uploaded_centers: list) -> list:
    """Keep user resource sizing while protecting the platform power model."""
    platform_by_id = {
        center.get("id"): center
        for center in base_centers
        if isinstance(center, dict) and center.get("id")
    }
    effective = []
    for uploaded in uploaded_centers:
        center = copy.deepcopy(uploaded)
        if center.get("device_pool"):
            effective.append(center)
            continue
        platform = platform_by_id.get(center.get("id"), {})
        platform_devices = platform.get("device_pool") or []
        if platform_devices:
            center["device_pool"] = copy.deepcopy(platform_devices)
            # Keep the uploaded mapping values user-configurable while
            # inheriting only the platform's equipment inventory.  The
            # example user config intentionally omits device details, but its
            # power_scale must still override the platform default.
            center["power_per_tflops"] = float(
                center.get(
                    "power_per_tflops",
                    platform.get("power_per_tflops", _PREDEFINED_FALLBACK_POWER_PER_TFLOPS_MW),
                )
            )
            center["power_scale"] = float(
                center.get("power_scale", platform.get("power_scale", 1.0))
            )
        else:
            center["device_pool"] = []
            center["power_per_tflops"] = _PREDEFINED_FALLBACK_POWER_PER_TFLOPS_MW
        effective.append(center)
    return effective


def validate_frontend_user_config(config: dict) -> None:
    """Validate the restricted configuration shape accepted by the Web UI."""
    if not isinstance(config, dict):
        raise ValueError("user_config must be a JSON object")
    for field in config:
        if field in _FRONTEND_DUPLICATE_INPUTS:
            raise ValueError(f"{field} is not accepted in frontend user config; {_FRONTEND_DUPLICATE_INPUTS[field]}")
        if field not in _FRONTEND_CONFIG_SECTIONS:
            raise ValueError(f"unsupported frontend user config field: {field}")
    optimization = config.get("optimization", {})
    if isinstance(optimization, dict) and optimization.get("objective_function"):
        raise ValueError("optimization.objective_function is not accepted in frontend user config; use the safe custom objective weights")
    validate_user_config(config)
    if "data_centers" in config and not config["data_centers"]:
        raise ValueError("data_centers must contain at least one data center")
    for index, center in enumerate(config.get("data_centers", [])):
        for field in ("name", "region", "grid_bus_id", "total_compute"):
            if field not in center:
                raise ValueError(f"data_centers[{index}].{field} is required")
        _number(center["total_compute"], f"data_centers[{index}].total_compute", 0.000001)
        if "total_bandwidth" in center:
            _number(center["total_bandwidth"], f"data_centers[{index}].total_bandwidth", 0.000001)
        device_pool = center.get("device_pool", [])
        if not isinstance(device_pool, list) or any(not isinstance(device, dict) for device in device_pool):
            raise ValueError(f"data_centers[{index}].device_pool must be an array of objects")
    for index, storage in enumerate(config.get("storages", [])):
        for field in ("bus_id", "capacity_mwh", "max_power_mw"):
            if field not in storage:
                raise ValueError(f"storages[{index}].{field} is required")


def merge_frontend_config(base: dict, user: dict, ui: dict) -> tuple[dict, dict]:
    """Resolve platform defaults, uploaded editable sections, then UI controls."""
    validate_frontend_user_config(user)
    if not isinstance(base, dict) or not isinstance(ui, dict):
        raise ValueError("base and ui configuration must be objects")

    result = copy.deepcopy(base)
    sources = {
        section: "user_upload" if section in user else "platform_default"
        for section in _FRONTEND_CONFIG_SECTIONS
    }
    for section, value in user.items():
        if section == "data_centers":
            result[section] = _apply_predefined_power_mapping(base.get("data_centers", []), value)
        elif section == "storages":
            result[section] = copy.deepcopy(value)
        else:
            current = result.get(section, {})
            if not isinstance(value, dict):
                raise ValueError(f"{section} must be an object")
            result[section] = _deep_merge(current if isinstance(current, dict) else {}, value)

    for section, value in ui.items():
        if section == "data_centers":
            result[section] = _apply_predefined_power_mapping(base.get("data_centers", []), value)
        elif section == "storages":
            result[section] = copy.deepcopy(value)
        elif isinstance(value, dict) and isinstance(result.get(section), dict):
            result[section] = _deep_merge(result[section], value)
        else:
            result[section] = copy.deepcopy(value)
    return result, sources


def load_user_config(
    user_config_file: str | None = None,
    user_config: dict | None = None,
    defaults: dict | None = None,
) -> dict:
    """Load user JSON/dict, merge it over defaults, then validate it."""
    if user_config_file and user_config is not None:
        raise ValueError("provide either user_config_file or user_config, not both")
    supplied = {}
    if user_config_file:
        path = Path(user_config_file)
        if not path.is_absolute():
            path = _project_root() / path
        with path.open("r", encoding="utf-8") as stream:
            supplied = json.load(stream)
    elif user_config is not None:
        supplied = copy.deepcopy(user_config)
    if not isinstance(supplied, dict):
        raise ValueError("user_config must be a JSON object")
    result = _deep_merge(defaults or {}, supplied)
    validate_user_config(result)
    return result


def _number(value: Any, path: str, minimum: float | None = None) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{path} must be a number")
    if minimum is not None and value < minimum:
        raise ValueError(f"{path} must be >= {minimum}")
    return float(value)


def validate_user_config(config: dict) -> None:
    if not isinstance(config, dict):
        raise ValueError("user_config must be an object")

    optimization = config.get("optimization", {})
    if not isinstance(optimization, dict):
        raise ValueError("optimization must be an object")
    mode = optimization.get("mode", "none")
    if mode not in {"none", "hierarchical", "joint", "local", "global"}:
        raise ValueError("optimization.mode must be none, hierarchical, or joint")

    simulation = config.get("simulation", {})
    if not isinstance(simulation, dict):
        raise ValueError("simulation must be an object")
    for field in (
        "duration_hours",
        "step_seconds",
        "stats_interval_seconds",
        "renewable_optimization_interval_seconds",
        "report_interval_seconds",
        "cpf_interval_seconds",
        "power_flow_interval_seconds",
    ):
        if field in simulation:
            _number(simulation[field], f"simulation.{field}", 0.000001)

    pricing = config.get("pricing", config.get("electricity_pricing", {}))
    if pricing and not isinstance(pricing, dict):
        raise ValueError("pricing must be an object")
    if pricing.get("mode", "marginal") not in {"fixed_tou", "marginal", "custom"}:
        raise ValueError("pricing.mode must be fixed_tou, marginal, or custom")
    periods = pricing.get("periods")
    if periods is not None:
        try:
            FixedTimeOfUsePricing(periods)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"pricing.periods: {exc}") from exc
    if pricing.get("mode") == "custom":
        parameters = pricing.get("parameters")
        if not isinstance(parameters, dict):
            raise ValueError("pricing.parameters must be an object")
        try:
            GridResponsivePricing(**{
                key: value for key, value in parameters.items() if key != "name"
            })
        except (TypeError, ValueError) as exc:
            raise ValueError(f"pricing.parameters: {exc}") from exc

    data_sources = config.get("data_sources", {})
    if data_sources and not isinstance(data_sources, dict):
        raise ValueError("data_sources must be an object")
    for key, value in data_sources.items():
        if value is not None and not isinstance(value, str):
            raise ValueError(f"data_sources.{key} must be a path string")
        if isinstance(value, str) and ".." in Path(value).parts:
            raise ValueError(f"data_sources.{key} must stay inside allowed roots")

    for collection_name in ("data_centers", "storages"):
        collection = config.get(collection_name)
        if collection is None:
            continue
        if not isinstance(collection, list):
            raise ValueError(f"{collection_name} must be an array")
        ids = []
        for index, item in enumerate(collection):
            if not isinstance(item, dict):
                raise ValueError(f"{collection_name}[{index}] must be an object")
            item_id = item.get("id")
            if not isinstance(item_id, str) or not item_id:
                raise ValueError(f"{collection_name}[{index}].id must be a non-empty string")
            if item_id in ids:
                raise ValueError(f"{collection_name}[{index}].id must be unique")
            ids.append(item_id)


def validate_user_resources(config: dict, topology: dict | None = None) -> None:
    """Validate user data-center and storage resources against a topology."""
    bus_ids = None
    if topology is not None:
        bus_ids = {bus.get("id") for bus in topology.get("buses", []) if isinstance(bus, dict)}
    for collection_name in ("data_centers", "storages"):
        for index, item in enumerate(config.get(collection_name, []) or []):
            path = f"{collection_name}[{index}]"
            bus_id = item.get("grid_bus_id" if collection_name == "data_centers" else "bus_id")
            if bus_ids is not None and bus_id not in bus_ids:
                raise ValueError(f"{path}.{'grid_bus_id' if collection_name == 'data_centers' else 'bus_id'} references unknown bus {bus_id}")
            if collection_name == "storages":
                capacity = _number(item.get("capacity_mwh"), f"{path}.capacity_mwh", 0)
                minimum = _number(item.get("min_soc_mwh", 0), f"{path}.min_soc_mwh", 0)
                initial = _number(item.get("initial_soc_mwh", 0), f"{path}.initial_soc_mwh", 0)
                _number(item.get("max_power_mw"), f"{path}.max_power_mw", 0)
                _number(item.get("charge_efficiency"), f"{path}.charge_efficiency", 0)
                _number(item.get("discharge_efficiency"), f"{path}.discharge_efficiency", 0)
                if minimum > initial or initial > capacity:
                    raise ValueError(f"{path}.initial_soc_mwh must be between min_soc_mwh and capacity_mwh")
                if item.get("charge_efficiency") > 1 or item.get("discharge_efficiency") > 1:
                    raise ValueError(f"{path} efficiencies must be <= 1")


def resolve_user_path(path: str, allowed_roots: list[Path]) -> Path:
    """Resolve a user path and reject paths outside explicitly allowed roots."""
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = _project_root() / candidate
    candidate = candidate.resolve()
    roots = [Path(root).resolve() for root in allowed_roots]
    for root in roots:
        try:
            candidate.relative_to(root)
            return candidate
        except ValueError:
            continue
    raise ValueError(f"path is outside allowed roots: {path}")
