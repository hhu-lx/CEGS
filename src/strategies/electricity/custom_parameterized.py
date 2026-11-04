from __future__ import annotations


class GridResponsivePricing:
    """Safe formula-based nodal price driven by observable grid values."""

    def __init__(
        self,
        base_price: float = 0.45,
        local_load_coefficient: float = 0.0002,
        compute_load_coefficient: float = 0.002,
        voltage_deviation_coefficient: float = 1.5,
        minimum_price: float = 0.2,
        maximum_price: float = 1.5,
    ):
        values = {
            "base_price": base_price,
            "local_load_coefficient": local_load_coefficient,
            "compute_load_coefficient": compute_load_coefficient,
            "voltage_deviation_coefficient": voltage_deviation_coefficient,
            "minimum_price": minimum_price,
            "maximum_price": maximum_price,
        }
        values = {name: float(value) for name, value in values.items()}
        if any(value < 0 for value in values.values()):
            raise ValueError("custom pricing parameters must be non-negative")
        if values["minimum_price"] > values["maximum_price"]:
            raise ValueError("minimum_price must not exceed maximum_price")
        self.__dict__.update(values)

    def get_node_price(
        self,
        network,
        bus_id: int,
        extra_load_mw: float = 0.0,
        system_extra_load_mw: float = 0.0,
    ) -> float:
        local_load = 0.0
        if hasattr(network, "load") and len(network.load):
            local_load = float(network.load.loc[network.load["bus"] == bus_id, "p_mw"].sum())
        voltage = 1.0
        if hasattr(network, "res_bus") and bus_id in network.res_bus.index and "vm_pu" in network.res_bus:
            candidate = network.res_bus.loc[bus_id, "vm_pu"]
            if candidate == candidate:
                voltage = float(candidate)
        price = (
            self.base_price
            + self.local_load_coefficient * local_load
            + self.compute_load_coefficient * max(0.0, float(extra_load_mw))
            + self.voltage_deviation_coefficient * abs(1.0 - voltage)
        )
        return max(self.minimum_price, min(self.maximum_price, price))
