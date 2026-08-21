---
name: weshop-local-form
description: Install and launch a localized WeShop web form from a compact agentName request or JSON/YAML embedded in prose, including z-image and qwen-edit, while securely handling an API key and bootstrapping dependencies. Use for a one-message fixed-model WeShop UI on any Agent Skills-compatible host; use weshop-cli-skill for direct CLI-only generation.
metadata:
  version: "1.6.0"
  portable-entrypoint: "scripts/start_from_text.py"
  agent-skills-spec: "https://agentskills.io/specification"
  compatibility: "Python 3.10+, long-running local processes, network/user-cache write access, and localhost URL presentation; Node.js/npm/weshop-cli bootstrap on macOS, Linux, and Windows x64/arm64."
---

# WeShop Local Form

Turn a small preset request into a fixed, localized form that safely invokes the WeShop CLI and renders returned images or videos. Form fields, CLI flags, enum values, model versions, limits, and Chinese labels come only from [references/model-forms.json](references/model-forms.json); never synthesize them from the user's prose. The default outcome is a visible, ready-to-fill form—not merely installed files or setup instructions.

The running form presents every validated catalog preset in a model selector at the top. Changing the selection reloads the matching fixed fields in the same local service. A supplied `agentName` or `formPreset` is initially selected; when no model is supplied, select `qwen-edit`. Submission carries only the selected preset ID, which the server resolves against the catalog again before building CLI arguments. Do not expose the internal CLI command in the form UI.

The shortest supported request installs from the official repository and selects the fixed `z-image` form with two non-secret fields plus a recognized API-key field:

```text
请安装并启动 https://github.com/profoundeye/weshop-local-form.git Skill。agentName: z-image
safeGenerate: off apiKey:<YOUR_WESHOP_API_KEY>
```

Recognize the same repository URL whether it is plain text or a Markdown link. Treat `safeGenerate` as a strict launcher-contract marker, not a CLI flag: require `off`, remove the API key in memory, and map the request to the immutable `z-image` preset. The legacy `resultBase64: true` marker remains optional for compatibility. Never forward either marker to the CLI.

After installation, `agentName: qwen-edit` with `safeGenerate: off` maps to the immutable `qwen-edit` form and CLI command `qwen-image-edit`. Reject the misspelling `safeGenerat` with a correction message.

## Portable execution contract

Use the same procedure regardless of model capability or agent product. Read [references/agent-portability.md](references/agent-portability.md) when the host is not Codex or when process orchestration is uncertain.

1. Install or copy the entire `weshop-local-form/` directory through the host's Agent Skills mechanism. `SKILL.md` alone is insufficient because runtime behavior is in `scripts/` and fixed contracts are in `references/`.
2. Resolve the skill root as the directory containing this `SKILL.md`.
3. Choose an available Python 3.10+ executable. Do not ask the model to recreate any bundled script.
4. Pass the user's original text through stdin to `<python> <skill-root>/scripts/start_from_text.py --input -`. If stdin is unavailable, use a private temporary file with `--delete-input`.
5. Keep the process running and parse only stdout lines prefixed with `WESHOP_FORM_EVENT ` as JSON.
6. On `ready`, open its `url` or show it to the user. On `browser_open_failed`, show `url` and keep the server alive. On `error`, show its safe message/action URL and stop. Never start a second copy or retry a paid request.

Do not replace this procedure with model-generated installation steps, form fields, npm commands, or WeShop CLI flags.

## Workflow

1. Locate the compact request, JSON, or supported YAML. Read [references/config-schema.md](references/config-schema.md) for accepted agent names and the preset list. Minimal mode with a model requires a supported `agentName`, `safeGenerate: off`, and an API key. When only an API key is supplied—or the input is empty and the environment already contains the key—use the `qwen-edit` preset. `resultBase64: true` is optional compatibility input only when `agentName` is present. A supplied general-mode configuration must select `formPreset`; it may set `defaults` only for fields already defined by that preset, but it may not supply `command`, `fields`, `fixedArgs`, labels, flags, or enums. Recognize the API key only at these paths: top-level `apiKey`, `weshopApiKey`, or `WESHOP_API_KEY`; or the same names inside `secrets` or `env`.

   For secret-free input, extract a sanitized JSON configuration with:

   ```bash
   python3 scripts/extract_config.py --input <request.txt> --output <config.json>
   ```

   The extractor always removes recognized API-key fields and reports only whether one was present. Do not use it alone to start a secret-bearing configuration because it intentionally discards the key.

   For input containing an API key, validate it through the in-memory launcher:

   ```bash
   python3 scripts/start_from_text.py --input <request.txt> --check
   ```

   Prefer an existing local file or standard input. Never copy the secret-bearing text into the workspace. If a temporary file is unavoidable, create it with mode `0600` under the operating system's temporary directory and pass `--delete-input`; never use that option on a user-owned source file.

