"""Small developer workflow helper for source checkouts.

The script keeps setup commands explicit while giving contributors one stable
entry point for common tasks.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_VENV_DIR = PROJECT_ROOT / ".venv"
MIN_PYTHON = (3, 9)
PYTHON_DEPENDENCIES = (
    ("numpy", "numpy"),
    ("scipy", "scipy"),
    ("PyQt5", "PyQt5"),
    ("pyqtgraph", "pyqtgraph"),
    ("reportlab", "reportlab"),
    ("Pillow", "PIL"),
    ("openpyxl", "openpyxl"),
)


@dataclass(frozen=True)
class CheckResult:
    name: str
    ok: bool
    detail: str


def venv_python(venv_dir: Path = DEFAULT_VENV_DIR, os_name: str | None = None) -> Path:
    """Return the Python executable path for a virtual environment."""
    platform_name = os.name if os_name is None else os_name
    if platform_name == "nt":
        return venv_dir / "Scripts" / "python.exe"
    return venv_dir / "bin" / "python"


def preferred_python(venv_dir: Path = DEFAULT_VENV_DIR) -> Path:
    """Use the project venv when present, otherwise the current interpreter."""
    candidate = venv_python(venv_dir)
    return candidate if candidate.exists() else Path(sys.executable)


def check_python_version(version_info: tuple[int, int] | None = None) -> CheckResult:
    version = version_info or sys.version_info[:2]
    ok = tuple(version) >= MIN_PYTHON
    return CheckResult(
        "Python",
        ok,
        f"{version[0]}.{version[1]} (requires {MIN_PYTHON[0]}.{MIN_PYTHON[1]}+)",
    )


def check_file(path: Path, label: str) -> CheckResult:
    return CheckResult(label, path.exists(), str(path.relative_to(PROJECT_ROOT)))


def check_executable(command: str, label: str) -> CheckResult:
    resolved = shutil.which(command)
    return CheckResult(label, resolved is not None, resolved or f"`{command}` not found")


def check_python_module(module_name: str, label: str) -> CheckResult:
    code = f"import {module_name}"
    completed = subprocess.run(
        [str(preferred_python()), "-c", code],
        cwd=PROJECT_ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return CheckResult(label, completed.returncode == 0, module_name)


def collect_doctor_checks() -> list[CheckResult]:
    checks = [
        check_python_version(),
        check_file(PROJECT_ROOT / "pyproject.toml", "Python package metadata"),
        check_file(PROJECT_ROOT / "rust_module" / "Cargo.toml", "Rust package metadata"),
        check_executable("cargo", "Cargo"),
        check_python_module("maturin", "maturin"),
    ]
    checks.extend(
        check_python_module(module_name, label)
        for label, module_name in PYTHON_DEPENDENCIES
    )
    checks.append(check_python_module("spectrometer_rust", "Rust extension"))
    return checks


def print_check_results(results: Sequence[CheckResult]) -> None:
    width = max(len(result.name) for result in results) if results else 0
    for result in results:
        status = "OK" if result.ok else "FAIL"
        print(f"[{status}] {result.name:<{width}} {result.detail}")


def run_command(command: Sequence[str], *, cwd: Path = PROJECT_ROOT) -> None:
    print("$ " + " ".join(command))
    subprocess.run(list(command), cwd=cwd, check=True)


def ensure_venv(venv_dir: Path = DEFAULT_VENV_DIR) -> Path:
    python_path = venv_python(venv_dir)
    if not python_path.exists():
        run_command([sys.executable, "-m", "venv", str(venv_dir)])
    return python_path


def command_setup(args: argparse.Namespace) -> int:
    python_path = ensure_venv(Path(args.venv))
    run_command([str(python_path), "-m", "pip", "install", "--upgrade", "pip"])
    run_command([str(python_path), "-m", "pip", "install", "-e", ".[dev]"])
    run_command(
        [
            str(python_path),
            "-m",
            "maturin",
            "develop",
            "--manifest-path",
            "rust_module/Cargo.toml",
        ]
    )
    return 0


def command_doctor(_args: argparse.Namespace) -> int:
    results = collect_doctor_checks()
    print_check_results(results)
    return 0 if all(result.ok for result in results) else 1


def command_run(_args: argparse.Namespace) -> int:
    run_command([str(preferred_python()), "-m", "python_analyzer.main"])
    return 0


def command_test(_args: argparse.Namespace) -> int:
    env = dict(os.environ)
    env.setdefault("QT_QPA_PLATFORM", "offscreen")
    command = [str(preferred_python()), "-m", "pytest", "-q"]
    print("$ " + " ".join(command))
    subprocess.run(command, cwd=PROJECT_ROOT, env=env, check=True)
    return 0


def command_rust(_args: argparse.Namespace) -> int:
    run_command(["cargo", "test", "--manifest-path", "rust_module/Cargo.toml"])
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="ChromaTsvet source checkout helper",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    setup = subparsers.add_parser("setup", help="create .venv and build the Rust extension")
    setup.add_argument(
        "--venv",
        default=str(DEFAULT_VENV_DIR),
        help="virtual environment directory (default: .venv)",
    )
    setup.set_defaults(func=command_setup)

    doctor = subparsers.add_parser("doctor", help="check local developer environment")
    doctor.set_defaults(func=command_doctor)

    run = subparsers.add_parser("run", help="start ChromaTsvet from the checkout")
    run.set_defaults(func=command_run)

    test = subparsers.add_parser("test", help="run the Python test suite")
    test.set_defaults(func=command_test)

    rust = subparsers.add_parser("rust", help="run Rust unit tests")
    rust.set_defaults(func=command_rust)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
