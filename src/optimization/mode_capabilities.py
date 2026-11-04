"""Compatibility rules for the frontend optimization modes.

The UI and API use these rules to prevent a visible selection from being
silently replaced by a different runtime branch.
"""

from __future__ import annotations

from dataclasses import dataclass


COMPREHENSIVE_OBJECTIVE_WEIGHTS = {
    "cost": 1.0,
    "carbon": 1.5,
    "delay": 0.2,
    # Balance peak shifting against renewable absorption without forcing
    # the battery to charge at every small renewable surplus.
    "peak_shaving": 3.0,
    "renewable_curtailment": 1.0,
    "storage_degradation": 0.5,
}


@dataclass(frozen=True)
class ModeCapabilities:
    mode: str
    fixed_dispatch: str | None
    dispatch_strategies: tuple[str, ...]
    objectives: tuple[str, ...]


@dataclass(frozen=True)
class NormalizedSelection:
    mode: str
    dispatch_strategy: str
    objective: str
    dispatch_managed_by: str | None


_POWER_OBJECTIVES = (
    "min_cost",
    "min_curtailment",
    "weighted",
    "custom",
)
_COORDINATED_OBJECTIVES = (
    "min_cost",
    "min_curtailment",
    "weighted",
    "custom",
)
_DISPATCH_STRATEGIES = (
    "lowest_price",
    "low_carbon",
    "custom",
)

_CAPABILITIES = {
    "heuristic": ModeCapabilities(
        mode="heuristic",
        fixed_dispatch=None,
        dispatch_strategies=_DISPATCH_STRATEGIES,
        objectives=_POWER_OBJECTIVES,
    ),
    "local": ModeCapabilities(
        mode="local",
        fixed_dispatch=None,
        dispatch_strategies=_DISPATCH_STRATEGIES,
        objectives=_COORDINATED_OBJECTIVES,
    ),
    "global": ModeCapabilities(
        mode="global",
        fixed_dispatch="optimizer_managed",
        dispatch_strategies=(),
        objectives=_COORDINATED_OBJECTIVES,
    ),
}


def capabilities_for(mode: str) -> ModeCapabilities:
    try:
        return _CAPABILITIES[mode]
    except KeyError as exc:
        raise ValueError(f"Unknown optimization model: {mode}") from exc


def normalise_frontend_selection(
    mode: str,
    dispatch: str | None,
    objective: str,
) -> NormalizedSelection:
    capabilities = capabilities_for(mode)
    if objective not in capabilities.objectives:
        raise ValueError(f"Optimization model {mode} does not support objective {objective}")

    if capabilities.fixed_dispatch is None:
        effective_dispatch = dispatch or "lowest_price"
        if effective_dispatch not in capabilities.dispatch_strategies:
            raise ValueError(f"Optimization model {mode} does not support dispatch strategy {effective_dispatch}")
        managed_by = None
    else:
        # Older frontend builds always submitted their currently visible
        # built-in strategy.  Accept and explicitly normalize those values so
        # upgrades do not break saved forms, but never accept custom settings
        # for a model-managed branch.
        compatible_legacy_values = {None, capabilities.fixed_dispatch, *_DISPATCH_STRATEGIES[:-1]}
        if dispatch not in compatible_legacy_values:
            raise ValueError(f"Dispatch strategy for optimization model {mode} is model-managed; {dispatch} is not allowed")
        effective_dispatch = capabilities.fixed_dispatch
        managed_by = "joint_optimizer"

    return NormalizedSelection(
        mode=mode,
        dispatch_strategy=effective_dispatch,
        objective=objective,
        dispatch_managed_by=managed_by,
    )
