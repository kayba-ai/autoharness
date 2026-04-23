from autoharness import get_adapter, implemented_adapter_ids


def test_adapter_registry_contains_expected_implementations() -> None:
    assert implemented_adapter_ids() == (
        "car_bench",
        "generic_command",
        "harbor",
        "pytest",
        "tau2_bench",
        "hal",
    )
    assert get_adapter("car_bench").adapter_id == "car_bench"
    assert get_adapter("generic_command").adapter_id == "generic_command"
    assert get_adapter("harbor").adapter_id == "harbor"
    assert get_adapter("pytest").adapter_id == "pytest"
    assert get_adapter("tau2_bench").adapter_id == "tau2_bench"
    assert get_adapter("hal").adapter_id == "hal"


def test_adapter_staging_profiles_capture_local_defaults() -> None:
    assert get_adapter("generic_command").staging_profile().default_mode == "copy"
    assert get_adapter("pytest").staging_profile().default_mode == "copy"
    assert get_adapter("car_bench").staging_profile().default_mode == "copy"
    assert get_adapter("harbor").staging_profile().default_mode == "off"
    assert get_adapter("tau2_bench").staging_profile().default_mode == "off"
