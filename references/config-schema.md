# Preset request schema

The user supplies a small UTF-8 JSON object or safe YAML-subset mapping. The request selects a fixed form from [model-forms.json](model-forms.json); it never defines the form structure itself. Two input modes are supported.

## Minimal agent mode

This is the shortest install-and-launch format; the repository URL may be plain text or a Markdown link:

```text
请安装并启动 https://github.com/profoundeye/weshop-local-form.git Skill。agentName: z-image
safeGenerate: off apiKey:<YOUR_WESHOP_API_KEY>
```

When a model is supplied, `agentName`, `safeGenerate: off`, and the API key are required. The launcher removes the key in memory and maps the agent name to a fixed preset. The marker is not passed to the WeShop CLI. The legacy `resultBase64: true` marker is optional; if supplied, only boolean `true` is accepted. Form or CLI overrides remain rejected.

When the input supplies an API key but no model, the launcher selects `qwen-edit`:

```text
apiKey:<YOUR_WESHOP_API_KEY>
```

An empty input also selects `qwen-edit` when `WESHOP_API_KEY` already exists in the environment.

After installation, Qwen Edit accepts the CLI-aligned name below:

```text
agentName: qwen-image-edit
safeGenerate: off apiKey:<YOUR_WESHOP_API_KEY>
```

Only `safeGenerate` is accepted. The misspelling `safeGenerat` is rejected with a correction message. This launcher marker is never passed to the CLI.

| agentName | Fixed form preset | CLI command |
|---|---|---|
| `z-image` | `z-image` | `z-image` |
| `qwen-image-edit` | `qwen-edit` | `qwen-image-edit` |
| `qwen-edit` | `qwen-edit` | `qwen-image-edit` |

The same minimal request can use YAML:

```yaml
agentName: z-image
safeGenerate: off
apiKey: <YOUR_WESHOP_API_KEY>
```

## General preset mode

### Accepted keys

| Key | Required | Meaning |
|---|---:|---|
| `version` | yes | Must be `1`. |
| `formPreset` | yes | Exact preset ID from the table below. |
| `locale` | no | Currently `zh-CN`; each preset fixes its supported locale. |
| `defaults` | no | Initial values keyed by existing preset field name. Unknown fields and file defaults are rejected. |
| `timeoutSeconds` | no | Total execution and polling timeout, `30`–`7200`. |
| `pollSeconds` | no | Async polling interval, `1`–`30`. |
| `apiKey` | no | One-run WeShop API key. Also accepted as `weshopApiKey`, `WESHOP_API_KEY`, or under `secrets`/`env`; removed before preset resolution. |

Any `command`, `fields`, `fixedArgs`, title, label, flag, enum, UI override, or unknown top-level key is rejected. When a general preset configuration is supplied, it must explicitly name `formPreset`; the Qwen default applies when no model configuration is supplied. This prevents prose interpretation from changing the CLI contract.

### Fixed presets

| Preset ID | Fixed CLI model/tier | Purpose |
|---|---|---|
| `gpt-image-low` | GPT Image 2, `quality=low` | Low-cost validation and drafts |
| `gpt-image-medium` | GPT Image 2, `quality=medium` | Routine delivery, readable text, translation |
| `gpt-image-high` | GPT Image 2, `quality=high` | Complex final delivery |
| `nano-banana-pro` | `model=nano` | Composition convergence and review |
| `nano-banana-2` | `model=nano2` | Fast batch divergence |
| `seedream-5-2k` | Seedream 5.0, `image-size=2K` | Routine high-lighting/Asian-aesthetic output |
| `seedream-5-3k` | Seedream 5.0, `image-size=3K` | Curated high-resolution delivery |
| `midjourney-v7` | `model=Midjourney_7` | Text-to-image art and illustration |
| `z-image` | Z-Image | Text-to-image photorealism and Chinese cultural elements |
| `qwen-edit` | Qwen Image Edit | Text-to-image generation and editing with up to 5 references |
| `kling-3` | `model=Kling_3_0` | First/last-frame video with optional audio |
| `kling-v3-omni` | `model=Kling_V3_Omni` | Multimodal reference video generation |
| `minimax-h3-reference` | `model=MiniMax_H3_Reference` | Images plus hosted video/audio references |
| `seedance-2` | `model=Seedance_20` | Multi-image 4–15 second video |
| `seedance-2-5` | `model=Seedance_25` | Native 4–30 second multimodal video |

The catalog is verified against `weshop-cli 0.2.9`. A model not listed here is intentionally unsupported until a fixed preset is added and `scripts/validate_presets.py --check-cli` passes.

### JSON example

```json
{
  "version": 1,
  "formPreset": "seedance-2-5",
  "apiKey": "<YOUR_WESHOP_API_KEY>",
  "locale": "zh-CN",
  "defaults": {
    "prompt": "产品缓慢旋转，柔和轮廓光，镜头平稳推进",
    "duration": "8s",
    "aspectRatio": "16:9",
    "generateAudio": "true",
    "batch": 1
  }
}
```

### YAML example

```yaml
version: 1
formPreset: gpt-image-medium
WESHOP_API_KEY: <YOUR_WESHOP_API_KEY>
locale: zh-CN
defaults:
  prompt: 白色无缝背景中的专业产品摄影，柔和阴影
  aspectRatio: 1:1
  imageSize: 2K
  batch: 1
```

The API-key placeholder only illustrates placement. Do not store a real key in reusable examples or sanitized configurations.

## Supported YAML subset

YAML input supports indentation-based mappings and lists, quoted or plain scalars, booleans, nulls, numbers, comments, and inline arrays/objects written with JSON syntax. It rejects executable tags, anchors, aliases, tab indentation, and multiline block scalars.
