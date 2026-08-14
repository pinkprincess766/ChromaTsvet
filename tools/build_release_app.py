#!/usr/bin/env python3
"""Build a desktop app archive suitable for attaching to a GitHub release."""

from __future__ import annotations

import argparse
import hashlib
import os
import platform
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Sequence


PROJECT_ROOT = Path(__file__).resolve().parents[1]
APP_NAME = "ChromaTsvet"
PYPROJECT = PROJECT_ROOT / "pyproject.toml"
RUST_MANIFEST = PROJECT_ROOT / "rust_module" / "Cargo.toml"
ENTRY_POINT = PROJECT_ROOT / "python_analyzer" / "main.py"
ASSETS_DIR = PROJECT_ROOT / "assets"
LOGO_PATH = ASSETS_DIR / "chromatsvet_logo.png"
BUILD_ROOT = PROJECT_ROOT / "build" / "pyinstaller"
DIST_ROOT = PROJECT_ROOT / "dist" / "pyinstaller"
WHEEL_ROOT = BUILD_ROOT / "wheels"


class BuildError(RuntimeError):
    """Raised when the release app archive cannot be created safely."""


def run(
    command: Sequence[str],
    *,
    cwd: Path = PROJECT_ROOT,
    env: dict[str, str] | None = None,
) -> None:
    print("$ " + " ".join(command))
    subprocess.run(list(command), cwd=cwd, env=env, check=True)


def read_project_version() -> str:
    text = PYPROJECT.read_text(encoding="utf-8")
    match = re.search(r'(?m)^version\s*=\s*"([^"]+)"\s*$', text)
    if not match:
        raise BuildError("Cannot read project version from pyproject.toml")
    return match.group(1)


def platform_slug() -> str:
    system = platform.system()
    machine = platform.machine().lower() or "unknown"
    machine = {"amd64": "x86_64"}.get(machine, machine)
    if system == "Darwin":
        return f"macos-{machine}"
    if system == "Windows":
        return f"windows-{machine}"
    raise BuildError("Release app archives are currently supported on macOS and Windows")


def safe_remove(path: Path) -> None:
    resolved = path.resolve()
    allowed_roots = (
        BUILD_ROOT.resolve(),
        DIST_ROOT.resolve(),
        (PROJECT_ROOT / "release_artifacts").resolve(),
    )
    if not any(resolved == root or root in resolved.parents for root in allowed_roots):
        raise BuildError(f"Refusing to remove a path outside release build roots: {path}")
    if path.is_dir():
        shutil.rmtree(path)
    elif path.exists():
        path.unlink()


def create_icon() -> Path | None:
    if not LOGO_PATH.is_file():
        print("Logo file is missing; building without a custom app icon.")
        return None

    try:
        from PIL import Image
    except ImportError:
        print("Pillow is not available; building without a custom app icon.")
        return None

    BUILD_ROOT.mkdir(parents=True, exist_ok=True)
    image = Image.open(LOGO_PATH).convert("RGBA")
    if platform.system() == "Darwin":
        icon_path = BUILD_ROOT / "chromatsvet.icns"
        image.save(
            icon_path,
            format="ICNS",
            sizes=[(16, 16), (32, 32), (64, 64), (128, 128), (256, 256), (512, 512)],
        )
        return icon_path
    if platform.system() == "Windows":
        icon_path = BUILD_ROOT / "chromatsvet.ico"
        image.save(
            icon_path,
            format="ICO",
            sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
        )
        return icon_path
    return None


def ensure_rust_extension(skip_maturin: bool) -> None:
    if skip_maturin:
        print("Skipping maturin build by request.")
        return
    if WHEEL_ROOT.exists():
        safe_remove(WHEEL_ROOT)
    WHEEL_ROOT.mkdir(parents=True, exist_ok=True)

    # Build a wheel instead of using `maturin develop`: GitHub runners do not
    # provide an activated virtualenv, but pip can install a freshly built wheel.
    run(
        [
            sys.executable,
            "-m",
            "maturin",
            "build",
            "--manifest-path",
            str(RUST_MANIFEST),
            "--release",
            "--out",
            str(WHEEL_ROOT),
        ],
        cwd=RUST_MANIFEST.parent,
        env=rust_build_env(),
    )
    wheels = sorted(WHEEL_ROOT.glob("*.whl"), key=lambda path: path.stat().st_mtime)
    if not wheels:
        raise BuildError(f"maturin did not produce a wheel in {WHEEL_ROOT}")
    run(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--force-reinstall",
            "--no-deps",
            str(wheels[-1]),
        ],
        env=pip_env(),
    )


