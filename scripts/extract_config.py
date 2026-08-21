#!/usr/bin/env python3
"""Extract and sanitize a JSON or safe YAML-subset configuration from text."""

from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path
from typing import Any


FENCE_RE = re.compile(r"```(?:json|yaml|yml)?\s*\n(.*?)```", re.DOTALL | re.IGNORECASE)
SECRET_KEYS = {"apikey", "weshopapikey", "weshop_api_key"}
SECRET_CONTAINERS = {"secrets", "env"}


class ParseError(ValueError):
    pass


def balanced_objects(text: str):
    start = None
    depth = 0
    in_string = False
    escaped = False
    for index, char in enumerate(text):
        if start is None:
            if char == "{":
                start = index
                depth = 1
            continue
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                yield text[start : index + 1]
                start = None


def strip_yaml_comment(value: str) -> str:
    quote = None
    escaped = False
    for index, char in enumerate(value):
        if escaped:
            escaped = False
            continue
        if char == "\\" and quote == '"':
            escaped = True
            continue
        if char in {"'", '"'}:
            if quote is None:
                quote = char
            elif quote == char:
                quote = None
        elif char == "#" and quote is None and (index == 0 or value[index - 1].isspace()):
            return value[:index].rstrip()
    return value.rstrip()


def yaml_scalar(raw: str) -> Any:
    value = strip_yaml_comment(raw).strip()
    if not value:
        return ""
    if value.startswith(("!", "&", "*")):
        raise ParseError("YAML tags, anchors, and aliases are not supported")
    lowered = value.lower()
    if lowered in {"null", "~"}:
        return None
    if lowered in {"true", "false"}:
        return lowered == "true"
    if re.fullmatch(r"[-+]?\d+", value):
        return int(value)
    if re.fullmatch(r"[-+]?(?:\d+\.\d*|\d*\.\d+)(?:[eE][-+]?\d+)?", value):
        return float(value)
    if value.startswith('"') and value.endswith('"'):
        try:
            return json.loads(value)
        except json.JSONDecodeError as exc:
            raise ParseError(f"invalid double-quoted YAML scalar: {exc.msg}") from exc
    if value.startswith("'") and value.endswith("'"):
        return value[1:-1].replace("''", "'")
    if value.startswith(("[", "{")):
        try:
            return json.loads(value)
        except json.JSONDecodeError as exc:
            raise ParseError("inline YAML arrays and objects must use JSON syntax") from exc
    return value


def split_yaml_mapping(content: str, line_number: int) -> tuple[str, str]:
    quote = None
    escaped = False
    for index, char in enumerate(content):
        if escaped:
            escaped = False
            continue
        if char == "\\" and quote == '"':
            escaped = True
            continue
        if char in {"'", '"'}:
            if quote is None:
                quote = char
            elif quote == char:
                quote = None
        elif char == ":" and quote is None:
            key = content[:index].strip()
            if not key:
                break
            return key, content[index + 1 :].strip()
    raise ParseError(f"YAML line {line_number} must contain a mapping key followed by ':'")


def yaml_lines(text: str) -> list[tuple[int, str, int]]:
    result = []
    for number, raw in enumerate(text.splitlines(), 1):
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        if "\t" in raw[: len(raw) - len(raw.lstrip())]:
            raise ParseError(f"YAML line {number} uses tabs for indentation")
        content = raw.lstrip(" ")
        if content in {"---", "..."}:
            continue
        if content.startswith(("|", ">")):
            raise ParseError(f"YAML line {number} uses an unsupported block scalar")
        result.append((len(raw) - len(content), content, number))
    if not result:
        raise ParseError("YAML document is empty")
    return result


