FROM python:3.14-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY . .

ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 8080
CMD ["sh", "-c", "flask --app wsgi db upgrade && gunicorn --bind 0.0.0.0:8080 wsgi:app"]
