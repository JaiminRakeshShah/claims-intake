FROM python:3.12-slim-bookworm

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH"

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project --no-cache

COPY src ./src
COPY data ./data
RUN uv sync --frozen --no-dev --no-cache

EXPOSE 8000

CMD ["uvicorn", "claims.api.routes:app", "--host", "0.0.0.0", "--port", "8000"]