def parse_yaml_subset(text: str) -> Any:
    lines = yaml_lines(text)

    def parse_block(index: int, indent: int) -> tuple[Any, int]:
        if index >= len(lines) or lines[index][0] < indent:
            raise ParseError("YAML has a missing nested value")
        is_list = lines[index][0] == indent and lines[index][1].startswith("-")
        collection: Any = [] if is_list else {}
        while index < len(lines):
            current_indent, content, line_number = lines[index]
            if current_indent < indent:
                break
            if current_indent > indent:
                raise ParseError(f"unexpected indentation on YAML line {line_number}")
            if is_list:
                if not content.startswith("-"):
                    break
                remainder = content[1:].strip()
                if not remainder:
                    child, index = parse_block(index + 1, next_indent(index + 1, indent))
                    collection.append(child)
                    continue
                if ":" in remainder:
                    key, raw_value = split_yaml_mapping(remainder, line_number)
                    item = {}
                    if raw_value:
                        item[key] = yaml_scalar(raw_value)
                        index += 1
                    else:
                        child, index = parse_block(index + 1, next_indent(index + 1, indent))
                        item[key] = child
                    while index < len(lines) and lines[index][0] > indent:
                        child_indent, child_content, child_line = lines[index]
                        if child_content.startswith("-"):
                            break
                        child_key, child_raw = split_yaml_mapping(child_content, child_line)
                        if child_key in item:
                            raise ParseError(f"duplicate YAML key {child_key!r} on line {child_line}")
                        if child_raw:
                            item[child_key] = yaml_scalar(child_raw)
                            index += 1
                        else:
                            child, index = parse_block(
                                index + 1, next_indent(index + 1, child_indent)
                            )
                            item[child_key] = child
                    collection.append(item)
                    continue
                collection.append(yaml_scalar(remainder))
                index += 1
                continue
            if content.startswith("-"):
                break
            key, raw_value = split_yaml_mapping(content, line_number)
            if key in collection:
                raise ParseError(f"duplicate YAML key {key!r} on line {line_number}")
            if raw_value:
                collection[key] = yaml_scalar(raw_value)
                index += 1
            else:
                child, index = parse_block(index + 1, next_indent(index + 1, indent))
                collection[key] = child
        return collection, index

    def next_indent(index: int, parent_indent: int) -> int:
        if index >= len(lines) or lines[index][0] <= parent_indent:
            raise ParseError("YAML has a missing nested block")
        return lines[index][0]

    value, final_index = parse_block(0, lines[0][0])
    if final_index != len(lines):
        raise ParseError(f"could not parse YAML near line {lines[final_index][2]}")
    return value


def parse_candidate(candidate: str) -> Any:
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        return parse_yaml_subset(candidate)


def normalize_secret_key(key: str) -> str:
    return re.sub(r"[^a-z0-9_]", "", key.lower())


def pop_api_key(config: dict) -> str | None:
    found = []
    for key in list(config):
        normalized = normalize_secret_key(str(key))
        if normalized in SECRET_KEYS:
            found.append(config.pop(key))
        elif normalized in SECRET_CONTAINERS and isinstance(config[key], dict):
            container = config[key]
            for nested_key in list(container):
                if normalize_secret_key(str(nested_key)) in SECRET_KEYS:
                    found.append(container.pop(nested_key))
            if not container:
                config.pop(key)
    values = [str(value).strip() for value in found if value is not None and str(value).strip()]
    if len(values) > 1 and len(set(values)) > 1:
        raise ParseError("configuration contains conflicting WeShop API keys")
    return values[0] if values else None


def extract_with_secret(text: str) -> tuple[dict, str | None]:
    candidates = [match.group(1).strip() for match in FENCE_RE.finditer(text)]
    candidates.extend(balanced_objects(text))
    candidates.append(text.strip())
    errors = []
    for candidate in candidates:
        if not candidate:
            continue
        try:
            value = parse_candidate(candidate)
        except (json.JSONDecodeError, ParseError, ValueError) as exc:
            errors.append(str(exc))
            continue
        if not isinstance(value, dict):
            errors.append("configuration value is not an object")
            continue
        config = dict(value)
        api_key = pop_api_key(config)
        return config, api_key
    detail = f" Last parser error: {errors[-1]}" if errors else ""
    raise ParseError("No valid JSON or supported YAML configuration was found." + detail)


def extract(text: str) -> dict:
    config, _ = extract_with_secret(text)
    return config


def write_private_json(path: Path, config: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    os.fchmod(descriptor, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        json.dump(config, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    config, api_key = extract_with_secret(args.input.read_text(encoding="utf-8"))
    write_private_json(args.output, config)
    print(f"Extracted sanitized configuration to {args.output}")
    print(f"WeShop API key: {'present and removed' if api_key else 'not present'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