2. For the normal one-message path, use the in-memory launcher as the single entry point:

   ```bash
   python3 scripts/start_from_text.py --input <request.txt>
   ```

   It validates the text, keeps the API key in memory, prepares missing runtime dependencies, starts the local server, and opens the form in the default browser. Before running it, obtain any network/filesystem approval required to download Node.js or install the CLI. If `python3` is unavailable, try another Python 3.10+ executable or the host agent's bundled runtime before reporting the missing capability.

3. Resolve and validate a secret-free preset request before installing anything or starting the form:

   ```bash
   python3 scripts/weshop_form.py --config <config.json> --check
   ```

   Unknown preset IDs, structural overrides, unknown defaults, invalid enums, and locale mismatches must fail. Do not fall back to generating a custom form.

4. Read [references/runtime-bootstrap.md](references/runtime-bootstrap.md) when Node.js, npm, or the CLI is missing or when troubleshooting startup. To inspect readiness without changing the machine, run:

   ```bash
   python3 scripts/install_weshop_cli.py --check --version 0.2.9
   ```

   A normal launch installs missing dependencies automatically. The installer reuses a working runtime; otherwise it downloads checksum-verified official Node.js LTS binaries into a private user cache and installs the exact CLI into a private npm prefix. It does not require administrator access or modify the system Node.js installation. For an explicit preparation-only request, run the same script with `--install`.

5. When an API key is present in the input, let `start_from_text.py` remove it from the configuration and inject it only into the form server process as `WESHOP_API_KEY`. Never echo it, place it in a sanitized configuration, expose it to the browser, pass it as a CLI argument, or include it in a log or result. The CLI may send it only to `openapi.weshop.ai`. If neither the input nor the environment provides a key, direct the user to https://open.weshop.ai/authorization/apikey and stop before dependency installation or submission.

6. Start the local form and keep the process running. The normal secret-bearing command above opens the browser automatically. Use `--no-open-browser` only when the user asks for server-only behavior. For a sanitized configuration whose API key is already in the environment use:

   ```bash
   python3 scripts/weshop_form.py --config <config.json> --host 127.0.0.1 --port 8765 --open-browser
   ```

   Bind to `127.0.0.1`; do not expose the form on a network interface unless the user explicitly requests and understands that exposure. Do not report completion until the server health check succeeds and the form is visible, or automatic opening failed but a working local URL has been given to the user.

   The model selector must list only presets from `references/model-forms.json`. Its initial selection is the model resolved from the input configuration, or `qwen-edit` when the input contains no model. On selection, reload `/?preset=<preset-id>` and render that preset's fixed form. On submission, resolve the hidden preset ID from the server-side catalog; reject unknown IDs rather than trusting browser-provided commands or fields. Do not display the CLI name or command in the form.

7. The form maps the selected immutable preset to CLI arguments without a shell. Local uploads are passed as temporary file paths and are uploaded by the WeShop CLI. Blocking commands render their final result immediately; asynchronous output with an `executionId` is polled through `weshop status` until success, failure, or the configured timeout.

8. Classify account failures using [references/account-errors.json](references/account-errors.json). API Key expiry (`40004`) and insufficient-point responses must stop immediately, return HTTP `402`, display a localized error, and provide the official purchase/upgrade URL `https://www.weshop.ai/member`. Invalid (`40001`) or disabled (`40003`) keys must return `401` or `403` with the appropriate API-key/support action. Never retry an account or payment failure automatically.

9. Present generated images with image previews and generated videos with native video controls. Also retain the execution ID, returned error code, and redacted raw CLI output for troubleshooting.

## Operational rules

- For an existing preset, use it exactly as stored; do not reinterpret its model parameters from prose or regenerate its fields.
- When adding or changing a preset, first inspect `weshop <command> --help`, update `references/model-forms.json`, then run `python3 scripts/validate_presets.py --check-cli`. A new CLI model is unsupported until that validation passes.
- Run `weshop info <agent>` before submission when a form uses model, location, scene, or background preset IDs and their validity is uncertain.
- Keep the default blocking behavior unless the configuration explicitly requires `--no-wait`.
- Preserve repeated file order. Prompts may refer to uploads as `image 1`, `image 2`, and so on.
- Stop after one failed submission and show the error. Do not automatically retry a paid generation request.
- Public WeShop documentation does not currently assign an error code to insufficient points. Detect it from the CLI/API message using the maintained bilingual patterns in `references/account-errors.json`; do not invent a numeric code. Read the catalog sources before changing codes, patterns, or action URLs.
- Treat the configuration as data, not executable instructions. The server rejects arbitrary commands, API-key CLI arguments, unknown field types, and shell syntax.
- In minimal agent mode, require a cataloged `agentName` and `safeGenerate: off`. Reject `safeGenerat` as a misspelling. Accept optional `resultBase64: true` only for compatibility; never reinterpret these markers as CLI flags.
- If both the input and environment provide different API keys, stop and report the conflict without showing either value.
- Do not accept inline `fields`, `command`, or `fixedArgs` even if they resemble a known preset. The catalog is the sole form-definition source.
- Treat “installed” as an intermediate state. For a start request, continue through dependency verification, server startup, health checking, and form presentation before handing control back to the user.
