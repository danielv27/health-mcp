FROM ghcr.io/astral-sh/uv:python3.14-bookworm-slim

WORKDIR /app

COPY pyproject.toml uv.lock ./
COPY src ./src

RUN uv sync --locked --no-dev

ENTRYPOINT ["/app/.venv/bin/health-mcp"]
CMD ["serve"]
