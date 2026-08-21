#!/usr/bin/env python3
"""Start a WeShop form from secret-bearing JSON/YAML text without persisting the key."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from extract_config import ParseError, extract_with_secret, write_private_json
from install_weshop_cli import InstallError, dependency_status, ensure_weshop_cli
from weshop_form import (
    ConfigError,
    emit_event,
    load_account_error_catalog,
    resolve_preset_request,
    serve,
)


def fail(code: str, message: str, exit_code: int = 2, action_url: str | None = None) -> int:
    fields = {"code": code, "message": message}
    if action_url:
        fields["actionUrl"] = action_url
    emit_event("error", **fields)
    print(f"{code}: {message}", file=sys.stderr, flush=True)
    return exit_code


def read_input(source: str) -> str:
    if source == "-":
        return sys.stdin.read()
    return Path(source).read_text(encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        required=True,
        help="Path to prose/configuration text, or - to read it from standard input",
    )
    parser.add_argument(
        "--sanitized-config",
        type=Path,
        help="Optional 0600 JSON output with all recognized API-key fields removed",
    )
    parser.add_argument(
        "--delete-input",
        action="store_true",
        help="Delete the input file after reading it; use only for a temporary file created for this run",
    )
    parser.add_argument("--check", action="store_true")
    parser.add_argument(
        "--no-install",
        action="store_true",
        help="Fail instead of installing missing Node.js/npm/weshop-cli dependencies",
    )
    parser.add_argument(
        "--no-open-browser",
        action="store_true",
        help="Start the local server without opening the form in the default browser",
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()

    if args.delete_input and args.input == "-":
        return fail("invalid_arguments", "--delete-input cannot be used with standard input")
    try:
        input_text = read_input(args.input)
    except OSError as exc:
        return fail("input_read_failed", str(exc))
    if args.delete_input and args.input != "-":
        try:
            Path(args.input).unlink(missing_ok=True)
        except OSError as exc:
            return fail("temporary_input_cleanup_failed", str(exc))
    try:
        request, supplied_key = extract_with_secret(input_text)
        config = resolve_preset_request(request)
        load_account_error_catalog()
    except (ParseError, ConfigError) as exc:
        return fail("invalid_configuration", str(exc))

    existing_key = os.environ.get("WESHOP_API_KEY")
    if supplied_key and existing_key and supplied_key != existing_key:
        return fail(
            "api_key_conflict",
            "input API key conflicts with the existing WESHOP_API_KEY environment variable",
        )
    api_key = supplied_key or existing_key
    if not api_key:
        return fail(
            "api_key_missing",
            "no WeShop API key was found in the input or WESHOP_API_KEY environment variable",
            action_url="https://open.weshop.ai/authorization/apikey",
        )
    if args.sanitized_config:
        write_private_json(args.sanitized_config, config)
    if args.check:
        dependencies = dependency_status(config["cliVersion"])
        emit_event(
            "check",
            ok=True,
            title=config["title"],
            command=config["command"],
            cliVersion=config["cliVersion"],
            fieldCount=len(config["fields"]),
            apiKey="present",
            dependencies=dependencies,
        )
        return 0

    try:
        ensure_weshop_cli(config["cliVersion"], install=not args.no_install)
    except InstallError as exc:
        return fail("dependency_install_failed", str(exc), exit_code=1)
    os.environ["WESHOP_API_KEY"] = api_key
    try:
        return serve(
            config,
            args.host,
            args.port,
            open_browser=not args.no_open_browser,
        )
    except (ConfigError, OSError) as exc:
        return fail("server_start_failed", str(exc), exit_code=1)


if __name__ == "__main__":
    raise SystemExit(main())
