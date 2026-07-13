# Backend image: FastAPI panel managed with uv.
FROM python:3.12-slim-bookworm

# uv for fast, reproducible dependency installs.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# Install dependencies first for better layer caching.
COPY pyproject.toml ./
RUN uv pip install --system --no-cache -r pyproject.toml

COPY . .

# Normalize CRLF -> LF on the entrypoint so it runs even if checked out on Windows.
RUN sed -i 's/\r$//' entrypoint.sh

EXPOSE 8000

# Apply DB migrations on startup, then exec the CMD (or the compose `command:`
# override). ENTRYPOINT is not overridden by compose `command:`, so migrations
# always run first.
ENTRYPOINT ["sh", "entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
