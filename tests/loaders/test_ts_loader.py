from src.loaders.ts_loader import TimeSeriesDataLoader


def test_time_series_loader_applies_start_offset_before_elapsed_time():
    loader = TimeSeriesDataLoader(
        "tests/fixtures/time_series_offset_test.csv",
        "测试时序",
        time_compression=1.0,
        start_offset_seconds=2,
    )

    assert loader.get_value_at_second(0) == 2.0
    assert loader.get_value_at_second(1) == 3.0


def test_time_series_offset_is_applied_in_source_time_after_compression():
    loader = TimeSeriesDataLoader(
        "tests/fixtures/time_series_offset_test.csv",
        "测试时序",
        time_compression=2.0,
        start_offset_seconds=2,
    )

    assert loader.get_value_at_second(0) == 2.0
    assert loader.get_value_at_second(2) == 3.0
