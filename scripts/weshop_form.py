#!/usr/bin/env python3
"""Serve a localized form that invokes the WeShop CLI without a shell."""

from __future__ import annotations

import argparse
import copy
import hmac
import html
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import tempfile
import time
import webbrowser
from email.parser import BytesParser
from email.policy import default as email_policy
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote, urlparse


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
from install_weshop_cli import InstallError, activate_private_runtime, ensure_weshop_cli


COMMAND_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]*$")
FLAG_RE = re.compile(r"^--[a-z0-9][a-z0-9-]*$")
NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]*$")
VERSION_RE = re.compile(r"^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$")
FIELD_TYPES = {"text", "textarea", "number", "select", "checkbox", "file", "url-list"}
FORBIDDEN_ARG_RE = re.compile(r"api[-_]?key|authorization|bearer", re.IGNORECASE)
SHELL_TOKENS = {";", "&&", "||", "|", ">", ">>", "<", "`", "$("}
CATALOG_PATH = Path(__file__).resolve().parent.parent / "references" / "model-forms.json"
ACCOUNT_ERRORS_PATH = Path(__file__).resolve().parent.parent / "references" / "account-errors.json"
DEFAULT_PRESET_ID = "qwen-edit"
EVENT_PREFIX = "WESHOP_FORM_EVENT "
PRESET_REQUEST_KEYS = {
    "version",
    "formPreset",
    "locale",
    "defaults",
    "timeoutSeconds",
    "pollSeconds",
}
MINIMAL_AGENT_REQUEST_KEYS = {
    "agentName",
    "safeGenerate",
    "resultBase64",
}
MINIMAL_AGENT_REQUIRED_KEYS = {
    "agentName",
}
MINIMAL_AGENT_PRESETS = {
    "z-image": "z-image",
    "qwen-edit": "qwen-edit",
    "qwen-image-edit": "qwen-edit",
}

UI_DEFAULTS = {
    "zh-CN": {
        "submit": "提交生成",
        "submitting": "正在生成，请勿关闭页面…",
        "result": "生成结果",
        "error": "提交失败",
        "rawOutput": "CLI 原始输出",
        "apiKeyMissing": "未检测到 WESHOP_API_KEY，请先在启动表单的环境中设置。",
        "back": "返回表单",
        "errorCode": "错误码",
    },
    "en-US": {
        "submit": "Generate",
        "submitting": "Generating—keep this page open…",
        "result": "Generated result",
        "error": "Submission failed",
        "rawOutput": "Raw CLI output",
        "apiKeyMissing": "WESHOP_API_KEY is not set in the form server environment.",
        "back": "Back to form",
        "errorCode": "Error code",
    },
}

STYLE = """
:root{color-scheme:light dark;--card:#fff;--text:#18212f;--muted:#657084;--line:#dfe5ee;--accent:#6c4dff;--accent2:#5034d9;--danger:#b42318}*{box-sizing:border-box}body{margin:0;background:linear-gradient(135deg,#eef2ff,#f8fafc 45%,#f2fbf8);color:var(--text);font:16px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}.wrap{width:min(860px,calc(100% - 32px));margin:48px auto}.card{background:var(--card);border:1px solid var(--line);border-radius:20px;box-shadow:0 16px 50px rgba(31,42,68,.10);padding:28px}h1{font-size:clamp(26px,5vw,38px);line-height:1.15;margin:0 0 10px}.model-picker{margin:0 0 14px}.model-picker label{color:var(--muted);font-size:13px;font-weight:700;letter-spacing:.08em;text-transform:uppercase}.model-selector{font-size:clamp(25px,4.5vw,38px);font-weight:800;line-height:1.15;padding:12px 46px 12px 14px;border:1px solid var(--line);border-radius:14px;background-color:transparent;cursor:pointer}.model-selector:focus{outline:3px solid color-mix(in srgb,var(--accent) 25%,transparent);border-color:var(--accent)}p.intro,.help{color:var(--muted)}.field{margin:22px 0}label{display:block;font-weight:650;margin-bottom:8px}input,textarea,select{width:100%;border:1px solid #cbd4e1;border-radius:11px;background:#fff;color:#18212f;font:inherit;padding:11px 13px}textarea{min-height:130px;resize:vertical}input[type=file]{padding:9px}.check{display:flex;gap:10px;align-items:center}.check input{width:auto}.required{color:var(--danger)}button{border:0;border-radius:12px;background:var(--accent);color:#fff;font:inherit;font-weight:700;padding:12px 20px;cursor:pointer}button:hover{background:var(--accent2)}button:disabled{opacity:.6;cursor:wait}.notice{border-radius:12px;padding:12px 14px;background:#fff4e5;color:#7a4d00;margin:18px 0}.error{border-radius:12px;padding:14px;background:#fff0ee;color:var(--danger);white-space:pre-wrap}.action{display:inline-block;margin-top:16px;border-radius:12px;background:var(--accent);color:#fff;padding:11px 17px;text-decoration:none;font-weight:700}.action:hover{background:var(--accent2)}.gallery{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:16px;margin-top:18px}.media{border:1px solid var(--line);border-radius:14px;overflow:hidden;background:#111}.media img,.media video{display:block;width:100%;height:auto;max-height:640px;object-fit:contain}details{margin-top:22px}pre{overflow:auto;padding:14px;border-radius:12px;background:#111827;color:#e5e7eb;white-space:pre-wrap;word-break:break-word}.meta{color:var(--muted);font-size:14px}.back{display:inline-block;margin-top:20px;color:var(--accent);text-decoration:none;font-weight:650}@media(prefers-color-scheme:dark){:root{--card:#151d2a;--text:#eef2f7;--muted:#9ba7b9;--line:#2a3545}body{background:linear-gradient(135deg,#15132b,#0c111b 50%,#0d1b1a)}input,textarea,select{background:#0f1722;color:#eef2f7;border-color:#39475a}.model-selector{background-color:#0f1722}.notice{background:#342a10;color:#ffd98a}}
"""


