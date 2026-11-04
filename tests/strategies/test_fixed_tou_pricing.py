from src.strategies.electricity.fixed_tou import FixedTimeOfUsePricing
import pytest


def test_fixed_tou_price_uses_peak_valley_periods():
    pricing = FixedTimeOfUsePricing([
        {"start_hour": 0, "end_hour": 7, "price": 0.30},
        {"start_hour": 7, "end_hour": 23, "price": 0.90},
        {"start_hour": 23, "end_hour": 24, "price": 0.30},
    ])

    assert pricing.price_at_hour(3) == 0.30
    assert pricing.price_at_hour(12) == 0.90
    assert pricing.price_at_hour(23.5) == 0.30


def test_fixed_tou_can_load_user_periods_from_csv():
    pricing = FixedTimeOfUsePricing.from_csv("tests/fixtures/time_of_use_pricing.csv")

    assert pricing.price_at_hour(2) == 0.20
    assert pricing.price_at_hour(12) == 0.65
    assert pricing.price_at_hour(19) == 1.10


def test_fixed_tou_rejects_gaps_in_user_periods():
    with pytest.raises(ValueError, match="cover the complete 24-hour day"):
        FixedTimeOfUsePricing([
            {"start_hour": 0, "end_hour": 7, "price": 0.20},
            {"start_hour": 8, "end_hour": 24, "price": 0.80},
        ])
