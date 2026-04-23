import sys

from autoharness import get_adapter


def test_generic_command_adapter_executes_python_command() -> None:
    adapter = get_adapter("generic_command")
    result = adapter.run(
        {
            "benchmark_name": "smoke",
            "command": [sys.executable, "-c", "print('ok')"],
        }
    )

    assert result.success is True
    assert result.exit_code == 0
    assert result.stdout.strip() == "ok"
    assert result.timed_out is False
