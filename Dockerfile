# One image, two stages. `prod` is last, so DigitalOcean App Platform (which
# builds the final stage) gets gunicorn; docker-compose asks for `dev`, which
# adds pytest and gets the source bind-mounted over /app.
FROM python:3.14-slim AS base

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# The venv lives outside /app so the dev bind mount can cover /app without
# shadowing it.
ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH"

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY . .


FROM base AS dev
RUN uv sync --frozen


FROM base AS prod
EXPOSE 8080
CMD ["sh", "-c", "flask --app wsgi db upgrade && gunicorn --bind 0.0.0.0:8080 wsgi:app"]
