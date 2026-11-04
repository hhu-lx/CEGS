from dataclasses import dataclass
import csv
from pathlib import Path


@dataclass(frozen=True)
class TariffPeriod:
    start_hour: float
    end_hour: float
    price: float


class FixedTimeOfUsePricing:
    """User-replaceable fixed time-of-use tariff in yuan/kWh."""

    def __init__(self, periods: list[dict] | list[TariffPeriod]):
        self.periods = [
            period if isinstance(period, TariffPeriod) else TariffPeriod(**period)
            for period in periods
        ]
        if not self.periods:
            raise ValueError("at least one fixed tariff period is required")
        for period in self.periods:
            if not 0 <= period.start_hour < 24 or not 0 < period.end_hour <= 24:
                raise ValueError("tariff hours must be within [0, 24]")
            if period.start_hour >= period.end_hour or period.price < 0:
                raise ValueError("tariff period or price is invalid")
        ordered = sorted(self.periods, key=lambda item: item.start_hour)
        if ordered[0].start_hour != 0 or ordered[-1].end_hour != 24 or any(
            current.start_hour != previous.end_hour
            for previous, current in zip(ordered, ordered[1:])
        ):
            raise ValueError("fixed tariff periods must cover the complete 24-hour day")
        for previous, current in zip(ordered, ordered[1:]):
            if current.start_hour < previous.end_hour:
                raise ValueError("fixed tariff periods must not overlap")

    @classmethod
    def from_csv(cls, file_path: str | Path) -> "FixedTimeOfUsePricing":
        """Load user-defined periods from a CSV file.

        Required columns are ``start_hour``, ``end_hour`` and ``price``;
        an optional ``label`` column is ignored by the pricing engine.
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"tariff file does not exist: {path}")
        with path.open("r", encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream)
            required = {"start_hour", "end_hour", "price"}
            if not reader.fieldnames or not required.issubset(set(reader.fieldnames)):
                raise ValueError("tariff CSV must contain start_hour,end_hour,price columns")
            periods = []
            for row in reader:
                if not row or not any(str(value or "").strip() for value in row.values()):
                    continue
                periods.append({
                    "start_hour": float(row["start_hour"]),
                    "end_hour": float(row["end_hour"]),
                    "price": float(row["price"]),
                })
        return cls(periods)

    def price_at_hour(self, hour: float) -> float:
        hour = hour % 24.0
        for period in self.periods:
            if period.start_hour <= hour < period.end_hour:
                return period.price
        raise ValueError(f"no fixed tariff period covers hour {hour}")

    def as_dict(self) -> dict:
        return {
            "mode": "fixed_tou",
            "periods": [period.__dict__ for period in self.periods],
        }
