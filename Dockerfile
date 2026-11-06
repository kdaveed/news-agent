# One image for every service (init, web, collector, dispatcher); Compose picks the command.
# No secrets are baked in: NEWSALERT_SECRET_KEY and SMTP settings come from the environment.
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.13.0 /uv /uvx /usr/local/bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

# Dependencies first (cached layer), then the project itself.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY src ./src
RUN uv sync --frozen --no-dev

RUN useradd --create-home --uid 1000 app \
    && mkdir -p /app/data \
    && chown app:app /app/data
USER app

ENV NEWSALERT_DATABASE_URL=sqlite:////app/data/newsalert.db \
    NEWSALERT_DATA_DIR=/app/data

EXPOSE 8000
CMD ["uvicorn", "newsalert.web.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
