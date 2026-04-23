from autoharness.benchmarks import benchmark_catalog, recommended_v1_adapter_ids


def test_catalog_contains_expected_v1_adapters() -> None:
    adapter_ids = {spec.adapter_id for spec in benchmark_catalog()}
    assert "car_bench" in adapter_ids
    assert "generic_command" in adapter_ids
    assert "pytest" in adapter_ids
    assert "harbor" in adapter_ids
    assert "tau2_bench" in adapter_ids
    assert "hal" in adapter_ids


def test_recommended_v1_adapter_ids_are_stable() -> None:
    assert recommended_v1_adapter_ids() == (
        "generic_command",
        "pytest",
        "harbor",
        "tau2_bench",
        "hal",
    )