class ConfigError(ValueError):
    pass


def emit_event(event: str, **fields: Any) -> None:
    payload = {"event": event, **fields}
    print(EVENT_PREFIX + json.dumps(payload, ensure_ascii=False, sort_keys=True), flush=True)


def load_model_catalog(path: Path = CATALOG_PATH) -> dict:
    try:
        catalog = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ConfigError(f"model form catalog not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ConfigError(
            f"invalid model form catalog at line {exc.lineno}, column {exc.colno}: {exc.msg}"
        ) from exc
    if not isinstance(catalog, dict) or catalog.get("schemaVersion") != 1:
        raise ConfigError("model form catalog schemaVersion must be 1")
    presets = catalog.get("presets")
    if not isinstance(presets, dict) or not presets:
        raise ConfigError("model form catalog must contain presets")
    return catalog


def load_account_error_catalog(path: Path = ACCOUNT_ERRORS_PATH) -> dict:
    try:
        catalog = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ConfigError(f"account error catalog not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ConfigError(
            f"invalid account error catalog at line {exc.lineno}, column {exc.colno}: {exc.msg}"
        ) from exc
    if not isinstance(catalog, dict) or catalog.get("schemaVersion") != 1:
        raise ConfigError("account error catalog schemaVersion must be 1")
    rules = catalog.get("rules")
    if not isinstance(rules, list) or not rules:
        raise ConfigError("account error catalog must contain rules")
    for index, rule in enumerate(rules):
        if not isinstance(rule, dict) or not isinstance(rule.get("kind"), str):
            raise ConfigError(f"account error rule {index} is invalid")
        if not isinstance(rule.get("codes"), list) or not all(
            isinstance(code, str) for code in rule["codes"]
        ):
            raise ConfigError(f"account error rule {index}.codes must be strings")
        if not isinstance(rule.get("patterns"), list) or not all(
            isinstance(pattern, str) for pattern in rule["patterns"]
        ):
            raise ConfigError(f"account error rule {index}.patterns must be strings")
        try:
            for pattern in rule["patterns"]:
                re.compile(pattern, re.IGNORECASE)
        except re.error as exc:
            raise ConfigError(f"account error rule {index} has invalid regex: {exc}") from exc
        if not isinstance(rule.get("httpStatus"), int) or not 400 <= rule["httpStatus"] < 500:
            raise ConfigError(f"account error rule {index}.httpStatus must be 4xx")
        action_url = rule.get("actionUrl")
        if not isinstance(action_url, str) or urlparse(action_url).scheme not in {"https", "mailto"}:
            raise ConfigError(f"account error rule {index}.actionUrl must use https or mailto")
    return catalog


