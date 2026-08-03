# Cornell-KB

Cornell-KB is a source-grounded study pipeline for turning course material into searchable notes, retrieval artifacts, and Obsidian pages. It combines deterministic manifests and provenance checks with optional OpenViking, Hindsight, LLM, and local media-model integrations.

The repository is designed to be useful in two modes:

- **Offline development:** validate manifests, run the test suite, exercise retrieval logic with fixture data, and inspect generated artifacts without any external service.
- **Live study workflow:** process PDFs/audio/text, index approved derived artifacts, retrieve source context, and sync generated notes into an Obsidian vault.

It is a toolkit, not a hosted application. A live deployment still needs the services described below. That distinction saves a surprising amount of confusion.

## What is included

- Source manifests with SHA-256 validation and deterministic resource identities.
- PDF/text/media artifact handling with provenance metadata.
- Hybrid retrieval utilities: dense OpenViking search plus a local BM25 index, with optional reranking.
- Hindsight-backed study-memory ingestion with production-bank safeguards.
- Obsidian synchronization with course namespace routing and managed-file boundaries.
- Offline tests and a synthetic fixture manifest that works immediately after checkout.

The public repository does **not** include private course folders, raw lecture audio, generated indexes, API credentials, or the separate Lean reference project. Real course manifests and source files should remain local.

## Quick start

### Requirements

- Python 3.11 or newer
- Git
- Optional: an OpenViking server, Hindsight server, Ollama, or an LLM provider for live features

Create an environment and install the dependencies used by the offline suite:

```bash
python -m venv .venv
```

Windows:

```powershell
.venv\Scripts\activate
python -m pip install -r requirements-dev.txt
```

macOS/Linux:

```bash
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
```

Run the checks:

```bash
python -m pytest -q
python -m compileall -q scripts tests test_runs
```

The repository's offline gate is also available directly:

```bash
python test_runs/e2e_gate.py
```

### Validate the checked-in fixture manifest

The checked-in `config/source_manifest.json` contains only repository-local fixture files. It is a safe example, not a place to add personal course paths.

```bash
python scripts/ingestion/source_manifest.py validate \
  --manifest config/source_manifest.json \
  --root .

python scripts/ingestion/preflight.py \
  --manifest config/source_manifest.json \
  --root . \
  --no-services \
  --no-git
```

The second command is a diagnostic preflight. It will report any live-provider configuration that is unavailable; use the first command and the offline gate when you only want a no-network check.

## Repository map

```text
config/
  course_manifest_template.json   Template for a local course manifest
  course_namespaces.yaml          Course-to-Obsidian routing rules
  pipeline_laptop.yaml            Media pipeline defaults
  source_manifest.json            Safe, repository-local fixture manifest

data/test_sources/                Small fixture corpus for offline tests
scripts/core/                     HTTP, provenance, model, and OpenViking adapters
scripts/ingestion/                Manifest validation and ingestion helpers
scripts/media/                    Transcription, OCR, and diagram tooling
scripts/notes/                    Chunking and note generation
scripts/ops/                      Pipelines, connectivity, cleanup, and Obsidian sync
scripts/retrieval/                Search, BM25, hybrid fusion, and reranking
tests/                             Offline regression tests
docs/                              Onboarding and production runbooks
tools/                             Optional Windows/Linux model helpers
```

## Typical workflows

### 1. Add local course material

Keep source files under an ignored local directory such as `courses/<course-slug>/`. Start from the template rather than editing the public fixture manifest:

```bash
mkdir -p config/manifests courses/my-course
cp config/course_manifest_template.json config/manifests/my-course.json
```

Fill in relative source paths and SHA-256 hashes, then validate before indexing:

```bash
python scripts/ingestion/source_manifest.py validate \
  --manifest config/manifests/my-course.json \
  --root .
```

Use `--no-services --no-git` on preflight when you are checking local structure only. Do not use `--index` or live ingestion until the manifest and provenance checks are green.

### 2. Process media

The media pipeline accepts a directory of PDFs, audio, images, or text and writes derived artifacts plus a manifest. It does not index anything unless `--index` is explicitly supplied.

```bash
python scripts/ops/laptop_pipeline.py \
  --input-dir courses/my-course/incoming \
  --output-dir data/artifacts/my-course \
  --course MY-COURSE \
  --lecture 1
```

