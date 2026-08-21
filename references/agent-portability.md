# Portable agent contract

This skill follows the open Agent Skills directory convention: `SKILL.md` plus optional `scripts/` and `references/`. `agents/openai.yaml` is optional product metadata; non-OpenAI agents may ignore it. Runtime behavior must come from the portable Python scripts, not from vendor-specific tools.

Install the whole skill directory using the host client's normal Agent Skills import or filesystem location. An installation containing only `SKILL.md` is incomplete. At minimum, confirm these files remain relative to the skill root: `scripts/start_from_text.py`, `scripts/weshop_form.py`, `scripts/install_weshop_cli.py`, `references/model-forms.json`, and `references/account-errors.json`.

## Capability requirements

The host agent needs only these capabilities:

1. Read files in the installed skill directory.
2. Run a Python 3.10+ process and keep a long-running process alive.
3. Supply the user's original text through process stdin or a mode-`0600` temporary file.
4. Request network and user-cache write permission when its environment requires approval.
5. Open a localhost URL, or show that URL to the user.

The agent does not need to understand npm, WeShop CLI flags, model enums, HTML, polling, or API error codes. Bundled scripts own those decisions.

## Canonical invocation

Resolve `<skill-root>` as the directory containing this skill's `SKILL.md`. Choose the first available Python 3.10+ executable (`python3`, `python`, or Windows `py -3`), then run exactly one of:

```text
<python> <skill-root>/scripts/start_from_text.py --input -
<python> <skill-root>/scripts/start_from_text.py --input <private-temporary-file> --delete-input
```

Prefer stdin. Do not pass the original text or API key as a command-line argument. Do not transcribe the configuration into another format, choose a model on the user's behalf, or call npm directly.

The command is a server process and is expected to remain running. Use the host agent's background/session mechanism rather than waiting for process exit.

## Machine-readable events

Read stdout line by line. Lines beginning with `WESHOP_FORM_EVENT ` contain one JSON object. Ignore other lines unless troubleshooting.

| Event | Agent action |
|---|---|
| `check` | Configuration was validated. Inspect `dependencies.ready` only when the user asked for diagnostics. |
| `ready` | The server is listening. Open `url`; if GUI opening is unavailable, show the exact URL. Do not wait for process exit. |
| `browser_open_failed` | Keep the server alive and show `url`; this is not a server failure. |
| `error` | Stop. Show `message` and `actionUrl` when present. Never expose the input text or API key and never retry automatically. |
| `stopped` | The server is no longer available. Do not claim the form is still running. |

Unknown events must be ignored for forward compatibility. Event payloads never contain the API key.

## Deterministic recovery

- If Python 3.10+ is unavailable, report that single missing host capability. Do not invent a platform-specific Python installer.
- If the process exits before `ready`, report the `error` event or sanitized stderr. Do not replace the launcher with hand-written npm or CLI commands.
- If no event appears but the process is still running, wait for output once more; dependency installation can take time. Do not start a second copy.
- If the default port is occupied, the server automatically tries ports `8765` through `8775`; use only the URL from the `ready` event.
- After `ready`, verify `/health` only when the host can make localhost requests. A `200` response confirms the server; it does not validate the user's API subscription or points.
- Account errors and generated media are rendered in the browser. The host agent should not duplicate the paid submission outside the form.
