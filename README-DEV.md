# AetioECG Developer Guide

Setup, architecture, the contract, the PTB-XL adapter, rendering, interfaces, testing and releases for AetioECG, a service that returns 12-lead ECGs as SVG. For what the project is and a quick start, see the [README](README.md).

AetioECG is stateless: no database, no file is written except the SVG you ask for. It uses no LLM.

## Table of contents

- [Requirements and setup](#requirements-and-setup)
- [Architecture](#architecture)
- [Contract](#contract)
- [PTB-XL adapter](#ptb-xl-adapter)
- [Data access](#data-access)
- [Rendering](#rendering)
- [Adding a source adapter](#adding-a-source-adapter)
- [CLI](#cli)
- [MCP server](#mcp-server)
- [AetioMed integration](#aetiomed-integration)
- [Testing](#testing)
- [Docker, CI and releases](#docker-ci-and-releases)

## Requirements and setup

- Python 3.13 (pinned in `.python-version`)
- [uv](https://docs.astral.sh/uv/)

```sh
git clone https://github.com/janthoXO/AetioECG.git
cd AetioECG
uv sync
uv run aetioecg --help
```

```
pyproject.toml                  dependencies, the `aetioecg` script, ruff and pyright settings
.env.example                    PTBXL_SOURCE
proto/aetioecg/v1/ecg.proto     the contract
examples/request.json           an EcgRequest
src/aetioecg/
├── core.py                     EcgSource port, Recording, list_options, get_ecg
├── ptbxl.py                    EcgSource over PTB-XL
├── render.py                   Recording leads -> SVG
├── cli.py                      CLI: options, get, mcp, grpc; source() wires the adapter
├── mcp_server.py               MCP server: list_ecg_options, get_ecg_svg
├── grpc_server.py              gRPC server: EcgService ListOptions, GetEcg
└── v1/                         generated protobuf code (committed, do not edit)
tests/                          test suite
```

## Architecture

Ports and adapters with one small core.

```
 driving adapters              core (core.py)                  driven adapters
 ----------------        -----------------------------      ----------------------
  cli.py        ---+        list_options(source)               EcgSource (port)
  (options/get/     +-->  get_ecg(source, request)  ----->   options() / retrieve()
   mcp/grpc)        |     validate -> retrieve                    |
  mcp_server.py  ---+     -> render_svg (render.py)               +-- ptbxl.PtbXl
  grpc_server.py ---+                                             +-- (planned) parametric synthesis
```

- `core.py` is the whole core interface: `list_options(source)` and `get_ecg(source, request)`. `get_ecg` checks the request against the source's options (at least one statement, every code known), draws a seed if none was given, calls `source.retrieve`, renders the recording with `render_svg` and assembles the `Ecg` message.
- The one port is `EcgSource` (a `Protocol`): `options()` lists every statement it can be asked for; `retrieve(request, rng)` returns a `Recording` (12 leads in mV, sample rate, statements shown, sex, age, attribution). All randomness comes from the given `random.Random`.
- Rendering and validation stay in the core, so a new source only produces a `Recording`.
- `cli.source()` (cached) is the only place that picks and configures an adapter.

## Contract

[`proto/aetioecg/v1/ecg.proto`](proto/aetioecg/v1/ecg.proto) defines the messages (`EcgRequest`, `Ecg`, `EcgOptions`, `Statement`, `Attribution`, enums `Sex` and `StatementKind`) and an `EcgService` with `ListOptions` and `GetEcg`. `grpc_server.py` serves the service; the CLI and MCP expose the same two operations. JSON on the wire is the proto3 JSON mapping: camelCase field names, enums as names (`SEX_FEMALE`), `bytes` as base64 (over gRPC, `bytes` are raw).

**Regenerate** the Python code after any change to the `.proto` and commit the result:

```sh
uv run python -m grpc_tools.protoc -Iproto --python_out=src --pyi_out=src --grpc_python_out=src proto/aetioecg/v1/ecg.proto
```

CI regenerates and fails when `git diff src/aetioecg/v1` is not empty.

**Consumers** (for example AetioMed, TypeScript) copy or fetch the `.proto` and generate their own types. With [ts-proto](https://github.com/stephenh/ts-proto) via buf, a `buf.gen.yaml` with the `ts-proto` plugin and `buf generate` over `proto/aetioecg/v1/ecg.proto` is enough; `protoc --ts_proto_out` works as well. Parse and print JSON with the proto3 JSON mapping of the generated types.

## PTB-XL adapter

`ptbxl.py`'s `PtbXl` is retrieval, not synthesis: it picks one of the 21,799 recordings in PTB-XL 1.0.3 (CC BY 4.0).

**Index.** On first use it reads `ptbxl_database.csv` (one row per recording) and `scp_statements.csv` (about 7 MB together) and keeps them in memory. A recording's `.hea` and `.dat` (500 Hz, `filename_hr`, about 120 KB) are read only when it is chosen.

**Statements.** Each recording's `scp_codes` maps a code to a likelihood. Statements with likelihood below 50 are ignored; 0 means "not rated" (form and rhythm statements) and counts. `options()` lists the codes of `scp_statements.csv` that appear in at least one recording, with description and kinds (diagnostic, form, rhythm; a statement can have several).

**Matching.** Candidates are the recordings whose statements include every requested code. None: `ValueError("no PTB-XL record shows all of [...]; try fewer statements")`.

**Ranking.** Among candidates, the lowest tuple wins, in this order:

1. number of extra findings (statements beyond those requested; sinus rhythm `SR` is not counted),
2. signal flaws: one per noise annotation (`baseline_drift`, `static_noise`, `burst_noise`, `electrodes_problems`), plus one when the record was not validated by a human,
3. sex mismatch (only when a sex was requested),
4. age gap in 10-year steps (only when an age was requested and known).

Ties are broken by a choice from the seeded `rng`, so request plus seed is deterministic.

**Age.** PTB-XL codes ages above 89 as 300; AetioECG caps them at 90. Age may be unknown for a record (`Ecg.age` unset).

**Signal.** Records are WFDB format 16 (interleaved little-endian int16), the only format PTB-XL uses; the reader parses header and data by hand, applies gain and baseline, and rejects any other format. Lead names `AVR`, `AVL`, `AVF` become `aVR`, `aVL`, `aVF`.

**Attribution.** Every `Ecg` carries `record` (`ptb-xl/<ecg_id>`), the PTB-XL citation (DOI 10.13026/kfzx-aw45) and `CC BY 4.0`.

## Data access

`PTBXL_SOURCE` is a folder path or a URL, read in `cli.source()`. Unset, it is `https://physionet.org/files/ptb-xl/1.0.3/`. The same relative paths are read from either, so a URL needs no local copy; each `get` then downloads the two CSVs once per process (about 7 MB) and the chosen record.

To work offline, download the dataset (about 1.7 GB):

```sh
curl -O https://physionet.org/static/published-projects/ptb-xl/ptb-xl-a-large-publicly-available-electrocardiography-dataset-1.0.3.zip
unzip ptb-xl-a-large-publicly-available-electrocardiography-dataset-1.0.3.zip -d data
export PTBXL_SOURCE=data/ptb-xl-a-large-publicly-available-electrocardiography-dataset-1.0.3
```

Point `PTBXL_SOURCE` at the folder that contains `ptbxl_database.csv`. `/data/` is git-ignored. With Docker, mount the folder read-only and set `PTBXL_SOURCE` to the mount point (see `docker-compose.yml`).

## Rendering

`render.py`'s `render_svg(leads, rate)` draws an SVG in millimetres on grid paper:

- 3x4 layout, 2.5 s per lead (columns I/II/III, aVR/aVL/aVF, V1-V3, V4-V6), plus a 10 s lead II rhythm strip below;
- 25 mm/s, 10 mm/mV, so the image is 250 mm of signal wide;
- display rate 250 Hz: 500 Hz input is halved, invisible at this scale, half the file size;
- the only text is the lead names and the "25 mm/s  10 mm/mV" note, so there is nothing to translate.

## Adding a source adapter

1. Implement `EcgSource` (`core.py`): `options()` returns an `EcgOptions` with the codes the source can produce; `retrieve(request, rng)` returns a `core.Recording` showing every requested statement (already validated against `options()`), drawing all randomness from `rng`, and raises `ValueError` when nothing fits. Leads must cover all names in `core.LEADS`, in mV.
2. Wire it in `cli.source()`. There is one source today; choose by an environment variable when there are two.
3. Add tests against a small fake dataset. Rendering, request validation and seeding need no changes.

## CLI

`cli.py` uses pydantic-settings' CLI support (`CliApp`, `CliSubCommand`) on plain pydantic models.

| Command | Arguments and flags |
| --- | --- |
| `options` | prints `EcgOptions` as proto3 JSON |
| `get FILE` | `FILE` is an `EcgRequest` JSON file, `-` reads stdin; `-o, --output PATH` SVG to write (required); prints the `Ecg` without `image` to stdout |
| `grpc` | `--host` (default `127.0.0.1`); `--port` (default `50051`) |
| `mcp` | `--http` serve streamable HTTP instead of stdio; `--host` (default `127.0.0.1`); `--port` (default `8000`) |

Errors (`ValueError`, `OSError`, invalid request JSON) print `error: <message>` to stderr and exit with status 1.

## MCP server

`mcp_server.py` uses the official `mcp` SDK 2.x (`MCPServer`). Tools:

| Tool | Arguments | Result |
| --- | --- | --- |
| `list_ecg_options` | none | `EcgOptions` as text content and structured content |
| `get_ecg_svg` | `statements`, `sex` (enum name), `age`, `seed` | embedded SVG resource, and the `Ecg` without `image` as structured content |

The `get_ecg_svg` parameters mirror `EcgRequest` field by field. The SVG is a `BlobResourceContents` with uri `ecg://<record>.svg`, MIME `image/svg+xml` and a base64 `blob`. Errors reach the client as tool errors. The stdio transport is the default; the HTTP transport (`mcp --http`) serves `/mcp` and has no authentication.

## gRPC server

`grpc_server.py` serves `aetioecg.v1.EcgService` with `grpcio` (`aetioecg grpc`, default `127.0.0.1:50051`). Why gRPC: typed service-to-service calls with a client generated from the `.proto`, binary `bytes` (the SVG is not base64) and deadlines/cancellation. MCP stays for LLM agents, the CLI for scripts and humans.

| Method | Request | Response |
| --- | --- | --- |
| `ListOptions` | `ListOptionsRequest` | `EcgOptions` |
| `GetEcg` | `EcgRequest` | `Ecg` (including `image`) |

Status codes: `ValueError` (invalid request) becomes `INVALID_ARGUMENT`, `OSError` (dataset unreachable) becomes `UNAVAILABLE`. The port is plaintext: no TLS, no health service and no reflection yet, so grpcurl needs `-import-path proto -proto aetioecg/v1/ecg.proto`. Add `grpcio-health-checking` when an orchestrator probes it.

## AetioMed integration

AetioMed may call either MCP (current, like AetioReferral) or gRPC with a client generated from the `.proto` (for example `@grpc/grpc-js` with ts-proto `outputServices=grpc-js`). The MCP flow, over streamable HTTP (`http://<host>:8000/mcp`):

1. Call `list_ecg_options` once and cache the codes; map the case's findings to these codes.
2. Call `get_ecg_svg` with `statements`, and `sex` and `age` of the case's patient. Pass a seed derived from the case for reproducibility.
3. Read the embedded resource from `content`: its `blob` is the base64-encoded SVG. `structuredContent` holds the statements the ECG actually shows (possibly more than requested), sex, age, seed and attribution.

Show the attribution wherever the ECG is displayed (CC BY 4.0).

## Testing

```sh
uv run pytest
uv run ruff format && uv run ruff check
uv run pyright          # checks src/ only
```

Tests live in `tests/` and go through the core interface and the adapters, not internals. A test checks that the `get_ecg_svg` parameters mirror `EcgRequest`.

## Docker, CI and releases

- `Dockerfile`: build stage `debian:trixie-slim` with Debian's Python 3.13 and a pinned uv; runtime `gcr.io/distroless/python3-debian13:nonroot` (no shell, non-root). Both use `/usr/bin/python3.13`, so the copied venv stays valid. Entry point `aetioecg`, default command `mcp --http --host 0.0.0.0 --port 8000`; the image exposes 8000 and 50051 (`grpc --host 0.0.0.0` serves gRPC instead). `PTBXL_SOURCE` is not set in the image. `proto/` is not copied: the generated code is committed.
- `docker-compose.yml`: service `mcp`, port from `PORT` (default 8000), and service `grpc`, port from `GRPC_PORT` (default 50051); `PTBXL_SOURCE` passed through; a commented volume mounts `./data/ptb-xl` read-only.
- `.github/workflows/build.yml` (pull requests): `uv sync --locked`, regenerate the protobuf code and fail on a diff, `ruff format --check`, `ruff check`, `pyright`, `pytest`, `aetioecg --help`, `uv build`.
- `.github/workflows/package.yml` (pull requests to `main`, reusable): sets the version, builds wheel and sdist and the Docker image, smoke-tests the image (`--help`) and uploads artifacts.
- `.github/workflows/release.yml`: on `v*` tags and on pushes to `main` that touch `src/`, `pyproject.toml`, `uv.lock`, the `Dockerfile` or the workflow. `.github/actions/determine-version` takes the version from the tag, or else bumps the patch of the latest release (starting at `0.0.1`). Pushes `ghcr.io/janthoxo/aetioecg/server:<version>` and `:latest` and creates a GitHub release with the image tar, wheel and sdist.
- `astral-sh/setup-uv` has no moving major tags; pin an exact version.