def resolve_preset_request(request: Any, catalog_path: Path = CATALOG_PATH) -> dict:
    if not isinstance(request, dict):
        raise ConfigError("configuration must be a JSON/YAML object")
    if "safeGenerat" in request:
        raise ConfigError("safeGenerat is misspelled; use safeGenerate")
    if not request:
        request = {"version": 1, "formPreset": DEFAULT_PRESET_ID}
    safe_generate = None
    if "agentName" in request:
        extra = set(request) - MINIMAL_AGENT_REQUEST_KEYS
        if extra:
            raise ConfigError(
                "minimal agent requests accept only agentName, safeGenerate, "
                "resultBase64, "
                "and a recognized API-key field; unsupported keys: "
                + ", ".join(sorted(extra))
            )
        missing = MINIMAL_AGENT_REQUIRED_KEYS - set(request)
        if missing:
            raise ConfigError(
                "minimal agent request is missing: " + ", ".join(sorted(missing))
            )
        preset_id = MINIMAL_AGENT_PRESETS.get(request["agentName"])
        if preset_id is None:
            available = ", ".join(sorted(MINIMAL_AGENT_PRESETS))
            raise ConfigError(f"unsupported agentName; available agents: {available}")
        if "safeGenerate" not in request:
            raise ConfigError("minimal agent request requires safeGenerate")
        if request["safeGenerate"] != "off":
            raise ConfigError("minimal agent request requires safeGenerate to be the string 'off'")
        safe_generate = request["safeGenerate"]
        if "resultBase64" in request and request["resultBase64"] is not True:
            raise ConfigError("minimal agent request requires resultBase64 to be true")
        request = {"version": 1, "formPreset": preset_id}
    if request.get("version") != 1:
        raise ConfigError("version must be 1")
    extra = set(request) - PRESET_REQUEST_KEYS
    if extra:
        raise ConfigError(
            "preset requests may not redefine form structure; unsupported keys: "
            + ", ".join(sorted(extra))
        )
    preset_id = request.get("formPreset")
    if not isinstance(preset_id, str) or not COMMAND_RE.fullmatch(preset_id):
        raise ConfigError("formPreset must be a preset ID containing letters, numbers, and hyphens")
    catalog = load_model_catalog(catalog_path)
    preset = catalog["presets"].get(preset_id)
    if not isinstance(preset, dict):
        available = ", ".join(sorted(catalog["presets"]))
        raise ConfigError(f"unknown formPreset {preset_id!r}; available presets: {available}")
    resolved = copy.deepcopy(preset)
    resolved["version"] = 1
    resolved["formPreset"] = preset_id
    if safe_generate is not None:
        resolved["safeGenerate"] = safe_generate
    requested_locale = request.get("locale", resolved.get("locale", "zh-CN"))
    if requested_locale != resolved.get("locale", "zh-CN"):
        raise ConfigError(
            f"formPreset {preset_id!r} is fixed for locale {resolved.get('locale', 'zh-CN')}"
        )
    for key in ("timeoutSeconds", "pollSeconds"):
        if key in request:
            resolved[key] = request[key]
    defaults = request.get("defaults", {})
    if not isinstance(defaults, dict):
        raise ConfigError("defaults must be an object keyed by preset field name")
    field_map = {field.get("name"): field for field in resolved.get("fields", [])}
    unknown_defaults = set(defaults) - set(field_map)
    if unknown_defaults:
        raise ConfigError(
            "defaults contains unknown preset fields: " + ", ".join(sorted(unknown_defaults))
        )
    for name, value in defaults.items():
        field = field_map[name]
        if field.get("type") == "file":
            raise ConfigError(f"defaults.{name} is not allowed for file fields")
        field["default"] = value
    return validate_config(resolved)


def option_pairs(options: Any, path: str) -> list[tuple[str, str]]:
    if not isinstance(options, list) or not options:
        raise ConfigError(f"{path}.options must be a non-empty array")
    result = []
    for index, option in enumerate(options):
        if isinstance(option, (str, int, float, bool)):
            value = str(option).lower() if isinstance(option, bool) else str(option)
            result.append((value, value))
        elif isinstance(option, dict) and "value" in option and "label" in option:
            result.append((str(option["value"]), str(option["label"])))
        else:
            raise ConfigError(f"{path}.options[{index}] must be a scalar or value/label object")
    return result


def validate_config(config: Any) -> dict:
    if not isinstance(config, dict):
        raise ConfigError("configuration must be a JSON object")
    if config.get("version") != 1:
        raise ConfigError("version must be 1")
    for key in ("title", "command", "fields"):
        if key not in config:
            raise ConfigError(f"missing required key: {key}")
    if not isinstance(config["title"], str) or not config["title"].strip():
        raise ConfigError("title must be a non-empty string")
    if not isinstance(config["command"], str) or not COMMAND_RE.fullmatch(config["command"]):
        raise ConfigError("command may contain only letters, numbers, and hyphens")
    cli_version = config.get("cliVersion", "0.2.12")
    if not isinstance(cli_version, str) or not VERSION_RE.fullmatch(cli_version):
        raise ConfigError("cliVersion must be a semantic version such as 0.2.12")
    fields = config["fields"]
    if not isinstance(fields, list) or not fields:
        raise ConfigError("fields must be a non-empty array")
    names = set()
    for index, field in enumerate(fields):
        path = f"fields[{index}]"
        if not isinstance(field, dict):
            raise ConfigError(f"{path} must be an object")
        for key in ("name", "label", "type", "flag"):
            if key not in field:
                raise ConfigError(f"{path} is missing {key}")
        name = field["name"]
        if not isinstance(name, str) or not NAME_RE.fullmatch(name):
            raise ConfigError(f"{path}.name is invalid")
        if name in names:
            raise ConfigError(f"duplicate field name: {name}")
        names.add(name)
        if not isinstance(field["label"], str) or not field["label"].strip():
            raise ConfigError(f"{path}.label must be a non-empty string")
        if field["type"] not in FIELD_TYPES:
            raise ConfigError(f"{path}.type must be one of {sorted(FIELD_TYPES)}")
        flag = field["flag"]
        if not isinstance(flag, str) or not FLAG_RE.fullmatch(flag):
            raise ConfigError(f"{path}.flag must be a lowercase long CLI flag")
        if FORBIDDEN_ARG_RE.search(flag):
            raise ConfigError(f"{path}.flag is forbidden")
        if field["type"] == "select":
            allowed = option_pairs(field.get("options"), path)
            if "default" in field and str(field["default"]) not in {value for value, _ in allowed}:
                raise ConfigError(f"{path}.default is not present in options")
        if field["type"] == "file":
            if "default" in field:
                raise ConfigError(f"{path}.default is not allowed for file fields")
            max_files = field.get("maxFiles", 10 if field.get("multiple") else 1)
            if not isinstance(max_files, int) or not 1 <= max_files <= 30:
                raise ConfigError(f"{path}.maxFiles must be an integer from 1 to 30")
        if field["type"] == "url-list":
            max_items = field.get("maxItems", 10)
            if not isinstance(max_items, int) or not 1 <= max_items <= 30:
                raise ConfigError(f"{path}.maxItems must be an integer from 1 to 30")
        if field["type"] == "number":
            for numeric_key in ("min", "max", "step"):
                if numeric_key in field and not isinstance(field[numeric_key], (int, float)):
                    raise ConfigError(f"{path}.{numeric_key} must be numeric")
    fixed_args = config.get("fixedArgs", [])
    if not isinstance(fixed_args, list) or not all(isinstance(item, str) for item in fixed_args):
        raise ConfigError("fixedArgs must be an array of strings")
    for item in fixed_args:
        if FORBIDDEN_ARG_RE.search(item) or item in SHELL_TOKENS or "\x00" in item:
            raise ConfigError(f"fixedArgs contains a forbidden token: {item!r}")
    safe_generate = config.get("safeGenerate")
    if safe_generate is not None and safe_generate != "off":
        raise ConfigError("safeGenerate must be the string 'off'")
    for key, low, high, fallback in (
        ("timeoutSeconds", 30, 7200, 1800),
        ("pollSeconds", 1, 30, 3),
    ):
        value = config.get(key, fallback)
        if not isinstance(value, (int, float)) or not low <= value <= high:
            raise ConfigError(f"{key} must be between {low} and {high}")
    config = dict(config)
    config["cliVersion"] = cli_version
    config["timeoutSeconds"] = float(config.get("timeoutSeconds", 1800))
    config["pollSeconds"] = float(config.get("pollSeconds", 3))
    return config


