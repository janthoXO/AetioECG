# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

AetioECG returns real 12-lead ECGs from PTB-XL as SVG for requested SCP-ECG statements, exposed as an MCP server, a gRPC server and a CLI. It uses no LLM. `README.md` is the user overview, `README-DEV.md` the full technical reference.

## Commands

```bash
uv sync                                              # install (Python 3.13, deps from uv.lock)
uv run pytest                                        # all tests
uv run pytest tests/<file>.py::<test>                # one test
uv run ruff format && uv run ruff check              # format + lint (line length 140)
uv run pyright                                       # type check; covers src/ only
uv run python -m grpc_tools.protoc -Iproto --python_out=src --pyi_out=src --grpc_python_out=src proto/aetioecg/v1/ecg.proto   # regenerate src/aetioecg/v1 after editing the .proto
uv run aetioecg options
uv run aetioecg get examples/request.json -o ecg.svg
uv run aetioecg grpc [--port 50051]                   # gRPC server (plaintext) on 127.0.0.1:50051
uv run aetioecg mcp [--http]                         # MCP server, stdio or streamable HTTP on 127.0.0.1:8000/mcp
docker build -t aetioecg .                           # distroless runtime image
docker compose up --build                            # MCP over HTTP on port 8000
```

CI (`.github/workflows/build.yml`) runs `uv sync --locked`, a protobuf regeneration that must leave `git diff src/aetioecg/v1` empty, `ruff format --check`, `ruff check`, `pyright`, `pytest`, `aetioecg --help` and `uv build`; keep all of them green. `get` and `options` read PTB-XL (network or `PTBXL_SOURCE`), so CI does not run them.

## Architecture

Ports and adapters with one small core:

- `core.py` is the whole core interface: `list_options(source)` and `get_ecg(source, request)`. `cli.py`, `mcp_server.py` and `grpc_server.py` are thin driving adapters over them.
- The one port is `EcgSource` (`options()`, `retrieve(request, rng) -> Recording`). `ptbxl.py`'s `PtbXl` is the only adapter; a parametric synthesizer is planned as a second. `cli.source()` (cached) is the only place an adapter is chosen; `PTBXL_SOURCE` (folder or URL, default PhysioNet) configures it.
- Validation, seeding and SVG rendering (`render.py`) are in the core, so a source only produces a `Recording`.
- The contract is `proto/aetioecg/v1/ecg.proto`. The generated code in `src/aetioecg/v1/` is committed and never hand-edited. JSON uses the proto3 JSON mapping (camelCase, enum names).
- PTB-XL ranking: fewest extra findings (`SR` not counted), then signal flaws, then sex mismatch, then age gap in 10-year steps, seeded choice among ties; diagnostic statements with likelihood below 50 are ignored.

## Making changes

- Contract change: edit the `.proto`, regenerate (command above; it also rewrites `ecg_pb2_grpc.py`), commit the generated code, and update `mcp_server.py` (the `get_ecg_svg` parameters mirror `EcgRequest` field by field; a test enforces it). Consumers such as AetioMed sync the `.proto`.
- New source adapter: implement `EcgSource`, wire it in `cli.source()`; see `README-DEV.md#adding-a-source-adapter`.
- The MCP SDK is 2.x: `mcp.server.mcpserver.MCPServer`, types from `mcp_types`, test clients via `mcp.Client(server)`.
- Every result must keep its `attribution` (PTB-XL is CC BY 4.0).
- Keep tests independent of the network and of the working directory: use a small fake PTB-XL folder, never PhysioNet.
- Mark deliberate shortcuts with a `ponytail:` comment naming the limit and the upgrade path (see `cli.source()`).

## Build and release

- `Dockerfile`: build stage `debian:trixie-slim` with Debian's Python 3.13, runtime `gcr.io/distroless/python3-debian13:nonroot`. Both must keep the same interpreter path (`/usr/bin/python3.13`) or the copied venv breaks. `proto/` is not copied; `PTBXL_SOURCE` is not set in the image.
- `release.yml` publishes on every push to `main` that touches `src/`, `pyproject.toml`, `uv.lock`, the `Dockerfile` or the workflow: patch-bumped GitHub release plus `ghcr.io/janthoxo/aetioecg/server`. Merging such a PR releases.
- `astral-sh/setup-uv` has no moving major tags; pin an exact version (e.g. `@v10.2.0`).

## Repo conventions

- `data/` is git-ignored: a local PTB-XL copy lives there. Never commit dataset files.
- AetioMed (`../AetioMed`) is the sister project that embeds these ECGs; its integration contract is in `README-DEV.md#aetiomed-integration`.
