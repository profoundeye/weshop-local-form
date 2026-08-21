#!/usr/bin/env python3
"""Validate every fixed model form, optionally against installed CLI help."""

from __future__ import annotations

import argparse
import shutil
import subprocess

from install_weshop_cli import activate_private_runtime
from weshop_form import CATALOG_PATH, ConfigError, load_model_catalog, validate_config


def preset_flags(preset: dict) -> list[str]:
    flags = [field["flag"] for field in preset.get("fields", [])]
    fixed = preset.get("fixedArgs", [])
    flags.extend(item for item in fixed if isinstance(item, str) and item.startswith("--"))
    return flags


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check-cli", action="store_true")
    args = parser.parse_args()
    catalog = load_model_catalog()
    errors = []
    help_cache = {}
    if args.check_cli:
        activate_private_runtime()
    executable = shutil.which("weshop") if args.check_cli else None
    if args.check_cli and not executable:
        parser.error("weshop CLI was not found")

    for preset_id, preset in sorted(catalog["presets"].items()):
        try:
            validate_config({**preset, "version": 1, "formPreset": preset_id})
        except ConfigError as exc:
            errors.append(f"{preset_id}: {exc}")
            continue
        if not args.check_cli:
            continue
        command = preset["command"]
        if command not in help_cache:
            result = subprocess.run(
                [executable, command, "--help"],
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            if result.returncode != 0:
                errors.append(f"{preset_id}: weshop {command} --help failed")
                continue
            help_cache[command] = result.stdout
        help_text = help_cache[command]
        for flag in preset_flags(preset):
            if flag not in help_text:
                errors.append(f"{preset_id}: {flag} is absent from weshop {command} --help")
        fixed = preset.get("fixedArgs", [])
        for index in range(0, len(fixed) - 1, 2):
            flag, value = fixed[index], fixed[index + 1]
            if isinstance(flag, str) and flag.startswith("--") and str(value) not in help_text:
                errors.append(
                    f"{preset_id}: fixed value {value!r} is absent from weshop {command} --help"
                )
    if errors:
        raise SystemExit("\n".join(errors))
    print(
        f"Validated {len(catalog['presets'])} fixed presets"
        + (f" against {len(help_cache)} CLI commands" if args.check_cli else "")
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
