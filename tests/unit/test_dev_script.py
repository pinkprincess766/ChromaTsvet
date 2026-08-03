from pathlib import Path

import scripts.dev as dev


def test_venv_python_uses_platform_specific_layout():
    root = Path("workspace") / ".venv"

    assert dev.venv_python(root, os_name="posix") == root / "bin" / "python"
    assert dev.venv_python(root, os_name="nt") == root / "Scripts" / "python.exe"


def test_python_version_check_enforces_project_minimum():
    assert dev.check_python_version((3, 9)).ok
    assert dev.check_python_version((3, 12)).ok
    assert not dev.check_python_version((3, 8)).ok


def test_check_file_reports_relative_project_path():
    result = dev.check_file(dev.PROJECT_ROOT / "pyproject.toml", "metadata")

    assert result.ok
    assert result.detail == "pyproject.toml"


def test_print_check_results_is_plain_and_actionable(capsys):
    results = [
        dev.CheckResult("Python", True, "3.12"),
        dev.CheckResult("Cargo", False, "`cargo` not found"),
    ]

    dev.print_check_results(results)

    output = capsys.readouterr().out
    assert "[OK] Python" in output
    assert "[FAIL] Cargo" in output
    assert "`cargo` not found" in output