def load_config(path: Path) -> dict:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ConfigError(f"configuration file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ConfigError(f"invalid JSON at line {exc.lineno}, column {exc.colno}: {exc.msg}") from exc
    return resolve_preset_request(raw)


def ui_text(config: dict) -> dict[str, str]:
    locale = config.get("locale", "zh-CN")
    base = dict(UI_DEFAULTS.get(locale, UI_DEFAULTS["en-US"]))
    overrides = config.get("ui", {})
    if isinstance(overrides, dict):
        for key in base:
            if isinstance(overrides.get(key), str):
                base[key] = overrides[key]
    return base


def page_shell(title: str, body: str, locale: str = "zh-CN") -> bytes:
    return f"""<!doctype html><html lang=\"{html.escape(locale, quote=True)}\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\"><title>{html.escape(title)}</title><style>{STYLE}</style></head><body><main class=\"wrap\"><section class=\"card\">{body}</section></main></body></html>""".encode("utf-8")


def render_field(field: dict) -> str:
    name = html.escape(field["name"], quote=True)
    label = html.escape(field["label"])
    required = bool(field.get("required"))
    required_attr = " required" if required else ""
    mark = ' <span class="required">*</span>' if required else ""
    placeholder = html.escape(str(field.get("placeholder", "")), quote=True)
    default = field.get("default", False if field["type"] == "checkbox" else "")
    help_text = field.get("help")
    help_html = f'<div class="help">{html.escape(str(help_text))}</div>' if help_text else ""
    field_type = field["type"]
    if field_type in {"textarea", "url-list"}:
        control = f'<textarea id="{name}" name="{name}" placeholder="{placeholder}"{required_attr}>{html.escape(str(default))}</textarea>'
    elif field_type == "select":
        options = []
        for value, option_label in option_pairs(field["options"], field["name"]):
            selected = " selected" if str(default) == value else ""
            options.append(f'<option value="{html.escape(value, quote=True)}"{selected}>{html.escape(option_label)}</option>')
        control = f'<select id="{name}" name="{name}"{required_attr}>{"".join(options)}</select>'
    elif field_type == "checkbox":
        checked = " checked" if bool(default) else ""
        return f'<div class="field check"><input id="{name}" name="{name}" type="checkbox" value="1"{checked}><label for="{name}">{label}{mark}</label></div>{help_html}'
    elif field_type == "file":
        accept = html.escape(str(field.get("accept", "")), quote=True)
        multiple = " multiple" if field.get("multiple") else ""
        control = f'<input id="{name}" name="{name}" type="file" accept="{accept}"{multiple}{required_attr}>'
    elif field_type == "number":
        attrs = []
        for key in ("min", "max", "step"):
            if key in field:
                attrs.append(f' {key}="{html.escape(str(field[key]), quote=True)}"')
        control = f'<input id="{name}" name="{name}" type="number" value="{html.escape(str(default), quote=True)}" placeholder="{placeholder}"{"".join(attrs)}{required_attr}>'
    else:
        control = f'<input id="{name}" name="{name}" type="text" value="{html.escape(str(default), quote=True)}" placeholder="{placeholder}"{required_attr}>'
    return f'<div class="field"><label for="{name}">{label}{mark}</label>{control}{help_html}</div>'


def render_form(
    config: dict,
    api_key_present: bool,
    csrf_token: str,
    preset_options: list[tuple[str, str]] | None = None,
) -> bytes:
    ui = ui_text(config)
    description = html.escape(str(config.get("description", "")))
    intro = f'<p class="intro">{description}</p>' if description else ""
    notice = "" if api_key_present else f'<div class="notice">{html.escape(ui["apiKeyMissing"])}</div>'
    fields = "".join(render_field(field) for field in config["fields"])
    token = html.escape(csrf_token, quote=True)
    preset_id = str(config.get("formPreset") or "")
    options = preset_options or [(preset_id, config["title"])]
    selector_options = []
    for option_id, option_title in options:
        selected = " selected" if option_id == preset_id else ""
        selector_options.append(
            f'<option value="{html.escape(option_id, quote=True)}"{selected}>'
            f'{html.escape(option_title)}</option>'
        )
    selector = (
        '<div class="model-picker"><label for="modelPreset">选择模型</label>'
        '<select id="modelPreset" class="model-selector" aria-label="选择模型" '
        'onchange="window.location.href=\'/?preset=\'+encodeURIComponent(this.value)">'
        f'{"".join(selector_options)}</select></div>'
    )
    submitting_js = html.escape(json.dumps(ui["submitting"], ensure_ascii=False), quote=True)
    body = f'{selector}{intro}{notice}<form method="post" action="/submit" enctype="multipart/form-data" onsubmit="const b=this.querySelector(\'button\');b.disabled=true;b.textContent={submitting_js}"><input type="hidden" name="_csrf" value="{token}"><input type="hidden" name="_preset" value="{html.escape(preset_id, quote=True)}">{fields}<button type="submit">{html.escape(ui["submit"])}</button></form>'
    return page_shell(config["title"], body, config.get("locale", "zh-CN"))


def build_selectable_configs(initial_config: dict) -> dict[str, dict]:
    initial = validate_config(initial_config)
    configs = {
        preset_id: resolve_preset_request({"version": 1, "formPreset": preset_id})
        for preset_id in load_model_catalog()["presets"]
    }
    if initial.get("safeGenerate") is not None:
        for selectable_config in configs.values():
            selectable_config["safeGenerate"] = initial["safeGenerate"]
    initial_id = initial.get("formPreset")
    if not isinstance(initial_id, str) or initial_id not in configs:
        raise ConfigError("initial formPreset must exist in the fixed model catalog")
    configs[initial_id] = initial
    return configs


def select_config(configs: dict[str, dict], preset_id: str | None) -> dict:
    if not isinstance(preset_id, str) or preset_id not in configs:
        raise ConfigError("selected model is not in the fixed model catalog")
    return configs[preset_id]


def parse_multipart(content_type: str, body: bytes) -> dict[str, list[dict[str, Any]]]:
    message = BytesParser(policy=email_policy).parsebytes(
        f"Content-Type: {content_type}\r\nMIME-Version: 1.0\r\n\r\n".encode() + body
    )
    if not message.is_multipart():
        raise ConfigError("submission must use multipart/form-data")
    result: dict[str, list[dict[str, Any]]] = {}
    for part in message.iter_parts():
        name = part.get_param("name", header="content-disposition")
        if not name:
            continue
        result.setdefault(name, []).append(
            {
                "filename": part.get_filename(),
                "content_type": part.get_content_type(),
                "data": part.get_payload(decode=True) or b"",
            }
        )
    return result


def scalar_value(parts: dict[str, list[dict[str, Any]]], name: str) -> str | None:
    values = parts.get(name, [])
    if not values:
        return None
    return values[0]["data"].decode("utf-8", errors="replace")


def build_command(config: dict, parts: dict[str, list[dict[str, Any]]], upload_dir: Path) -> list[str]:
    activate_private_runtime()
    executable = shutil.which("weshop")
    if not executable:
        raise ConfigError("weshop CLI was not found; run install_weshop_cli.py --install first")
    args = [executable, config["command"]]
    if config.get("safeGenerate") is not None:
        args.append(f'--safeGenerate={config["safeGenerate"]}')
    args.extend(config.get("fixedArgs", []))
    for field in config["fields"]:
        name, flag, field_type = field["name"], field["flag"], field["type"]
        if field_type == "file":
            uploaded = [item for item in parts.get(name, []) if item.get("filename")]
            max_files = field.get("maxFiles", 10 if field.get("multiple") else 1)
            if len(uploaded) > max_files:
                raise ConfigError(f"{field['label']}: at most {max_files} files are allowed")
            if field.get("required") and not uploaded:
                raise ConfigError(f"{field['label']}: a file is required")
            for index, item in enumerate(uploaded):
                safe_name = Path(item["filename"]).name or f"upload-{index}"
                destination = upload_dir / f"{name}-{index}-{safe_name}"
                destination.write_bytes(item["data"])
                args.extend([flag, str(destination)])
            continue
        if field_type == "url-list":
            value = scalar_value(parts, name) or ""
            urls = [line.strip() for line in value.splitlines() if line.strip()]
            max_items = field.get("maxItems", 10)
            if len(urls) > max_items:
                raise ConfigError(f"{field['label']}: at most {max_items} URLs are allowed")
            if field.get("required") and not urls:
                raise ConfigError(f"{field['label']}: at least one URL is required")
            for url in urls:
                if urlparse(url).scheme not in {"http", "https"}:
                    raise ConfigError(f"{field['label']}: every line must be an http(s) URL")
                args.extend([flag, url])
            continue
        value = scalar_value(parts, name)
        if field_type == "checkbox":
            if value is not None:
                args.append(flag)
            elif field.get("required"):
                raise ConfigError(f"{field['label']}: must be checked")
            continue
        if value is None or value == "":
            if field.get("required"):
                raise ConfigError(f"{field['label']}: a value is required")
            continue
        if field_type == "select":
            allowed = {option for option, _ in option_pairs(field["options"], name)}
            if value not in allowed:
                raise ConfigError(f"{field['label']}: invalid option")
        if field_type == "number":
            try:
                number = float(value)
            except ValueError as exc:
                raise ConfigError(f"{field['label']}: must be numeric") from exc
            if "min" in field and number < field["min"]:
                raise ConfigError(f"{field['label']}: must be at least {field['min']}")
            if "max" in field and number > field["max"]:
                raise ConfigError(f"{field['label']}: must be at most {field['max']}")
        args.extend([flag, value])
    return args


def parse_output(output: str) -> dict[str, Any]:
    execution_id = None
    status = None
    error = None
    code = None
    media = []
    in_result = False
    current = None
    for raw_line in output.splitlines():
        line = raw_line.strip()
        if line.startswith("[") and line.endswith("]"):
            in_result = line == "[result]"
            current = None
            continue
        key, separator, value = line.partition(":")
        if not separator:
            continue
        key, value = key.strip(), value.strip()
        if key in {"code", "errorCode", "returnCode"} and re.fullmatch(r"\d{5}", value):
            code = code or value
        if code is None:
            code_match = re.search(
                r"(?i)(?:api\s+error|error\s+code|return\s+code)\s*[:：]?\s*(\d{5})\b",
                line,
            )
            if code_match:
                code = code_match.group(1)
        if key == "executionId" and not execution_id:
            execution_id = value
        if key == "message" and error is None:
            error = value
        if key.lower() in {"error", "api error"} and error is None:
            error = value
        if in_result and key == "status" and current is None:
            status = value
        match = re.fullmatch(r"(image|video)\[(\d+)\]", key)
        if in_result and match:
            current = {"kind": match.group(1), "index": int(match.group(2))}
            media.append(current)
        elif in_result and current is not None and key in {"url", "poster", "status"}:
            current[key] = value
    return {
        "executionId": execution_id,
        "status": status,
        "error": error,
        "code": code,
        "media": media,
    }


def classify_account_error(
    output: str,
    parsed: dict[str, Any] | None = None,
    catalog_path: Path = ACCOUNT_ERRORS_PATH,
) -> dict[str, Any] | None:
    parsed = parsed or {}
    code = str(parsed.get("code") or "")
    searchable = "\n".join((str(parsed.get("error") or ""), output))
    for rule in load_account_error_catalog(catalog_path)["rules"]:
        if code and code in rule["codes"]:
            matched = dict(rule)
            matched["detectedCode"] = code
            return matched
        if any(re.search(pattern, searchable, re.IGNORECASE) for pattern in rule["patterns"]):
            matched = dict(rule)
            matched["detectedCode"] = code or None
            return matched
    return None


def mark_account_error(parsed: dict[str, Any], output: str) -> dict[str, Any]:
    account_error = classify_account_error(output, parsed)
    if account_error:
        parsed["accountError"] = account_error
        parsed["status"] = "Failed"
    return parsed


def localized_value(value: Any, locale: str) -> str:
    if not isinstance(value, dict):
        return str(value or "")
    return str(value.get(locale) or value.get("en-US") or next(iter(value.values()), ""))


def result_http_status(parsed: dict[str, Any]) -> HTTPStatus:
    account_error = parsed.get("accountError")
    if isinstance(account_error, dict):
        try:
            return HTTPStatus(int(account_error["httpStatus"]))
        except (KeyError, TypeError, ValueError):
            return HTTPStatus.BAD_REQUEST
    return HTTPStatus.OK


def redact_output(output: str) -> str:
    secret = os.environ.get("WESHOP_API_KEY")
    if secret:
        output = output.replace(secret, "[REDACTED]")
    output = re.sub(
        r"(?i)(authorization\s*:\s*bearer\s+)[^\s]+",
        r"\1[REDACTED]",
        output,
    )
    return output


def run_command(config: dict, args: list[str]) -> tuple[dict[str, Any], str]:
    deadline = time.monotonic() + config["timeoutSeconds"]
    initial = subprocess.run(
        args,
        capture_output=True,
        text=True,
        timeout=max(1, deadline - time.monotonic()),
        check=False,
    )
    combined = (initial.stdout or "") + (("\n" + initial.stderr) if initial.stderr else "")
    parsed = mark_account_error(parse_output(combined), combined)
    if parsed.get("accountError"):
        return parsed, combined
    if initial.returncode != 0:
        parsed["status"] = parsed.get("status") or "Failed"
        return parsed, combined
    execution_id = parsed.get("executionId")
    while execution_id and parsed.get("status") not in {"Success", "Failed"} and not parsed.get("media"):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError(f"timed out waiting for execution {execution_id}")
        time.sleep(min(config["pollSeconds"], remaining))
        poll = subprocess.run(
            [args[0], "status", execution_id],
            capture_output=True,
            text=True,
            timeout=max(1, deadline - time.monotonic()),
            check=False,
        )
        poll_output = (poll.stdout or "") + (("\n" + poll.stderr) if poll.stderr else "")
        combined += "\n\n[poll]\n" + poll_output
        parsed = mark_account_error(parse_output(poll_output), poll_output)
        parsed["executionId"] = parsed.get("executionId") or execution_id
        if parsed.get("accountError"):
            break
        if poll.returncode != 0:
            parsed["status"] = parsed.get("status") or "Failed"
            break
    return parsed, combined


def render_result(config: dict, parsed: dict[str, Any], output: str) -> bytes:
    ui = ui_text(config)
    locale = config.get("locale", "zh-CN")
    account_error = parsed.get("accountError")
    failed = parsed.get("status") == "Failed" or parsed.get("error") or account_error
    heading = (
        localized_value(account_error.get("title"), locale)
        if isinstance(account_error, dict)
        else ui["error"] if failed else ui["result"]
    )
    media_html = []
    for item in parsed.get("media", []):
        url = item.get("url")
        if not url or urlparse(url).scheme not in {"http", "https"}:
            continue
        safe_url = html.escape(url, quote=True)
        if item.get("kind") == "video":
            poster = item.get("poster")
            poster_attr = f' poster="{html.escape(poster, quote=True)}"' if poster and urlparse(poster).scheme in {"http", "https"} else ""
            element = f'<video controls playsinline preload="metadata"{poster_attr}><source src="{safe_url}"></video>'
        else:
            element = f'<img src="{safe_url}" alt="generated image" loading="lazy">'
        media_html.append(f'<div class="media">{element}</div>')
    message_value = (
        localized_value(account_error.get("message"), locale)
        if isinstance(account_error, dict)
        else str(parsed.get("error") or "")
    )
    message = html.escape(redact_output(message_value))
    error_html = f'<div class="error">{message}</div>' if failed and message else ""
    code_value = (
        account_error.get("detectedCode") or parsed.get("code")
        if isinstance(account_error, dict)
        else parsed.get("code")
    )
    code_html = (
        f'<p class="meta">{html.escape(ui["errorCode"])}: '
        f'{html.escape(str(code_value))}</p>'
        if code_value
        else ""
    )
    action_html = ""
    if isinstance(account_error, dict):
        action_url = str(account_error.get("actionUrl") or "")
        if urlparse(action_url).scheme in {"https", "mailto"}:
            label = localized_value(account_error.get("actionLabel"), locale)
            target = ' target="_blank" rel="noopener noreferrer"' if action_url.startswith("https://") else ""
            action_html = (
                f'<a class="action" href="{html.escape(action_url, quote=True)}"{target}>'
                f'{html.escape(label)}</a>'
            )
    execution = html.escape(str(parsed.get("executionId") or ""))
    meta = f'<p class="meta">Execution ID: {execution}</p>' if execution else ""
    gallery = f'<div class="gallery">{"".join(media_html)}</div>' if media_html else ""
    raw = html.escape(redact_output(output))
    preset_id = quote(str(config.get("formPreset") or ""), safe="")
    body = f'<h1>{html.escape(heading)}</h1>{meta}{code_html}{error_html}{action_html}{gallery}<details><summary>{html.escape(ui["rawOutput"])}</summary><pre>{raw}</pre></details><a class="back" href="/?preset={preset_id}">← {html.escape(ui["back"])}</a>'
    return page_shell(heading, body, config.get("locale", "zh-CN"))


class FormHandler(BaseHTTPRequestHandler):
    server_version = "WeShopLocalForm/1"

    @property
    def config(self) -> dict:
        return self.server.config  # type: ignore[attr-defined]

    @property
    def csrf_token(self) -> str:
        return self.server.csrf_token  # type: ignore[attr-defined]

    @property
    def configs(self) -> dict[str, dict]:
        return self.server.configs  # type: ignore[attr-defined]

    def requested_config(self, preset_id: str | None) -> dict:
        return select_config(self.configs, preset_id or self.config.get("formPreset"))

    def send_html(self, payload: bytes, status: HTTPStatus = HTTPStatus.OK) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; img-src https: data:; media-src https:; "
            "style-src 'unsafe-inline'; script-src 'unsafe-inline'",
        )
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self) -> None:
        parsed_url = urlparse(self.path)
        path = parsed_url.path
        if path == "/health":
            payload = json.dumps({"ok": True, "command": self.config["command"]}).encode()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return
        if path != "/":
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        preset_values = parse_qs(parsed_url.query).get("preset", [])
        try:
            config = self.requested_config(preset_values[0] if preset_values else None)
        except ConfigError as exc:
            self.send_error(HTTPStatus.BAD_REQUEST, str(exc))
            return
        options = [(preset_id, item["title"]) for preset_id, item in self.configs.items()]
        self.send_html(
            render_form(
                config,
                bool(os.environ.get("WESHOP_API_KEY")),
                self.csrf_token,
                preset_options=options,
            )
        )

    def do_POST(self) -> None:
        if urlparse(self.path).path != "/submit":
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        active_config = self.config
        if not os.environ.get("WESHOP_API_KEY"):
            ui = ui_text(self.config)
            payload = page_shell(
                ui["error"],
                f'<h1>{html.escape(ui["error"])}</h1><div class="error">'
                f'{html.escape(ui["apiKeyMissing"])}</div><a class="back" href="/">'
                f'← {html.escape(ui["back"])}</a>',
                self.config.get("locale", "zh-CN"),
            )
            self.send_html(payload, HTTPStatus.BAD_REQUEST)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > 250 * 1024 * 1024:
                raise ConfigError("submission size must be between 1 byte and 250 MB")
            content_type = self.headers.get("Content-Type", "")
            body = self.rfile.read(length)
            parts = parse_multipart(content_type, body)
            submitted_token = scalar_value(parts, "_csrf") or ""
            if not hmac.compare_digest(submitted_token, self.csrf_token):
                raise ConfigError("invalid form token; reload the form and submit again")
            active_config = self.requested_config(scalar_value(parts, "_preset"))
            with tempfile.TemporaryDirectory(prefix="weshop-form-") as temp_dir:
                args = build_command(active_config, parts, Path(temp_dir))
                parsed, output = run_command(active_config, args)
            self.send_html(
                render_result(active_config, parsed, output),
                result_http_status(parsed),
            )
        except (ConfigError, subprocess.SubprocessError, TimeoutError, OSError) as exc:
            ui = ui_text(active_config)
            preset_id = quote(str(active_config.get("formPreset") or ""), safe="")
            payload = page_shell(
                ui["error"],
                f'<h1>{html.escape(ui["error"])}</h1><div class="error">'
                f'{html.escape(str(exc))}</div><a class="back" href="/?preset={preset_id}">'
                f'← {html.escape(ui["back"])}</a>',
                active_config.get("locale", "zh-CN"),
            )
            self.send_html(payload, HTTPStatus.BAD_REQUEST)

    def log_message(self, format_string: str, *args: Any) -> None:
        print(f"[{self.log_date_time_string()}] {format_string % args}")


