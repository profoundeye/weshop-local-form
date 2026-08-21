#!/usr/bin/env python3
"""Check or install Node.js and an exact weshop-cli version without a shell."""

from __future__ import annotations

import argparse
import hashlib
import os
import platform
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
import zipfile
from pathlib import Path
from typing import Any


VERSION_RE = re.compile(r"^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$")
NODE_VERSION = "24.19.0"
MIN_NODE_MAJOR = 22
NODE_BASE_URL = "https://nodejs.org/dist"
NODE_DOWNLOAD_PAGE = "https://nodejs.org/en/download"
NODE_SHA256 = {
    "node-v24.19.0-darwin-arm64.tar.gz": "8294b7aa9b03997481c06babf1e8b270c859358f27da57a11509afe537ac381d",
    "node-v24.19.0-darwin-x64.tar.gz": "d1b5e999db158c62fe8f7267a4476b035d8bd93b1a605bac24a3f0dd166e3316",
    "node-v24.19.0-linux-arm64.tar.xz": "01443c1e1a29e531ccad5a46fefa6df490d2189c49f7955904aecdbb0fe86fdc",
    "node-v24.19.0-linux-x64.tar.xz": "14b342e71204f811bde6153be8e04b62aef63c236fef92b55f9c83154b409647",
    "node-v24.19.0-win-arm64.zip": "8502f4a50b458d4cc38ed8f2001556c2cd239d464920f74017926ccb1e1c157f",
    "node-v24.19.0-win-x64.zip": "57f71ab3652e797d84acddc79c81cc9ff1c6ddb2a1974cdb83f00fee9bff4c73",
}


class InstallError(RuntimeError):
    pass


def runtime_base() -> Path:
    override = os.environ.get("WESHOP_FORM_RUNTIME_DIR")
    if override:
        return Path(override).expanduser().resolve()
    system = platform.system()
    if system == "Windows":
        parent = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    elif system == "Darwin":
        parent = Path.home() / "Library" / "Caches"
    else:
        parent = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    return parent / "weshop-local-form"


def node_root(version: str = NODE_VERSION) -> Path:
    return runtime_base() / f"node-v{version}"


def npm_prefix() -> Path:
    return runtime_base() / "npm"


def node_bin_dir(root: Path | None = None) -> Path:
    root = root or node_root()
    return root if platform.system() == "Windows" else root / "bin"


def npm_bin_dir(prefix: Path | None = None) -> Path:
    prefix = prefix or npm_prefix()
    return prefix if platform.system() == "Windows" else prefix / "bin"


def prepend_path(path: Path) -> None:
    value = str(path)
    entries = os.environ.get("PATH", "").split(os.pathsep)
    if value not in entries:
        os.environ["PATH"] = value + os.pathsep + os.environ.get("PATH", "")


def activate_private_runtime() -> None:
    if node_root().exists():
        prepend_path(node_bin_dir())
    if npm_prefix().exists():
        prepend_path(npm_bin_dir())


