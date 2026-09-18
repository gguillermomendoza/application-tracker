# syntax=docker/dockerfile:1

FROM python:3.13-slim

# Install uv from the official image.
COPY --from=ghcr.io/astral-sh/uv:0.12.15 /uv /uvx /bin/

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_PYTHON_DOWNLOADS=0

WORKDIR /app

# Install third-party dependencies first so this layer can be cached.
COPY pyproject.toml uv.lock ./

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync \
        --locked \
        --no-dev \
        --no-install-project

# Only copy files required by the production runtime.
COPY src/ ./src/
COPY main.py ./

# Run using the environment created by uv.
ENV PATH="/app/.venv/bin:$PATH"

# Do not run the application as root.
RUN useradd --create-home --uid 10001 appuser \
    && chown -R appuser:appuser /app

USER appuser

# Cloud Run Job = one process that runs and exits.
CMD ["python", "main.py"]