def serve(
    config: dict,
    host: str = "127.0.0.1",
    port: int = 8765,
    open_browser: bool = False,
) -> int:
    config = validate_config(config)
    configs = build_selectable_configs(config)
    if not 1 <= port <= 65535:
        raise ConfigError("port must be between 1 and 65535")
    candidates = range(port, port + 11) if port == 8765 else (port,)
    last_error = None
    server = None
    for candidate in candidates:
        try:
            server = ThreadingHTTPServer((host, candidate), FormHandler)
            break
        except OSError as exc:
            last_error = exc
    if server is None:
        raise OSError(f"could not bind local form server near port {port}: {last_error}")
    server.config = config  # type: ignore[attr-defined]
    server.configs = configs  # type: ignore[attr-defined]
    server.csrf_token = secrets.token_urlsafe(32)  # type: ignore[attr-defined]
    actual_port = int(server.server_address[1])
    local_url = f"http://{host}:{actual_port}/"
    print(f"WeShop local form: {local_url}", flush=True)
    print(f"Command: weshop {config['command']}", flush=True)
    print(
        f"WESHOP_API_KEY: {'set' if os.environ.get('WESHOP_API_KEY') else 'not set'}",
        flush=True,
    )
    emit_event(
        "ready",
        url=local_url,
        command=config["command"],
        formPreset=config.get("formPreset"),
        browserRequested=open_browser,
    )
    if open_browser:
        try:
            if not webbrowser.open(local_url, new=2):
                print(f"Could not open a browser automatically. Open {local_url}", flush=True)
                emit_event("browser_open_failed", url=local_url)
        except (webbrowser.Error, OSError) as exc:
            print(f"Could not open a browser automatically ({exc}). Open {local_url}", flush=True)
            emit_event("browser_open_failed", url=local_url, message=str(exc))
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping form server…")
    finally:
        server.server_close()
        emit_event("stopped", url=local_url)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        type=Path,
        help="Optional preset JSON; without it the form starts on Qwen Image Edit",
    )
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--open-browser", action="store_true")
    parser.add_argument(
        "--no-install",
        action="store_true",
        help="Fail instead of installing missing Node.js/npm/weshop-cli dependencies",
    )
    args = parser.parse_args()
    try:
        config = load_config(args.config) if args.config else resolve_preset_request({})
    except ConfigError as exc:
        parser.error(str(exc))
    if args.check:
        print(
            json.dumps(
                {
                    "ok": True,
                    "title": config["title"],
                    "command": config["command"],
                    "cliVersion": config["cliVersion"],
                    "fieldCount": len(config["fields"]),
                },
                ensure_ascii=False,
            )
        )
        return 0
    if not 1 <= args.port <= 65535:
        parser.error("--port must be between 1 and 65535")
    try:
        ensure_weshop_cli(config["cliVersion"], install=not args.no_install)
    except InstallError as exc:
        parser.error(str(exc))
    return serve(config, args.host, args.port, open_browser=args.open_browser)


if __name__ == "__main__":
    raise SystemExit(main())