The GPU/media dependencies are intentionally separate:

```bash
python -m pip install -r requirements-media.txt
```

MOSS transcription has its own upstream install step and is optional. The default Whisper/Ollama endpoints are local and can be overridden with environment variables; no private machine address is embedded in the repository.

## Switching models and providers

There is no single global model switch. Cornell-KB has separate model roles, and
the supported switch depends on which stage you are running:

| Stage | Current route | How to switch |
|---|---|---|
| Note synthesis, fact checking, and corrections | DeepSeek V4 Pro API | Set `DEEPSEEK_API_KEY`; override the compatible endpoint with `--api-url` if needed |
| Diagram descriptions | Ollama, default `qwen3-vl:8b` | Pass `--model` and optionally `--ollama-url` to `scripts/media/diagrams.py` |
| OCR | Ollama, default `glm-ocr` with `qwen3-vl:8b` fallback | Pass `--engine`, `--fallback-engine`, and `--ollama-url` to `scripts/media/transcribe.py ocr` |
| Single-speaker transcription | Local faster-whisper, default `large-v3-turbo` | Pass `--model`, `--device`, and `--compute-type` to `scripts/media/transcribe.py transcribe` |
| Multi-speaker transcription | Local MOSS runtime | Pass `--engine moss` and `--moss-model` to `scripts/media/transcribe.py transcribe` |

### Use the API model for note generation

The note-generation path is already API-backed. It deliberately no longer uses
Ollama for text synthesis, so do **not** point `--ollama-url` at a cloud API;
that option is retained only as a deprecated no-op for old scripts.

Set the key in the environment. Bash/macOS/Linux:

```bash
export DEEPSEEK_API_KEY="<your-deepseek-key>"
python scripts/notes/note_generator.py \
  --transcript courses/my-course/incoming/lecture.txt \
  --course MY-COURSE \
  --lecture 1 \
  --topic "Lecture topic" \
  --backend deepseek \
  --model deepseek-v4-pro
```

PowerShell:

```powershell
$env:DEEPSEEK_API_KEY = "<your-deepseek-key>"
python scripts/notes/note_generator.py --transcript courses/my-course/incoming/lecture.txt --course MY-COURSE --lecture 1 --backend deepseek --model deepseek-v4-pro
```

The loader checks the environment first, then a `KEY=value` file. Set
`CORNELL_KB_ENV_FILE` to choose the file explicitly; when running through
Hermes, `HERMES_HOME/.env` is discovered automatically, and standalone use
falls back to `~/.config/cornell-kb/.env`. To route the DeepSeek-compatible
client through a gateway, pass its chat-completions endpoint:

```bash
python scripts/notes/note_generator.py ... \
  --api-url "https://api.example.com/v1/chat/completions"
```

The current implementation intentionally accepts only the `deepseek` backend
and `deepseek-v4-pro` model. Switching to an unrelated API provider or model is
not an environment-only change: update the provider/client validation in
`scripts/notes/note_generator.py` and `scripts/core/common_client.py`, update
the generated-note metadata, and add tests before using it. This prevents a
provider-specific request format from being sent to the wrong endpoint.

### Switch local Ollama models

For diagrams, the model is a command-line option:

```bash
ollama pull qwen3-vl:8b
python scripts/media/diagrams.py slides.pdf \
  --course MY-COURSE \
  --lecture 1 \
  --model qwen3-vl:8b
```

For OCR, choose the primary and fallback engines:

```bash
python scripts/media/transcribe.py ocr slides.pdf \
  --engine glm-ocr \
  --fallback-engine qwen3-vl:8b
```

For audio, choose Whisper or MOSS and their model settings:

```bash
python scripts/media/transcribe.py transcribe lecture.wav \
  --engine whisper \
  --model large-v3-turbo

python scripts/media/transcribe.py transcribe discussion.wav \
  --engine moss \
  --moss-model OpenMOSS-Team/MOSS-Transcribe-Diarize
```

To use an Ollama server on another machine, change the Ollama endpoint rather
than changing the model code:

```bash
export CORNELL_KB_OLLAMA_URL="http://your-ollama-host:11434/api/generate"
```

The OCR, diagram, and local transcription entrypoints do not currently expose
cloud OCR/vision/audio providers. Moving those stages from local models to a
cloud API requires a separate adapter; setting `CORNELL_KB_OLLAMA_URL` to a
non-Ollama API is not sufficient because the request and response schemas
differ.

