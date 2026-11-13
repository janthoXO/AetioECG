# AetioECG: 12-Lead ECG Provider for Medical Education

**AetioECG is an open-source Python MCP server and CLI that returns a real 12-lead ECG as SVG for the SCP-ECG statements you ask for, such as atrial fibrillation (`AFIB`) or inferior myocardial infarction (`IMI`). The ECGs are real recordings from the PTB-XL dataset, selected by statement, sex and age. It is built for medical education and virtual-patient platforms.**

[![Build](https://github.com/janthoXO/AetioECG/actions/workflows/build.yml/badge.svg)](https://github.com/janthoXO/AetioECG/actions/workflows/build.yml)
![Python 3.13](https://img.shields.io/badge/python-3.13-blue)
![MCP server](https://img.shields.io/badge/MCP-server-black)
![License: MIT](https://img.shields.io/badge/license-MIT-green)

## Table of Contents

1. [What is AetioECG?](#what-is-aetioecg)
2. [Key Features](#key-features)
3. [Use Cases](#use-cases)
4. [Quick Start](#quick-start)
5. [Use with Claude and Other MCP Clients](#use-with-claude-and-other-mcp-clients)
6. [Request and Response](#request-and-response)
7. [FAQ](#faq)
8. [Data and Attribution](#data-and-attribution)
9. [Related Projects](#related-projects)
10. [License](#license)
11. [Developer Guide](README-DEV.md)

## What is AetioECG?

AetioECG answers one question: "show me an ECG with these findings". The caller names one or more [SCP-ECG](https://physionet.org/content/ptb-xl/1.0.3/) statement codes and, optionally, a preferred sex and age. AetioECG picks the best-matching real recording from PTB-XL and renders it as an SVG on grid paper: twelve leads in a 3x4 layout plus a lead II rhythm strip, at 25 mm/s and 10 mm/mV.

It first lists every statement code it can produce (`list_ecg_options`), so a client never has to guess codes. The contract is a protobuf schema, [`proto/aetioecg/v1/ecg.proto`](proto/aetioecg/v1/ecg.proto), spoken as proto3 JSON.

AetioECG is for education only and not for clinical use. It uses no LLM.

## Key Features

- **Real ECGs**: recordings from PTB-XL (21,799 ECGs of 10 s, 12 leads), not generated waveforms.
- **Statement-based**: ask for any SCP-ECG code in the dataset (diagnostic, form or rhythm statements); several codes must all be shown.
- **Best-match selection**: fewest extra findings first, then cleanest signal, then the requested sex, then the closest age. See the [Developer Guide](README-DEV.md#ptb-xl-adapter).
- **Reproducible**: the same request and seed return the same ECG; the seed is returned with every result.
- **Local or online data**: read PTB-XL straight from PhysioNet (the default, nothing to download) or from a local copy.
- **Attribution included**: every result carries the record id, the PTB-XL citation and the license.
- **Two interfaces**: an MCP server (stdio or streamable HTTP) for LLM clients and agents, and a command-line tool for scripts.
- **Language-free image**: the SVG holds only lead names and the paper speed and gain note, so it needs no translation.

## Use Cases

- **Medical education**: show students the ECG of a virtual patient, as in the sister project [AetioMed](https://github.com/janthoXO/AetioMed).
- **ECG interpretation practice**: produce examples of a given rhythm or finding for slides, quizzes and exams.
- **Agents and chat clients**: let Claude or another MCP client fetch a matching ECG during a conversation.
- **Testing software**: feed realistic ECG images into viewers and document pipelines.

## Quick Start

Requirements: Python 3.13 and [uv](https://docs.astral.sh/uv/).

```sh
git clone https://github.com/janthoXO/AetioECG.git
cd AetioECG
uv sync
```

List the statement codes, then get an ECG:

```sh
uv run aetioecg options
uv run aetioecg get examples/request.json -o ecg.svg
```

`get` writes the SVG and prints the rest of the result (statements shown, sex, age, seed, attribution) as JSON. Without `PTBXL_SOURCE`, the first call reads the dataset index (about 7 MB) from PhysioNet. To work offline, download PTB-XL once and point `PTBXL_SOURCE` at it; see the [Developer Guide](README-DEV.md#data-access).

Run `uv run aetioecg --help` for all commands.

### Docker

Every release publishes an image to GitHub Container Registry, built on a distroless Python base. By default it runs the MCP server over streamable HTTP on port 8000:

```sh
docker run --rm -p 8000:8000 ghcr.io/janthoxo/aetioecg/server
```

Any CLI command works too:

```sh
docker run --rm ghcr.io/janthoxo/aetioecg/server options
```

To use a local PTB-XL copy, mount it and set `PTBXL_SOURCE`:

```sh
docker run --rm -p 8000:8000 -v ./data/ptb-xl:/data/ptb-xl:ro -e PTBXL_SOURCE=/data/ptb-xl ghcr.io/janthoxo/aetioecg/server
```

From a checkout, `docker compose up --build` serves the MCP server on `http://127.0.0.1:8000/mcp`. Each release also attaches the Python wheel and source distribution.

## Use with Claude and Other MCP Clients

AetioECG speaks the [Model Context Protocol](https://modelcontextprotocol.io). Add it to Claude Code:

```sh
claude mcp add aetioecg -- uv run --directory /path/to/AetioECG aetioecg mcp
```

Or to any client that reads an `mcpServers` config, such as Claude Desktop:

```json
{
  "mcpServers": {
    "aetioecg": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/AetioECG", "aetioecg", "mcp"]
    }
  }
}
```

For a networked deployment, run `uv run aetioecg mcp --http` and connect to `http://127.0.0.1:8000/mcp`. The HTTP transport has no authentication, so keep it on localhost or a private network.

Tools:

- `list_ecg_options()`: every valid statement code with description and kind. Call this first.
- `get_ecg_svg(statements, sex?, age?, seed?)`: one ECG as an embedded `image/svg+xml` resource, plus the result without the image as structured content.

## Request and Response

Request (`aetioecg.v1.EcgRequest`, proto3 JSON, [`examples/request.json`](examples/request.json)):

```json
{"statements": ["AFIB"], "sex": "SEX_FEMALE", "age": 72, "seed": 7}
```

- `statements`: one or more codes from `list_ecg_options`; the ECG shows all of them. `["NORM"]` asks for a normal ECG.
- `sex`: `SEX_MALE` or `SEX_FEMALE`, a preference. Omit for any.
- `age`: preferred age in years, a preference. Ages above 89 count as 90 (PTB-XL does not give exact ages above 89).
- `seed`: optional. Omit for a random one, which is returned.

Response for this request (`aetioecg.v1.Ecg`; the CLI prints it without `image`):

```json
{
  "mimeType": "image/svg+xml",
  "statements": [
    {"code": "AFIB", "description": "atrial fibrillation", "kinds": ["STATEMENT_KIND_RHYTHM"]}
  ],
  "sex": "SEX_FEMALE",
  "age": 78,
  "seed": 7,
  "attribution": {
    "record": "ptb-xl/4161",
    "citation": "Wagner, P., Strodthoff, N., ... https://doi.org/10.13026/kfzx-aw45",
    "license": "CC BY 4.0"
  }
}
```

`statements` lists everything the ECG shows, so it can contain codes you did not ask for. The `image` field holds the SVG bytes (base64 in JSON).

## FAQ

### What is AetioECG?

AetioECG is an open-source Python tool that returns a real 12-lead ECG as SVG for requested SCP-ECG statements. It runs as an MCP server and as a CLI.

### Are the ECGs synthetic?

They are real recordings from PTB-XL, selected and rendered by AetioECG; the patients are not identified. A parametric synthesis source is planned as a second data source behind the same interface.

### Which ECG findings can I ask for?

Every statement PTB-XL contains, for example `NORM`, `AFIB`, `IMI`, `CLBBB`, `STACH`. `list_ecg_options` (or `aetioecg options`) returns the exact list with descriptions.

### What if no ECG shows all the statements I asked for?

The request fails with an error that suggests fewer statements. Statements are combined with "and", so rare combinations may not exist in PTB-XL.

### Does it need internet access?

Only for the dataset. By default it reads PTB-XL from PhysioNet on demand; with a local copy (`PTBXL_SOURCE`) it works offline.

### Does it use an LLM?

No.

### Can I use it clinically?

No. It is for education. Do not use it for diagnosis or patient care.

### How do I reproduce an ECG?

Send the same request with the seed from the earlier result.

### How does AetioECG relate to AetioMed?

[AetioMed](https://github.com/janthoXO/AetioMed) generates synthetic patient cases for medical education. AetioECG supplies the ECG a case can include. The [Developer Guide](README-DEV.md#aetiomed-integration) describes the integration.

## Data and Attribution

ECGs come from PTB-XL 1.0.3, licensed [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). If you use AetioECG output, credit the dataset and its paper:

> Wagner, P., Strodthoff, N., Bousseljot, R., Samek, W., & Schaeffter, T. (2022). PTB-XL, a large publicly available electrocardiography dataset (version 1.0.3). PhysioNet. https://doi.org/10.13026/kfzx-aw45

Every result carries this citation and the record id in `attribution`. Wagner et al., "PTB-XL, a large publicly available electrocardiography dataset", Scientific Data 7, 154 (2020) is the accompanying paper.

## Related Projects

- [AetioMed](https://github.com/janthoXO/AetioMed): LLM-based synthetic medical case generator for medical education.
- [AetioReferral](https://github.com/janthoXO/AetioReferral): synthetic medical referral letters as PDF.

## License

AetioECG is released under the [MIT License](LICENSE). The PTB-XL data it reads is CC BY 4.0 and is not part of this repository.

## Developer Guide

Architecture, the contract, the PTB-XL adapter, rendering, adding a data source, MCP and CLI details, testing and the AetioMed integration are in [README-DEV.md](README-DEV.md).
