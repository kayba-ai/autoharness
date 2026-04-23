from autoharness import get_adapter


def test_pytest_adapter_builds_expected_command() -> None:
    adapter = get_adapter("pytest")
    invocation = adapter.build_invocation(
        {
            "targets": ["tests/test_example.py", "-k", "fast"],
            "extra_args": ["-q"],
        }
    )

    assert invocation.command == ("pytest", "tests/test_example.py", "-k", "fast", "-q")
    assert invocation.benchmark_name == "pytest"


def test_pytest_adapter_supports_module_mode() -> None:
    adapter = get_adapter("pytest")
    invocation = adapter.build_invocation(
        {
            "module_mode": True,
            "targets": ["tests"],
        }
    )

    assert invocation.command[:3] == ("python", "-m", "pytest")
