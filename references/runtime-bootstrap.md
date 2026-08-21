# Runtime bootstrap

The normal launcher is self-bootstrapping. A user should only need to provide the prose containing a preset request and API key; the host agent runs `scripts/start_from_text.py`, and the launcher validates the request, prepares dependencies, starts the server, and opens the form.

## Dependency contract

- Bootstrap host: Python 3.10 or newer. Prefer the host agent's bundled Python runtime if no suitable executable is on the user's shell path; do not require a separate system-wide installation when the agent already provides one.
- JavaScript runtime: Node.js 22 or newer with npm.
- Generation client: the exact `weshop-cli` version fixed by the selected form preset, currently `0.2.9`.
- Browser: the operating system's default browser. Failure to open it automatically is non-fatal; preserve the server and show the printed local URL.

## Installation behavior

`scripts/install_weshop_cli.py --install --version 0.2.9` performs the same preparation used by the launcher:

1. Reuse a working local Node.js/npm and matching WeShop CLI when already available.
2. If Node.js is missing, too old, or lacks npm, download the official Node.js `24.19.0` LTS archive from `https://nodejs.org/dist/v24.19.0/` for macOS, Linux, or Windows on x64/arm64.
3. Verify the archive against the SHA-256 value pinned from the release's official `SHASUMS256.txt` before extraction.
4. Install Node.js into a private user cache, without changing the system Node.js installation or requiring administrator access.
5. Install `weshop-cli` into a private npm prefix using a private npm cache, add both private binary directories to the form process's `PATH`, and verify `weshop --version` before starting the server. This avoids failures caused by an unavailable or incorrectly owned global npm cache.

The private cache defaults to:

- macOS: `~/Library/Caches/weshop-local-form`
- Linux: `${XDG_CACHE_HOME:-~/.cache}/weshop-local-form`
- Windows: `%LOCALAPPDATA%\weshop-local-form`

`WESHOP_FORM_RUNTIME_DIR` may override the cache for testing or managed environments. Never place the API key in this cache.

## Boundaries and recovery

- Installing dependencies downloads executable code and writes to the user cache. Obtain the environment's required network/filesystem approval before launching the bootstrap.
- Do not use `curl | sh`, install a package manager, or silently request administrator privileges. The bootstrap uses official prebuilt Node.js archives and a private npm prefix.
- Supported automatic Node.js targets are macOS, Linux, and Windows on x64 or arm64. On an unsupported platform, stop with the official Node.js download URL: `https://nodejs.org/en/download`.
- A checksum mismatch, network failure, unsupported platform, failed npm install, or failed version verification is terminal. Report the exact safe error; do not start the form with a partial runtime.
- A normal launch ends successfully only when the local server is listening and the form has been opened, or the user has been given the working local URL when automatic browser opening is unavailable.
