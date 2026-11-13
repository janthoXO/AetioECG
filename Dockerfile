# Stage 1: install the app and its dependencies into /app/.venv.
# Debian 13 ships Python 3.13 at /usr/bin/python3.13, the same interpreter as the
# distroless runtime below, so the venv's interpreter link stays valid there.
FROM debian:trixie-slim AS build

COPY --from=ghcr.io/astral-sh/uv:0.13.3 /uv /usr/local/bin/uv
RUN apt-get update \
    && apt-get install -y --no-install-recommends python3 \
    && rm -rf /var/lib/apt/lists/*

ENV UV_PYTHON=/usr/bin/python3.13 \
    UV_PYTHON_DOWNLOADS=never \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app
# Dependencies first, so this layer is cached until uv.lock changes.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv uv sync --locked --no-dev --no-install-project

# README.md and LICENSE are referenced by pyproject.toml and needed to build the project wheel.
# proto/ is not needed: the generated code is committed under src/aetioecg/v1/.
COPY README.md LICENSE ./
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv uv sync --locked --no-dev --no-editable

# Stage 2: production image using Distroless (Python 3.13, no shell, non-root user).
FROM gcr.io/distroless/python3-debian13:nonroot AS runner

LABEL org.opencontainers.image.source="https://github.com/janthoXO/AetioECG" \
      org.opencontainers.image.description="Synthetic 12-lead ECG provider: MCP server and CLI that return real PTB-XL ECGs for SCP-ECG statements as SVG." \
      org.opencontainers.image.licenses="MIT"

WORKDIR /app
COPY --from=build /app/.venv /app/.venv

EXPOSE 8000

# PTBXL_SOURCE is not set: PTB-XL is read from PhysioNet unless you set it (-e) or mount a local copy.
# Any CLI command works: `docker run IMAGE options`.
ENTRYPOINT ["/app/.venv/bin/aetioecg"]
CMD ["mcp", "--http", "--host", "0.0.0.0", "--port", "8000"]