### 3. Use live retrieval

Install the live SDK only when you have an OpenViking service:

```bash
python -m pip install -r requirements-live.txt
```

Build the ignored local lexical index from your approved manifest, then use the retrieval CLI with the service URL configured for your environment. The live commands require a running OpenViking server and are deliberately not part of the offline test path.

```bash
python scripts/ingestion/source_manifest.py rebuild-index \
  --manifest config/manifests/my-course.json \
  --root . \
  --index-path data/lexical_index.json

python scripts/retrieval/search.py health
python scripts/retrieval/search.py hybrid "closed loop stability" \
  --index-path data/lexical_index.json
```

### 4. Sync notes to Obsidian

Preview a sync without writing to the vault:

```bash
python scripts/ops/obsidian_sync.py \
  --source-root courses \
  --vault-root ~/obsidian-vault \
  --once \
  --dry-run
```

For a Windows launcher, `scripts/ops/start_obsidian_sync.vbs` resolves the repository from its own location. Set `CORNELL_KB_PYTHON` if `python` on `PATH` is not the interpreter you want.

## Configuration

The project uses local defaults and environment overrides. Set only the values needed for the feature you are using:

| Variable | Purpose | Default |
|---|---|---|
| `CORNELL_KB_OPENVIKING_URL` | OpenViking HTTP endpoint | `http://127.0.0.1:1934` |
| `CORNELL_KB_HINDSIGHT_URL` | Hindsight HTTP endpoint | `http://127.0.0.1:8888` |
| `CORNELL_KB_EMBEDDING_URL` | Embedding service health endpoint | `http://127.0.0.1:8001` |
| `CORNELL_KB_OLLAMA_URL` | Ollama generation endpoint | `http://127.0.0.1:11434/api/generate` |
| `CORNELL_KB_OUTPUT_DIR` | Default media artifact directory | `data/artifacts/media` |
| `CORNELL_KB_WHISPER_DEVICE` | Whisper device selection | `cuda` |
| `CORNELL_KB_WHISPER_COMPUTE_TYPE` | Whisper compute type | `float16` |
| `CORNELL_KB_OLLAMA_SSH_TARGET` | Optional `user@host` for remote Ollama startup | unset; launch locally |
| `CORNELL_KB_OLLAMA_REMOTE_EXE` | Remote/local Ollama executable | `ollama` |
| `CORNELL_KB_ENV_FILE` | Optional local `KEY=value` file for provider credentials | `~/.config/cornell-kb/.env` |
| `DEEPSEEK_API_KEY` | Optional LLM access for generation/planning | unset |

If you run the project through Hermes, its configured environment-file mechanism may also provide credentials. Environment variables are preferred for standalone use. Never commit `.env`, keys, authorization headers, or generated traces containing secrets.

## Architecture and safety boundaries

1. **Manifest layer** — validates paths, hashes, metadata, duplicate sources, and namespace-safe identities.
2. **Artifact layer** — converts media into text/structured artifacts while recording the source hash and extraction engine.
3. **Index layer** — sends only approved document/text artifacts to OpenViking; audio remains local and is never uploaded as audio.
4. **Retrieval layer** — combines dense and lexical candidates while preserving source URIs and read-back provenance.
5. **Memory/notes layer** — writes explicitly scoped Hindsight facts and managed Obsidian notes.

The LLM can improve planning or generation, but validation and source selection remain deterministic code paths. Live writes should be treated as an explicit operator action, not an accidental side effect of running a test.

## Development checks

Before opening a pull request or sharing a change:

```bash
python -m pytest -q
python -m compileall -q scripts tests test_runs
git diff --check
```

The same test and compile steps run in GitHub Actions. Keep generated artifacts, local manifests, course content, model caches, and credentials out of commits. See `docs/course-onboarding.md` for the full course setup flow and `docs/production-readiness-runbook.md` for live-service gates.

## Current status

The offline retrieval and ingestion contracts are implemented and tested. The live-service path is intentionally configurable rather than bundled: friends can run the tests immediately, then add only the services and model dependencies they actually need.

## License

No license has been selected yet. Until one is added, the repository is viewable on GitHub but should not be treated as licensed for redistribution or commercial use.
