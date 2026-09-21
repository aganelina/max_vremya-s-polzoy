FROM python:3.13-slim AS builder
COPY --from=ghcr.io/astral-sh/uv:0.10 /uv /bin/uv
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-dev

FROM python:3.13-slim
RUN useradd --system --uid 10001 --create-home app
COPY certs/russian_trusted_root_ca.crt certs/russian_trusted_sub_ca.crt /usr/local/share/ca-certificates/
RUN update-ca-certificates
RUN mkdir -p /data/signing && chown app /data/signing
WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
COPY alembic.ini ./
COPY migrations ./migrations
COPY app ./app
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1 FORWARDED_ALLOW_IPS=* \
    SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt
USER app
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--no-access-log"]