def command_version(command: str, timeout: int = 15) -> str | None:
    executable = shutil.which(command)
    if not executable:
        return None
    try:
        result = subprocess.run(
            [executable, "--version"],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout.strip() if result.returncode == 0 else None


def major_version(value: str | None) -> int | None:
    match = re.match(r"^v?(\d+)(?:\.|$)", value or "")
    return int(match.group(1)) if match else None


def current_version() -> str | None:
    activate_private_runtime()
    return command_version("weshop")


def dependency_status(cli_version: str = "0.2.12") -> dict[str, Any]:
    activate_private_runtime()
    node = command_version("node")
    npm = command_version("npm")
    cli = command_version("weshop")
    node_major = major_version(node)
    return {
        "ready": cli == cli_version and npm is not None and node_major is not None and node_major >= MIN_NODE_MAJOR,
        "node": node,
        "nodeSupported": node_major is not None and node_major >= MIN_NODE_MAJOR,
        "npm": npm,
        "weshopCli": cli,
        "requiredWeshopCli": cli_version,
        "privateRuntime": str(runtime_base()),
    }


def node_distribution(
    system: str | None = None,
    machine: str | None = None,
    version: str = NODE_VERSION,
) -> tuple[str, str]:
    system = system or platform.system()
    machine = (machine or platform.machine()).lower()
    architecture = {
        "x86_64": "x64",
        "amd64": "x64",
        "aarch64": "arm64",
        "arm64": "arm64",
    }.get(machine)
    if not architecture:
        raise InstallError(
            f"Unsupported CPU architecture {machine!r}. Install Node.js from {NODE_DOWNLOAD_PAGE}."
        )
    if system == "Darwin":
        return f"node-v{version}-darwin-{architecture}.tar.gz", "tar"
    if system == "Linux":
        return f"node-v{version}-linux-{architecture}.tar.xz", "tar"
    if system == "Windows":
        return f"node-v{version}-win-{architecture}.zip", "zip"
    raise InstallError(
        f"Unsupported operating system {system!r}. Install Node.js from {NODE_DOWNLOAD_PAGE}."
    )


def download(url: str, destination: Path) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": "weshop-local-form/1"})
    try:
        with urllib.request.urlopen(request, timeout=120) as response, destination.open("wb") as out:
            shutil.copyfileobj(response, out)
    except Exception as exc:
        raise InstallError(f"Could not download {url}: {exc}") from exc


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def ensure_within(base: Path, member_name: str) -> None:
    base = base.resolve()
    target = (base / member_name).resolve()
    if target != base and base not in target.parents:
        raise InstallError(f"Unsafe archive member: {member_name}")


def extract_archive(archive: Path, kind: str, destination: Path) -> Path:
    destination.mkdir(parents=True, exist_ok=True)
    if kind == "tar":
        with tarfile.open(archive) as bundle:
            members = bundle.getmembers()
            for member in members:
                ensure_within(destination, member.name)
            bundle.extractall(destination)
    else:
        with zipfile.ZipFile(archive) as bundle:
            for member in bundle.infolist():
                ensure_within(destination, member.filename)
            bundle.extractall(destination)
    roots = [path for path in destination.iterdir() if path.is_dir()]
    if len(roots) != 1:
        raise InstallError("Node.js archive did not contain exactly one root directory")
    return roots[0]


def install_private_node(version: str = NODE_VERSION) -> Path:
    final_root = node_root(version)
    node_name = "node.exe" if platform.system() == "Windows" else "node"
    existing_node = node_bin_dir(final_root) / node_name
    if existing_node.exists():
        activate_private_runtime()
        return final_root

    base = runtime_base()
    base.mkdir(parents=True, exist_ok=True)
    filename, archive_kind = node_distribution(version=version)
    release_url = f"{NODE_BASE_URL}/v{version}"
    print(
        f"Node.js was not found. Installing private Node.js v{version} from nodejs.org…",
        flush=True,
    )
    with tempfile.TemporaryDirectory(prefix="node-install-", dir=base) as temp_name:
        temp_dir = Path(temp_name)
        archive = temp_dir / filename
        download(f"{release_url}/{filename}", archive)
        expected = NODE_SHA256.get(filename)
        if not expected:
            raise InstallError(f"No pinned official checksum is available for {filename}")
        actual = sha256(archive)
        if actual != expected:
            raise InstallError(
                f"Node.js archive checksum mismatch for {filename}; expected {expected}, got {actual}"
            )
        extracted = extract_archive(archive, archive_kind, temp_dir / "extracted")
        if final_root.exists():
            shutil.rmtree(final_root)
        shutil.move(str(extracted), final_root)
    if not existing_node.exists():
        raise InstallError(f"Node.js installation completed but {existing_node} is missing")
    activate_private_runtime()
    print(f"Private Node.js v{version} is ready at {final_root}", flush=True)
    return final_root


def ensure_node_and_npm(install: bool) -> tuple[str, str]:
    activate_private_runtime()
    node = command_version("node")
    npm = command_version("npm")
    node_major = major_version(node)
    if node_major is not None and node_major >= MIN_NODE_MAJOR and npm:
        return node, npm
    if not install:
        found = node or "not installed"
        raise InstallError(
            f"Node.js {MIN_NODE_MAJOR}+ with npm is required; current Node.js: {found}."
        )
    install_private_node()
    node = command_version("node")
    npm = command_version("npm")
    node_major = major_version(node)
    if node_major is None or node_major < MIN_NODE_MAJOR or not npm:
        raise InstallError(
            f"Private Node.js installation did not provide Node.js {MIN_NODE_MAJOR}+ and npm."
        )
    return node, npm


def ensure_weshop_cli(version: str = "0.2.12", install: bool = True) -> dict[str, Any]:
    if not VERSION_RE.fullmatch(version):
        raise InstallError("version must be semantic, such as 0.2.12")
    activate_private_runtime()
    installed = current_version()
    status = dependency_status(version)
    if status["ready"]:
        return status
    if not install:
        raise InstallError(
            f"Dependencies are not ready: Node.js={status['node'] or 'missing'}, "
            f"npm={status['npm'] or 'missing'}, "
            f"weshop-cli={status['weshopCli'] or 'missing'}"
        )

    ensure_node_and_npm(install=True)
    if installed == version:
        return dependency_status(version)
    npm = shutil.which("npm")
    if not npm:
        raise InstallError("npm is unavailable after Node.js installation")
    prefix = npm_prefix()
    prefix.mkdir(parents=True, exist_ok=True)
    npm_cache = runtime_base() / "npm-cache"
    npm_cache.mkdir(parents=True, exist_ok=True)
    package = f"weshop-cli@{version}"
    print(f"Installing {package} into private runtime…", flush=True)
    npm_environment = dict(os.environ)
    npm_environment["npm_config_cache"] = str(npm_cache)
    npm_environment["npm_config_update_notifier"] = "false"
    result = subprocess.run(
        [
            npm,
            "install",
            "--global",
            "--prefix",
            str(prefix),
            "--no-audit",
            "--no-fund",
            package,
        ],
        env=npm_environment,
        check=False,
    )
    if result.returncode != 0:
        raise InstallError(f"npm failed to install {package} (exit {result.returncode})")
    activate_private_runtime()
    installed = current_version()
    if installed != version:
        raise InstallError(
            f"Installation finished but weshop --version returned {installed or 'nothing'}"
        )
    print(f"weshop-cli {installed} is ready", flush=True)
    return dependency_status(version)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--install", action="store_true")
    parser.add_argument("--version", default="0.2.12")
    args = parser.parse_args()

    if not VERSION_RE.fullmatch(args.version):
        parser.error("--version must be a semantic version such as 0.2.12")
    if args.check:
        status = dependency_status(args.version)
        if status["ready"]:
            print(f"weshop-cli {args.version} is ready")
            return 0
        print(
            f"Dependencies are not ready: Node.js={status['node'] or 'missing'}, "
            f"npm={status['npm'] or 'missing'}, "
            f"weshop-cli={status['weshopCli'] or 'missing'}"
        )
        return 1
    try:
        ensure_weshop_cli(args.version, install=True)
    except InstallError as exc:
        print(f"Installation failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