def rust_build_env() -> dict[str, str]:
    """Return a Cargo environment that avoids embedding private local paths."""
    env = dict(os.environ)
    remaps = [
        f"{PROJECT_ROOT}=<project>",
        f"{Path.home() / '.cargo'}=<cargo>",
        f"{Path.home() / '.rustup'}=<rustup>",
        f"{Path.home()}=<home>",
    ]
    existing_flags = env.get("RUSTFLAGS", "").strip()
    remap_flags = " ".join(f"--remap-path-prefix={mapping}" for mapping in remaps)
    env["RUSTFLAGS"] = f"{existing_flags} {remap_flags}".strip()
    return env


def pip_env() -> dict[str, str]:
    env = dict(os.environ)
    env["PIP_CACHE_DIR"] = str(BUILD_ROOT / "pip-cache")
    env["PIP_DISABLE_PIP_VERSION_CHECK"] = "1"
    return env


def pyinstaller_env() -> dict[str, str]:
    env = dict(os.environ)
    env["PYINSTALLER_CONFIG_DIR"] = str(BUILD_ROOT / "pyinstaller-config")
    return env


def pyinstaller_output_path() -> Path:
    if platform.system() == "Darwin":
        return DIST_ROOT / f"{APP_NAME}.app"
    if platform.system() == "Windows":
        return DIST_ROOT / APP_NAME
    raise BuildError("Unsupported release platform")


def build_app(icon_path: Path | None) -> Path:
    if not ENTRY_POINT.is_file():
        raise BuildError(f"Missing application entry point: {ENTRY_POINT}")
    if not ASSETS_DIR.is_dir():
        raise BuildError(f"Missing assets directory: {ASSETS_DIR}")

    output_path = pyinstaller_output_path()
    if output_path.exists():
        safe_remove(output_path)

    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--windowed",
        "--name",
        APP_NAME,
        "--distpath",
        str(DIST_ROOT),
        "--workpath",
        str(BUILD_ROOT / "work"),
        "--specpath",
        str(BUILD_ROOT / "spec"),
        "--add-data",
        f"{ASSETS_DIR}{os.pathsep}assets",
        "--collect-binaries",
        "spectrometer_rust",
        "--collect-submodules",
        "spectrometer_rust",
        "--hidden-import",
        "scipy.signal",
        "--hidden-import",
        "scipy.ndimage",
        "--hidden-import",
        "scipy.linalg",
        "--hidden-import",
        "openpyxl",
        "--hidden-import",
        "pyqtgraph.exporters",
        "--exclude-module",
        "pytest",
        "--exclude-module",
        "_pytest",
        "--exclude-module",
        "py",
    ]
    if icon_path is not None:
        command.extend(["--icon", str(icon_path)])
    command.append(str(ENTRY_POINT))

    run(command, env=pyinstaller_env())
    if not output_path.exists():
        raise BuildError(f"PyInstaller did not produce {output_path}")
    return output_path


def sha256_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def package_release(app_path: Path, version: str) -> Path:
    release_dir = PROJECT_ROOT / "release_artifacts" / f"v{version}"
    release_dir.mkdir(parents=True, exist_ok=True)

    archive_base = release_dir / f"{APP_NAME}-v{version}-{platform_slug()}"
    zip_path = Path(f"{archive_base}.zip")
    if zip_path.exists():
        safe_remove(zip_path)

    shutil.make_archive(str(archive_base), "zip", root_dir=app_path.parent, base_dir=app_path.name)

    digest = sha256_digest(zip_path)
    checksum_path = release_dir / f"SHA256SUMS-{platform_slug()}.txt"
    checksum_path.write_text(f"{digest}  {zip_path.name}\n", encoding="utf-8")

    notes_path = release_dir / "RELEASE_ARTIFACTS.md"
    notes_path.write_text(
        "\n".join(
            [
                f"# ChromaTsvet v{version} Release Artifacts",
                "",
                "Attach the platform zip files and SHA256SUMS files to the GitHub release.",
                "",
                f"- `{zip_path.name}`: {platform_slug()} application archive",
                f"- `{checksum_path.name}`: checksum for this archive",
                "",
                "This folder is intentionally ignored by git.",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return zip_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build ChromaTsvet release app archive")
    parser.add_argument(
        "--skip-maturin",
        action="store_true",
        help="reuse the already installed spectrometer_rust extension",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    version = read_project_version()
    ensure_rust_extension(skip_maturin=bool(args.skip_maturin))
    icon_path = create_icon()
    app_path = build_app(icon_path)
    zip_path = package_release(app_path, version)
    print(f"Release archive: {zip_path.relative_to(PROJECT_ROOT)}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (BuildError, subprocess.CalledProcessError) as exc:
        print(f"Build failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
